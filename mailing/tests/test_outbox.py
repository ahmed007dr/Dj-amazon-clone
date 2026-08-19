"""
Outbox queue tests.

⚠️  **The two faults the queue exists for, and both were silent:**

    1. Sending inside the transaction before it commits — a transaction rolled
       back after the send means a customer receiving "we have received your
       order" for an order that does not exist.

    2. `fail_silently=True` with no retry — a server down for two seconds means
       a password reset request lost permanently, while the user sees a screen
       saying "we have sent you a message".
"""

from datetime import timedelta

import pytest
from django.core import mail as django_mail
from django.db import transaction
from django.utils import timezone

from mailing import services
from mailing.models import (
    BACKOFF_MINUTES,
    MAX_ATTEMPTS,
    DeliveryState,
    EmailAccount,
    MailTransport,
    OutboundMessage,
)

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture(autouse=True)
def clean_outbox(db):
    """
    ⚠️  The queue is a **shared** table, and counting on it measures what others left behind.

        Concurrency tests in other domains run with real transactions: they
        genuinely commit rows, and clean them with `TRUNCATE` on teardown. And
        when that teardown fails (as it sometimes does on hung thread
        connections) their rows stay in the reused test database — so a test
        here reads "two rows" while it created none.

        Cleaning before every test makes the assertion measure what it did itself.
    """
    OutboundMessage.objects.all().delete()


@pytest.fixture
def console_account(db, monkeypatch):
    monkeypatch.setattr(services, "CONSOLE_BACKEND", LOCMEM)
    return EmailAccount.objects.create(
        code="system",
        label_ar="النظام",
        label_en="System",
        transport=MailTransport.CONSOLE,
        from_email="noreply@example.com",
        is_default=True,
    )


@pytest.fixture
def dead_account(db):
    """A server that does not respond — a closed port and a one-second timeout."""
    return EmailAccount.objects.create(
        code="dead",
        label_ar="معطّل",
        label_en="Dead",
        host="127.0.0.1",
        port=1,
        timeout=1,
        from_email="noreply@example.com",
        is_default=True,
    )


def queue(template_key="password_changed", **overrides):
    payload = {
        "to": "customer@example.com",
        "language": "ar",
        "context": {"name": "أحمد"},
    }
    payload.update(overrides)
    return services.enqueue(template_key, **payload)


@pytest.mark.django_db
class TestSnapshot:
    def test_body_is_rendered_at_enqueue_not_at_delivery(self, console_account):
        """
        ⚠️  The text is a snapshot, not a reference: deferred rendering reads a
            template the admin may have edited in the meantime, and a context
            that may have changed — "your order total is 450" becomes another
            figure after a return.
        """
        message = queue(
            "order_placed",
            context={"name": "أحمد", "number": "ORD-1", "total": "450.00", "link": "x"},
        )

        assert "ORD-1" in message.subject
        assert "450.00" in message.body
        assert message.status == DeliveryState.PENDING


@pytest.mark.django_db
class TestCommitBoundary:
    """
    ⚠️  Without `transaction=True`.

        The transactional test truncates the tables on teardown, and combined
        with the hung thread connections in other domains' concurrency tests it
        makes the suite fail intermittently for reasons unrelated to what it
        tests. And the commit point is measured without it: callbacks registered
        inside a rolled-back block **are dropped**, which is exactly what
        "nothing was sent" means.
    """

    def test_rollback_leaves_no_message_and_schedules_no_delivery(
        self, console_account, django_capture_on_commit_callbacks
    ):
        """
        ⚠️  The first fault, literally: the row is written inside the
            transaction and rolled back with it, and the delivery is scheduled
            on `on_commit`, so it never happens at all.

            Before that, mail went out **before** the commit: a transaction
            rolled back afterwards meant a customer receiving "we have received
            your order ORD-…" for an order that does not exist in the database.
        """
        django_mail.outbox.clear()

        with django_capture_on_commit_callbacks() as callbacks:
            with pytest.raises(RuntimeError), transaction.atomic():
                queue()
                raise RuntimeError("العملية فشلت بعد تقييد البريد")

        assert OutboundMessage.objects.count() == 0
        assert callbacks == []
        assert django_mail.outbox == []

    def test_delivery_is_scheduled_only_after_commit(
        self, console_account, django_capture_on_commit_callbacks
    ):
        django_mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                message = queue()
            assert django_mail.outbox == []  # enqueued and not yet delivered

        message.refresh_from_db()
        assert message.status == DeliveryState.SENT
        assert message.sent_at is not None
        assert len(django_mail.outbox) == 1


