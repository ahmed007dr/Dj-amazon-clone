"""
Sending — the single entry point for mail in the system.

⚠️  **Three configuration layers, and their order is deliberate:**

        an enabled account in the database  ← the admin sets it from the screen
                 ↓ if absent
        the `.env` configuration (EMAIL_*)  ← a fresh install before any setup
                 ↓ if absent
        the console                         ← nothing is sent and nothing fails

    The third layer is not a luxury: a fresh install has an empty database with
    no account in it, and activating the first admin needs an activation email.
    Without the safe fallback the system becomes impossible to bootstrap.

⚠️  **And `settings.EMAIL_*` is never modified at runtime.**

    `settings` is global and not thread-safe, and the account is chosen **per
    message** according to its responsibility. Modifying it made two concurrent
    messages swap accounts: marketing mail going out from the security account
    and vice versa — a defect that appears only under load and never reproduces
    during diagnosis.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import transaction
from django.db.models import F
from django.utils import timezone, translation

from mailing.models import (
    BACKOFF_MINUTES,
    MAX_ATTEMPTS,
    STUCK_MINUTES,
    DeliveryState,
    EmailAccount,
    MailRoute,
    MailSecurity,
    MailTransport,
    OutboundMessage,
    TemplateOverride,
)
from mailing.purposes import SECURITY_PURPOSES
from mailing.templates import FALLBACK_LANGUAGE, TEMPLATES

logger = logging.getLogger(__name__)

SMTP_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
CONSOLE_BACKEND = "django.core.mail.backends.console.EmailBackend"


# ═══════════════════════════════════════════════════════════
#  Account selection
# ═══════════════════════════════════════════════════════════


def sending_accounts():
    """The accounts fit to send, in priority order."""
    return EmailAccount.objects.filter(
        is_active=True,
        direction__in=["OUT", "BOTH"],
    ).order_by("-priority", "code")


def resolve_account(purpose: str = "", template_key: str = "") -> EmailAccount | None:
    """
    The account this mail goes out from — from the most specific to the most general.

        a specific template  →  the purpose  →  the default  →  highest priority  →  `.env`

    ⚠️  **A default terminus is mandatory.**

        Without falling back to the default, a template added tomorrow is not
        sent — not with an error but silently. The screen says the notification
        was sent, the customer received nothing, and no line in any log explains why.

    ⚠️  **And the purpose is derived from the template, not from the caller.**

        A call passing a purpose contradicting its template's used to send
        "password reset" from the marketing account. The template declares its
        purpose, and it is the source.
    """
    template = TEMPLATES.get(template_key) if template_key else None
    if template is not None:
        purpose = template.purpose

    accounts = sending_accounts()

    for route in _routes_for(purpose, template_key):
        account = route.account
        if account.is_active and account.sends and _fence_allows(account, purpose):
            return account

    default = accounts.filter(is_default=True).first()
    if default is not None and _fence_allows(default, purpose):
        return default

    return next((a for a in accounts if _fence_allows(a, purpose)), None)


def _routes_for(purpose: str, template_key: str):
    """The matching responsibilities, most specific first."""
    if not purpose:
        return []

    routes = MailRoute.objects.filter(purpose=purpose, is_active=True).select_related("account")

    exact = [r for r in routes if r.template_key == template_key] if template_key else []
    general = [r for r in routes if not r.template_key]
    return exact + general


def _fence_allows(account: EmailAccount, purpose: str) -> bool:
    """
    ⚠️  **The firewall is applied twice deliberately** — here and in `MailRoute.clean()`.

        The duplication is not an oversight: `clean()` guards what is written
        from the screen, and this guards what is read. A row written before the
        rule existed, or an account that became a marketing one **after** being
        assigned, passes the first and does not pass the second. And the
        potential price — a security message from a blacklisted account — is
        dearer than one logical check.
    """
    return not (account.is_marketing and purpose in SECURITY_PURPOSES)


def connection_for(account: EmailAccount | None):
    """
    An SMTP connection built from the account — not from `settings`.

    ⚠️  `None` means "use the `.env` configuration": the second layer.
    """
    if account is None:
        return None

    if account.transport == MailTransport.CONSOLE:
        return get_connection(backend=CONSOLE_BACKEND)

    return get_connection(
        backend=SMTP_BACKEND,
        host=account.host,
        port=account.port,
        username=account.username,
        password=account.password,
        use_tls=account.security == MailSecurity.TLS,
        use_ssl=account.security == MailSecurity.SSL,
        timeout=account.timeout,
    )


# ═══════════════════════════════════════════════════════════
#  Health
# ═══════════════════════════════════════════════════════════


def record_success(account: EmailAccount | None) -> None:
    if account is None:
        return
    EmailAccount.objects.filter(pk=account.pk).update(
        last_success_at=timezone.now(), consecutive_failures=0, last_error=""
    )


def record_failure(account: EmailAccount | None, error: str) -> None:
    """
    ⚠️  `F`, not read-then-increment: two messages failing together each read
        the counter before the other writes, so one failure is recorded instead
        of two — and a collapsed account reads as slightly troubled.

    ⚠️  And the in-memory object is not updated: `update` writes to the row directly.
    """
    if account is None:
        return

    EmailAccount.objects.filter(pk=account.pk).update(
        last_error_at=timezone.now(),
        last_error=error[:2000],
        consecutive_failures=F("consecutive_failures") + 1,
    )


# ═══════════════════════════════════════════════════════════
#  Sending
# ═══════════════════════════════════════════════════════════


def send_mail(
    template_key: str,
    *,
    to: str,
    language: str,
    context: dict,
    fail_silently: bool = True,
    purpose: str = "",
) -> bool:
    """
    Enqueue a message and schedule its delivery after the commit.

    ⚠️  **It is no longer a synchronous send — and the difference is correctness, not performance.**

        Sending inside the transaction happened before it committed, so a
        transaction rolled back after the send meant a customer receiving "we
        have received your order ORD-…" for an order that does not exist in the
        database. The row here is written inside the same transaction and is
        rolled back with it, and delivery starts on `on_commit` — that is, once
        the event has become a fact.

    ⚠️  **And an SMTP failure no longer means a lost message.**

        `fail_silently=True` swallowed the failure with no retry: a password
        reset request was lost permanently because the server was down for two
        seconds. The row remains and is retried with a gradual backoff.

    The return value means **"enqueued"**, not "delivered". Whether it arrived
    is known from the row.
    """
    message = enqueue(template_key, to=to, language=language, context=context, purpose=purpose)
    return message is not None


def enqueue(
    template_key: str,
    *,
    to: str,
    language: str,
    context: dict,
    purpose: str = "",
) -> OutboundMessage:
    """
    Render now, deliver after the commit.

    ⚠️  **Rendering happens here, not at delivery** — the text is a snapshot, not a reference.

        The template may be edited in the meantime, and the context may change:
        "your order total is 450" becomes another figure after a return. The
        message describes the moment of the event.
    """
    template = TEMPLATES.get(template_key)
    if template is None:
        raise KeyError(f"قالب بريد غير معروف: {template_key}")

    with translation.override(language):
        subject, body = render(template_key, language, context)

    message = OutboundMessage.objects.create(
        to_email=to,
        subject=subject[:500],
        body=body,
        template_key=template_key,
        purpose=template.purpose or purpose,
        language=language,
    )

    # ⚠️  `on_commit`, not a direct call: delivery starts once the event has
    #     become a fact in the database. And an exception inside the callback
    #     is swallowed in `deliver` — because it happens **after** the response,
    #     so raising it would fail a request whose work already succeeded.
    transaction.on_commit(lambda: deliver(message.pk))

    return message


def send_to_user(template_key: str, user, context: dict, **kwargs) -> bool:
    """
    Derives the language and address from the user.

    ⚠️  `user` is passed in, not imported — this domain knows nothing of `accounts`.
    """
    payload = {"name": user.get_short_name(), **context}
    return send_mail(
        template_key,
        to=user.email,
        language=getattr(user, "preferred_language", FALLBACK_LANGUAGE),
        context=payload,
        **kwargs,
    )


# ═══════════════════════════════════════════════════════════
#  The check — before the first customer, not after
# ═══════════════════════════════════════════════════════════


def verify(account: EmailAccount) -> tuple[bool, str]:
    """
    A real SMTP handshake with no message sent.

    ⚠️  **The most important button on the mail screen.**

        Configuring SMTP with no immediate verification means the fault is
        discovered by the first real customer who has lost their password — that
        is, at the worst possible moment and on the most important message in
        the system.
    """
    connection = connection_for(account)

    if connection is None:
        return False, "لا حساب"

    try:
        connection.open()
        connection.close()
    except Exception as exc:
        record_failure(account, str(exc))
        return False, str(exc)

    record_success(account)
    return True, ""


def send_test(account: EmailAccount, *, to: str) -> tuple[bool, str]:
    """
    A test message from a specific account.

    ⚠️  It deliberately bypasses `resolve_account`: the question here is "does
        **this** account work?", not "who is responsible for this purpose?".
        Passing it through the resolver tested an account other than the one the
        operator is sitting in front of.
    """
    message = EmailMultiAlternatives(
        subject=f"رسالة تجريبية — {account.label_ar}",
        body=(
            f"هذه رسالة تجريبية من حساب البريد «{account.label_ar}» ({account.code}).\n"
            f"وصولها يعني أن الإعداد صحيح."
        ),
        from_email=account.sender,
        to=[to],
        reply_to=[account.reply_to] if account.reply_to else None,
        connection=connection_for(account),
    )

    try:
        message.send(fail_silently=False)
    except Exception as exc:
        logger.exception("فشلت الرسالة التجريبية من %s", account.code)
        record_failure(account, str(exc))
        return False, str(exc)

    record_success(account)
    return True, ""


# ═══════════════════════════════════════════════════════════
#  The responsibility map — the result is visible, not inferred
# ═══════════════════════════════════════════════════════════

#: Where the account came from — the screen shows it beside every template
SOURCE_TEMPLATE = "template"
SOURCE_PURPOSE = "purpose"
SOURCE_DEFAULT = "default"
SOURCE_PRIORITY = "priority"
SOURCE_ENV = "env"


def routing_map() -> list[dict]:
    """
    For each template: which account it actually goes out from, **and where that answer came from**.

    ⚠️  The reason matters, not the result alone.

        A screen showing "Orders ← the primary account" leaves the operator
        believing they assigned it, when it is in fact a fallback to the
        default. So if they change the default one day, messages they thought
        were pinned move with it. The "source" column makes the difference
        between "assigned" and "fell back to the default" visible before it surprises anyone.
    """
    routes = list(MailRoute.objects.filter(is_active=True).select_related("account"))
    by_template = {r.template_key: r for r in routes if r.template_key}
    by_purpose = {r.purpose: r for r in routes if not r.template_key}

    default = sending_accounts().filter(is_default=True).first()

    rows = []
    for key, template in sorted(TEMPLATES.items()):
        account = resolve_account(template_key=key)

        if account is None:
            source = SOURCE_ENV
        elif key in by_template and by_template[key].account_id == account.pk:
            source = SOURCE_TEMPLATE
        elif (
            template.purpose in by_purpose and by_purpose[template.purpose].account_id == account.pk
        ):
            source = SOURCE_PURPOSE
        elif default is not None and account.pk == default.pk:
            source = SOURCE_DEFAULT
        else:
            source = SOURCE_PRIORITY

        rows.append(
            {
                "template_key": key,
                "purpose": template.purpose,
                "subject_ar": template.subject_ar,
                "account_id": account.pk if account else None,
                "account_code": account.code if account else "",
                "account_label_ar": account.label_ar if account else "",
                "source": source,
            }
        )

    return rows


# ═══════════════════════════════════════════════════════════
#  Rendering — the override outranks the code
# ═══════════════════════════════════════════════════════════


def source_for(template_key: str):
    """
    The effective version: an enabled override if one exists, otherwise the code version.

    ⚠️  And absence is a valid state, not a gap.

        The table holds **overrides**, not templates: the system works fully
        with not a single row in it, and deleting the override restores the
        original text immediately — with no deployment and no backup restore.
    """
    override = TemplateOverride.objects.filter(key=template_key, is_active=True).first()
    return override or TEMPLATES.get(template_key)


def render(template_key: str, language: str, context: dict) -> tuple[str, str]:
    """
    ⚠️  And a failure here falls back to the code text, not to an empty message.

        The override is edited by a human, and humans make mistakes. And no
        defect in it must be able to stop "password reset" arriving — the
        original version is always there, and using it is cheaper than dropping
        the message.
    """
    default = TEMPLATES.get(template_key)
    source = source_for(template_key)

    try:
        return source.render(language, context)
    except Exception:
        if source is default or default is None:
            raise
        logger.exception("تعذّر تصيير تجاوز القالب %s — سقوط إلى نص الكود", template_key)
        return default.render(language, context)


# ═══════════════════════════════════════════════════════════
#  Delivery — from the queue to the server
# ═══════════════════════════════════════════════════════════


def _claim(message_id) -> OutboundMessage | None:
    """
    Claim a row for delivery — **with an atomic condition, not read-then-write**.

    ⚠️  Two workers reading the same "pending" row send it twice: the customer
        receives two identical messages. And `UPDATE … WHERE status = 'PENDING'`
        makes exactly one of them the winner however concurrent they are —
        whoever gets `1` back owns it.

    ⚠️  And the claim lasts `STUCK_MINUTES` and then lapses.

        A process that died between the claim and the send used to leave the row
        claimed forever: a message lost with no visible failure — worse than a
        declared one.
    """
    now = timezone.now()

    claimed = OutboundMessage.objects.filter(
        pk=message_id,
        status__in=(DeliveryState.PENDING, DeliveryState.SENDING),
        next_attempt_at__lte=now,
    ).update(
        status=DeliveryState.SENDING,
        next_attempt_at=now + timedelta(minutes=STUCK_MINUTES),
    )

    if not claimed:
        return None

    return OutboundMessage.objects.filter(pk=message_id).first()


def deliver(message_id) -> bool:
    """
    An attempt to deliver a single row.

    ⚠️  **It never raises.** It is called from `on_commit` — that is, after the
        work has been done and has succeeded. An exception here used to fail a
        request over an email.
    """
    try:
        message = _claim(message_id)
        if message is None:
            return False
        return _attempt(message)
    except Exception:
        logger.exception("تعذّر تسليم الرسالة %s", message_id)
        return False


def _attempt(message: OutboundMessage) -> bool:
    account = resolve_account(purpose=message.purpose, template_key=message.template_key)

    # ⚠️  Threading headers are added at delivery, not at enqueueing: the row
    #     carries the ids, and building them here keeps it all in one place.
    headers = {}
    if message.in_reply_to:
        headers["In-Reply-To"] = message.in_reply_to
    if message.references:
        headers["References"] = message.references

    email = EmailMultiAlternatives(
        subject=message.subject,
        body=message.body,
        from_email=account.sender if account else settings.DEFAULT_FROM_EMAIL,
        to=[message.to_email],
        reply_to=[account.reply_to] if account and account.reply_to else None,
        connection=connection_for(account),
        headers=headers or None,
    )

    try:
        email.send(fail_silently=False)
    except Exception as exc:
        _record_attempt_failure(message, account, str(exc))
        return False

    OutboundMessage.objects.filter(pk=message.pk).update(
        status=DeliveryState.SENT,
        sent_at=timezone.now(),
        attempts=F("attempts") + 1,
        account=account,
        last_error="",
    )
    record_success(account)
    return True


def _record_attempt_failure(message: OutboundMessage, account, error: str) -> None:
    """
    ⚠️  Final failure is **a declared state**, not a row that waits forever.

        A row retried without limit hides a permanent fault (a wrong address · a
        full mailbox) in the noise of the attempts, so nobody knows the message
        will never arrive. `FAILED` turns it into a line on the screen that gets
        read and dealt with.
    """
    attempts = message.attempts + 1
    exhausted = attempts >= MAX_ATTEMPTS
    delay = BACKOFF_MINUTES[min(message.attempts, len(BACKOFF_MINUTES) - 1)]

    OutboundMessage.objects.filter(pk=message.pk).update(
        status=DeliveryState.FAILED if exhausted else DeliveryState.PENDING,
        attempts=attempts,
        next_attempt_at=timezone.now() + timedelta(minutes=delay),
        last_error=error[:2000],
        account=account,
    )

    logger.warning(
        "فشل تسليم بريد %s إلى %s (محاولة %s/%s): %s",
        message.template_key,
        message.to_email,
        attempts,
        MAX_ATTEMPTS,
        error,
    )
    record_failure(account, error)


def deliver_pending(limit: int = 100) -> int:
    """
    The periodic task: deliver what is due.

    ⚠️  The claim happens **before** the send and outside any long transaction.

        Sending inside a transaction holds the lock on the row for the whole
        SMTP handshake — and a slow server stalls the entire table. The atomic
        claim releases the lock immediately and lets the condition alone prevent
        duplication.
    """
    now = timezone.now()

    candidates = list(
        OutboundMessage.objects.filter(
            status__in=(DeliveryState.PENDING, DeliveryState.SENDING),
            next_attempt_at__lte=now,
        )
        .order_by("next_attempt_at")
        .values_list("pk", flat=True)[:limit]
    )

    return sum(1 for pk in candidates if deliver(pk))


def retry(message: OutboundMessage) -> bool:
    """
    A manual retry from the screen — it resets the backoff, not the counter.

    ⚠️  The counter remains: it is the record of what happened. Resetting it
        makes a message that failed twenty times look like it is on its first attempt.
    """
    OutboundMessage.objects.filter(pk=message.pk).update(
        status=DeliveryState.PENDING, next_attempt_at=timezone.now()
    )
    return deliver(message.pk)


# ═══════════════════════════════════════════════════════════
#  Replying to inbound mail
# ═══════════════════════════════════════════════════════════


def enqueue_raw(
    *,
    to: str,
    subject: str,
    body: str,
    language: str = "ar",
    purpose: str = "",
    in_reply_to: str = "",
    references: str = "",
) -> OutboundMessage:
    """
    A free-text message — for a reply written by an employee.

    ⚠️  It goes through the same queue rather than a direct send: a manual reply
        deserves the retry and the record that automated mail gets. And the
        worst message to lose is the one a human wrote once.
    """
    message = OutboundMessage.objects.create(
        to_email=to,
        subject=subject[:500],
        body=body,
        purpose=purpose,
        language=language,
        in_reply_to=in_reply_to[:998],
        references=references,
    )
    transaction.on_commit(lambda: deliver(message.pk))
    return message


def reply(inbound, *, body: str, subject: str = "", actor=None) -> OutboundMessage:
    """
    A reply to an inbound message — inside its thread.

    ⚠️  **And an automated message is never replied to.**

        Two auto-replies facing each other generate thousands of messages in
        minutes, and end with the domain blacklisted — taking order mail and
        password resets down with it. The block belongs here, not on the screen:
        screens get bypassed.
    """
    from core.errors import BusinessError, ErrorCode
    from mailing.models import InboundState

    if inbound.is_auto:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            detail="لا يُردّ على رسالة آلية — حماية من حلقات البريد",
        )

    # ⚠️  The thread is built by appending the message id to its references, not replacing them:
    #     replacing breaks the thread at the customer's end, so the reply appears as a new conversation.
    references = " ".join(filter(None, [inbound.references, inbound.message_id]))

    outbound = enqueue_raw(
        to=inbound.from_email,
        subject=subject or f"Re: {inbound.subject}",
        body=body,
        purpose=inbound.account.routes.values_list("purpose", flat=True).first() or "",
        in_reply_to=inbound.message_id,
        references=references,
    )

    inbound.status = InboundState.REPLIED
    if actor is not None and inbound.assigned_to_id is None:
        inbound.assigned_to = actor
    inbound.save(update_fields=["status", "assigned_to", "updated_at"])

    return outbound