@pytest.mark.django_db
class TestRetry:
    def test_failure_keeps_the_message_and_backs_off(self, dead_account):
        """
        ⚠️  The second fault: a temporary failure used to mean a message lost
            forever. The row remains and is retried with a gradual backoff
            rather than immediately — a server that refused on a rate limit
            refuses insistence too.
        """
        message = queue()
        before = timezone.now()

        assert services.deliver(message.pk) is False

        message.refresh_from_db()
        assert message.status == DeliveryState.PENDING
        assert message.attempts == 1
        assert message.last_error
        assert message.next_attempt_at >= before + timedelta(minutes=BACKOFF_MINUTES[0])

    def test_backoff_grows_with_each_attempt(self, dead_account):
        message = queue()

        delays = []
        for _ in range(3):
            OutboundMessage.objects.filter(pk=message.pk).update(next_attempt_at=timezone.now())
            started = timezone.now()
            services.deliver(message.pk)
            message.refresh_from_db()
            delays.append(round((message.next_attempt_at - started).total_seconds() / 60))

        assert delays == sorted(delays)
        assert delays[0] < delays[-1]

    def test_exhausted_attempts_become_a_declared_failure(self, dead_account):
        """
        ⚠️  A row retried without limit hides a permanent fault (a wrong address ·
            a full mailbox) in the noise of the attempts, so nobody knows the
            message will never arrive. `FAILED` turns it into a line that gets
            read and dealt with.
        """
        message = queue()

        for _ in range(MAX_ATTEMPTS):
            OutboundMessage.objects.filter(pk=message.pk).update(next_attempt_at=timezone.now())
            services.deliver(message.pk)

        message.refresh_from_db()
        assert message.status == DeliveryState.FAILED
        assert message.attempts == MAX_ATTEMPTS

    def test_failed_message_is_not_picked_up_again(self, dead_account):
        message = queue()
        OutboundMessage.objects.filter(pk=message.pk).update(
            status=DeliveryState.FAILED, next_attempt_at=timezone.now()
        )

        assert services.deliver_pending() == 0

    def test_manual_retry_keeps_the_attempt_history(self, dead_account):
        """
        ⚠️  A manual retry resets the backoff, not the counter: resetting it
            makes a message that failed twenty times look like it is on its first attempt.
        """
        message = queue()
        OutboundMessage.objects.filter(pk=message.pk).update(
            status=DeliveryState.FAILED, attempts=3, next_attempt_at=timezone.now()
        )
        message.refresh_from_db()

        services.retry(message)

        message.refresh_from_db()
        assert message.attempts >= 4

    def test_manual_retry_delivers_once_the_fault_is_fixed(self, console_account):
        """
        ⚠️  The real situation after a fault: the operator fixes the
            configuration and then retries from the screen. A row declared
            failed must accept the retry — otherwise the declaration becomes a
            final verdict on a valid message.
        """
        django_mail.outbox.clear()
        message = queue()
        OutboundMessage.objects.filter(pk=message.pk).update(
            status=DeliveryState.FAILED, attempts=MAX_ATTEMPTS
        )
        message.refresh_from_db()

        assert services.retry(message) is True

        message.refresh_from_db()
        assert message.status == DeliveryState.SENT
        assert len(django_mail.outbox) == 1


@pytest.mark.django_db
class TestClaiming:
    def test_a_message_is_never_delivered_twice(self, console_account):
        """
        ⚠️  Two workers reading the same row send it twice: the customer
            receives two identical messages. The claim is an atomic condition —
            whoever gets `1` back owns it.
        """
        django_mail.outbox.clear()
        message = queue()

        assert services.deliver(message.pk) is True
        assert services.deliver(message.pk) is False  # no second owner

        assert len(django_mail.outbox) == 1

    def test_a_claim_expires_so_a_crash_does_not_swallow_the_message(self, console_account):
        """
        ⚠️  A process that died between the claim and the send used to leave the
            row claimed forever — a message lost with no visible failure, which
            is worse than a declared one. The claim lasts and then lapses, so
            the periodic task picks it up.
        """
        django_mail.outbox.clear()
        message = queue()
        OutboundMessage.objects.filter(pk=message.pk).update(
            status=DeliveryState.SENDING,
            next_attempt_at=timezone.now() - timedelta(minutes=1),
        )

        assert services.deliver_pending() == 1
        assert len(django_mail.outbox) == 1

    def test_a_live_claim_is_left_alone(self, console_account):
        """A live claim held by another worker is not seized — or the duplication returns by the other door."""
        message = queue()
        OutboundMessage.objects.filter(pk=message.pk).update(
            status=DeliveryState.SENDING,
            next_attempt_at=timezone.now() + timedelta(minutes=10),
        )

        assert services.deliver_pending() == 0

    def test_pending_before_its_time_is_not_picked_up(self, console_account):
        message = queue()
        OutboundMessage.objects.filter(pk=message.pk).update(
            next_attempt_at=timezone.now() + timedelta(minutes=5)
        )

        assert services.deliver_pending() == 0


@pytest.mark.django_db
class TestPeriodicSweep:
    def test_the_sweep_delivers_what_is_due(self, console_account):
        """
        ⚠️  A safety net, not the main path: delivery starts on `on_commit`,
            and this sweep picks up what failed and what got stuck.

        ⚠️  And its scheduling in `ops` is tested **there**, not here: importing
            the management command from a `mailing` test dragged every business
            domain in with it (`accounts` · `cart` · `inventory` · `loyalty`)
            and broke the domain isolation contract — `import-linter` genuinely caught it.
        """
        django_mail.outbox.clear()
        queue()
        OutboundMessage.objects.update(next_attempt_at=timezone.now())

        assert services.deliver_pending() == 1
        assert len(django_mail.outbox) == 1
