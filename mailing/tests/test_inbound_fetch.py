"""
Inbound mail — the pull from the mailbox, the connection test and the attachment download.

⚠️  **Why this file exists: "the customer replied and it never showed up".**

    Parsing was always tested (`test_inbound.py`); the *pull* was not, and the pull is where
    mail disappears without a trace: a cursor that moved past a message that failed, a cursor
    that kept counting a previous mailbox's UIDs, a folder name that selected nothing and
    looked like an empty mailbox. Each test below is one of those.

    The server is a small fake `imaplib` client implementing exactly the calls `fetch` makes
    (`select`, `response`, `uid search`, `uid fetch`, `logout`) — real message bytes, no
    network.
"""

from email.message import EmailMessage

import pytest
from django.apps import apps
from django.test import Client
from django.urls import reverse
from rest_framework.test import APIClient

from core.models.audit import AuditAction, AuditLog
from core.testing import grant_all_domains
from mailing import inbound, services
from mailing.models import (
    CredentialKey,
    EmailAccount,
    EmailCredential,
    InboundAttachment,
    InboundMessage,
    InboundState,
    MailDirection,
    MailTransport,
)

PASSWORD = "Str0ng-Test-Pass!23"

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


# ═══════════════════════════════════════════════════════════
#  A fake IMAP server
# ═══════════════════════════════════════════════════════════

REFUSE = "REFUSE"  # the server answers NO to the FETCH: transient
GONE = None  # the server answers OK with no data: expunged since the SEARCH


class FakeIMAP:
    """Just enough of `imaplib.IMAP4` for `mailing.inbound`."""

    def __init__(self, messages=None, *, uidvalidity=1000, folder_exists=True):
        self.messages: dict[int, object] = dict(messages or {})
        self.uidvalidity = uidvalidity
        self.folder_exists = folder_exists
        self.fetch_calls: list[int] = []
        self.fetch_specs: list[str] = []
        self.searches: list[str] = []
        self.selected = None
        self.readonly = None
        self.logged_out = False

    def select(self, folder, readonly=False):
        self.selected, self.readonly = folder, readonly
        if not self.folder_exists:
            return "NO", [b"[NONEXISTENT] Unknown Mailbox: " + folder.encode()]
        return "OK", [str(len(self.messages)).encode()]

    def response(self, code):
        assert code == "UIDVALIDITY"
        return code, [str(self.uidvalidity).encode()] if self.uidvalidity else [None]

    def uid(self, command, *args):
        if command == "search":
            criterion = args[1]
            self.searches.append(criterion)
            uids = sorted(self.messages)
            if criterion == "ALL":
                found = uids
            else:
                # RFC 3501: `n:*` always includes the highest message, even when it is below n
                start = int(criterion.split()[1].split(":")[0])
                found = [uid for uid in uids if uid >= start] or uids[-1:]
            return "OK", [" ".join(map(str, found)).encode()]

        assert command == "fetch"
        uid = int(args[0])
        self.fetch_calls.append(uid)
        self.fetch_specs.append(args[1])
        item = self.messages.get(uid)

        if isinstance(item, Exception):
            raise item
        if item == REFUSE:
            return "NO", [b"server busy"]
        if item is None:
            return "OK", [None]
        return "OK", [(f"{uid} (UID {uid} BODY[] {{{len(item)}}}".encode(), item), b")"]

    def logout(self):
        self.logged_out = True


def raw(number: int, *, subject="رسالة", attachment: bytes | None = None) -> bytes:
    message = EmailMessage()
    message["Message-ID"] = f"<msg-{number}@client.example>"
    message["From"] = "عميل <customer@client.example>"
    message["To"] = "support@example.com"
    message["Subject"] = f"{subject} {number}"
    message["Date"] = "Tue, 18 Aug 2026 10:30:00 +0300"
    message.set_content(f"نص الرسالة رقم {number}")
    if attachment:
        message.add_attachment(attachment, maintype="image", subtype="png", filename="صورة.png")
    return message.as_bytes()


def mailbox_of(*numbers: int, **kwargs) -> FakeIMAP:
    return FakeIMAP({n: raw(n) for n in numbers}, **kwargs)


@pytest.fixture
def account(db):
    return EmailAccount.objects.create(
        code="support",
        label_ar="الدعم",
        label_en="Support",
        direction=MailDirection.BOTH,
        transport=MailTransport.CONSOLE,
        from_email="support@example.com",
        imap_host="imap.example.com",
        imap_username="support@example.com",
    )


@pytest.fixture
def server(monkeypatch):
    """Install a fake server; the test chooses its contents with `server.set(...)`."""

    class Holder:
        client = FakeIMAP()

        def set(self, client: FakeIMAP) -> FakeIMAP:
            self.client = client
            return client

    holder = Holder()
    monkeypatch.setattr(inbound, "_connect", lambda account: holder.client)
    return holder


def fresh(account: EmailAccount) -> EmailAccount:
    account.refresh_from_db()
    return account


# ═══════════════════════════════════════════════════════════
#  The first pull
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestFirstPull:
    def test_it_starts_from_the_newest_messages_not_the_oldest(self, account, server):
        """
        ⚠️  A mailbox with years of history, pulled oldest-first in batches of 50, buries
            today's reply under a backlog nobody will read. The newest N come first.
        """
        client = server.set(mailbox_of(*range(1, 121)))

        assert inbound.fetch(account, limit=50) == 50

        assert client.fetch_calls == list(range(71, 121))
        assert InboundMessage.objects.count() == 50
        assert fresh(account).imap_last_uid == 120

    def test_what_arrives_afterwards_is_pulled_oldest_first_from_the_cursor(self, account, server):
        client = server.set(mailbox_of(*range(1, 121)))
        inbound.fetch(account, limit=50)

        for number in range(121, 126):
            client.messages[number] = raw(number)
        client.fetch_calls.clear()

        assert inbound.fetch(account) == 5
        assert client.fetch_calls == [121, 122, 123, 124, 125]
        assert fresh(account).imap_last_uid == 125

    def test_an_empty_mailbox_still_records_a_baseline(self, account, server):
        client = server.set(FakeIMAP({}))

        assert inbound.fetch(account) == 0

        account = fresh(account)
        assert account.imap_fingerprint
        assert account.imap_uidvalidity == 1000
        assert account.imap_last_fetch_at is not None

        # ... and the first message that ever arrives is not mistaken for old history
        client.messages[1] = raw(1)
        assert inbound.fetch(account) == 1

    def test_the_mailbox_is_opened_read_only_and_peeked(self, account, server):
        """The pull must not flip the "unread" flag on mail a human is reading in webmail."""
        client = server.set(mailbox_of(1, 2))

        inbound.fetch(account)

        assert client.readonly is True
        assert client.selected == '"INBOX"'
        assert set(client.fetch_specs) == {"(BODY.PEEK[])"}
        assert client.logged_out is True

    def test_a_folder_name_with_a_space_is_quoted(self, account, server):
        account.imap_folder = "Sent Items"
        client = server.set(mailbox_of(1))

        inbound.fetch(account)

        assert client.selected == '"Sent Items"'


# ═══════════════════════════════════════════════════════════
#  The cursor never skips a message that failed
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCursorNeverPassesAFailure:
    def test_a_refused_fetch_stops_the_run_and_is_retried(self, account, server):
        """
        ⚠️  **The bug this prevents:** message 3 fails transiently, message 4 succeeds, the
            cursor lands on 4 - and message 3 is never looked at again.
        """
        client = server.set(FakeIMAP({1: raw(1), 2: raw(2), 3: REFUSE, 4: raw(4), 5: raw(5)}))

        assert inbound.fetch(account) == 2

        assert client.fetch_calls == [1, 2, 3]  # 4 and 5 were not touched
        account = fresh(account)
        assert account.imap_last_uid == 2
        assert account.imap_retry_uid == 3 and account.imap_retry_count == 1
        assert "UID 3" in account.imap_last_error

        client.messages[3] = raw(3)
        client.fetch_calls.clear()

        assert inbound.fetch(account) == 3
        assert client.fetch_calls == [3, 4, 5]
        account = fresh(account)
        assert account.imap_last_uid == 5
        assert account.imap_retry_uid == 0 and account.imap_retry_count == 0
        assert account.imap_last_error == ""
        assert InboundMessage.objects.count() == 5

    def test_a_connection_dropped_mid_message_is_retried_too(self, account, server):
        client = server.set(FakeIMAP({1: raw(1), 2: OSError("connection reset"), 3: raw(3)}))

        inbound.fetch(account)

        assert fresh(account).imap_last_uid == 1

        client.messages[2] = raw(2)
        assert inbound.fetch(account) == 2
        assert fresh(account).imap_last_uid == 3

    def test_a_message_that_can_never_be_imported_is_skipped_loudly(
        self, account, server, monkeypatch
    ):
        """
        ⚠️  Retrying forever is the other failure: one corrupt email would hold every message
            behind it hostage. After MAX_UID_RETRIES runs it is skipped, and the skip is shown.
        """
        client = server.set(mailbox_of(1, 2, 3))
        real_import = inbound.import_message

        def poisoned(acct, data):
            if b"msg-2@" in data:
                raise ValueError("corrupt body")
            return real_import(acct, data)

        monkeypatch.setattr(inbound, "import_message", poisoned)

        for run in range(1, inbound.MAX_UID_RETRIES):
            inbound.fetch(account)
            account = fresh(account)
            assert account.imap_last_uid == 1, f"run {run}: the cursor must stay behind UID 2"
            assert account.imap_retry_count == run

        inbound.fetch(account)  # the run that gives up on it

        account = fresh(account)
        assert account.imap_last_uid == 3, "UID 2 skipped, UID 3 imported in the same run"
        assert account.imap_retry_uid == 0
        assert "تُخطّيت" in account.imap_last_error
        assert "UID 2" in account.imap_last_error
        assert sorted(InboundMessage.objects.values_list("subject", flat=True)) == [
            "رسالة 1",
            "رسالة 3",
        ]
        assert client.fetch_calls.count(2) == inbound.MAX_UID_RETRIES

    def test_a_message_expunged_between_search_and_fetch_is_not_a_failure(self, account, server):
        server.set(FakeIMAP({1: raw(1), 2: GONE, 3: raw(3)}))

        assert inbound.fetch(account) == 2

        account = fresh(account)
        assert account.imap_last_uid == 3
        assert account.imap_last_error == ""
        assert account.imap_retry_count == 0

    def test_a_message_already_imported_does_not_count_twice(self, account, server):
        server.set(mailbox_of(1, 2))
        inbound.fetch(account)

        # the cursor is rewound (as after an interrupted run): dedup by Message-ID holds
        EmailAccount.objects.filter(pk=account.pk).update(imap_last_uid=0, imap_fingerprint="x")
        assert inbound.fetch(fresh(account)) == 0
        assert InboundMessage.objects.count() == 2


# ═══════════════════════════════════════════════════════════
#  The cursor belongs to one mailbox
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCursorResets:
    def _synced(self, account, server, numbers=(1, 2, 3)):
        client = server.set(mailbox_of(*numbers))
        inbound.fetch(account)
        return client, fresh(account)

    @pytest.mark.parametrize(
        "change",
        [
            {"imap_host": "imap.other-provider.example"},
            {"imap_username": "someone-else@example.com"},
            {"imap_folder": "Archive"},
        ],
    )
    def test_changing_the_connection_resets_the_cursor(self, account, server, change):
        """
        ⚠️  **The bug this prevents:** the account is pointed at another mailbox whose UIDs
            run 1..3, while the cursor still says 500. `UID 501:*` returns the newest
            message, which is filtered out as "old" - and nothing is ever imported again.
        """
        _client, account = self._synced(account, server)
        EmailAccount.objects.filter(pk=account.pk).update(imap_last_uid=500)
        account = fresh(account)
        for field, value in change.items():
            setattr(account, field, value)
        account.save()

        new_mailbox = server.set(FakeIMAP({1: raw(10), 2: raw(11), 3: raw(12)}, uidvalidity=1000))

        assert inbound.fetch(account) == 3
        assert new_mailbox.fetch_calls == [1, 2, 3]
        assert fresh(account).imap_last_uid == 3

    def test_rotating_the_password_or_port_does_not_reset(self, account, server):
        """The same mailbox through a different door is still the same mailbox."""
        _client, account = self._synced(account, server)
        EmailCredential.objects.create(
            account=account, key=CredentialKey.IMAP_PASSWORD, value="rotated"
        )
        account.imap_port = 143
        account.save()
        assert fresh(account).imap_fingerprint == inbound.fingerprint(account)

        client = server.set(mailbox_of(1, 2, 3, 4))
        client.fetch_calls.clear()

        assert inbound.fetch(fresh(account)) == 1
        assert client.fetch_calls == [4]

    def test_a_new_uidvalidity_resets_the_cursor(self, account, server):
        """
        ⚠️  After a mailbox is rebuilt the UIDs are renumbered: new mail can sit *below* the
            old cursor and would never be fetched.
        """
        _client, account = self._synced(account, server, numbers=range(1, 201))
        assert account.imap_last_uid == 200

        rebuilt = server.set(FakeIMAP({n: raw(1000 + n) for n in range(1, 6)}, uidvalidity=2222))

        assert inbound.fetch(account) == 5
        assert rebuilt.fetch_calls == [1, 2, 3, 4, 5]
        account = fresh(account)
        assert account.imap_last_uid == 5
        assert account.imap_uidvalidity == 2222

    def test_a_server_that_reports_no_uidvalidity_never_triggers_a_reset(self, account, server):
        client = server.set(mailbox_of(1, 2, uidvalidity=0))
        inbound.fetch(account)

        client.messages[3] = raw(3)
        client.fetch_calls.clear()

        assert inbound.fetch(fresh(account)) == 1
        assert client.fetch_calls == [3]

    def test_a_legacy_account_is_adopted_not_reset(self, account, server):
        """
        An account that was polled before these fields existed has a cursor and nothing
        else. Resetting it would silently re-baseline every production mailbox on deploy.
        """
        EmailAccount.objects.filter(pk=account.pk).update(imap_last_uid=40)
        client = server.set(mailbox_of(*range(35, 46)))

        assert inbound.fetch(fresh(account)) == 5

        assert client.fetch_calls == [41, 42, 43, 44, 45]
        account = fresh(account)
        assert account.imap_fingerprint == inbound.fingerprint(account)
        assert account.imap_uidvalidity == 1000
        assert account.imap_last_uid == 45


# ═══════════════════════════════════════════════════════════
#  Failures are visible
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestFailuresAreVisible:
    def test_a_folder_that_does_not_exist_is_an_error_not_an_empty_mailbox(self, account, server):
        """
        ⚠️  `imaplib` answers `("NO", …)` for an unknown folder instead of raising, so a
            mistyped name used to look exactly like a mailbox with nothing in it - forever.
        """
        account.imap_folder = "Inbxo"
        server.set(FakeIMAP({1: raw(1)}, folder_exists=False))

        with pytest.raises(inbound.MailboxError, match="Inbxo"):
            inbound.fetch(account)

        account = fresh(account)
        assert "Inbxo" in account.imap_last_error
        assert account.imap_last_error_at is not None
        assert InboundMessage.objects.count() == 0

    def test_a_login_failure_is_recorded_on_the_account(self, account, monkeypatch):
        import imaplib

        def refuse(acct):
            raise imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED] Invalid credentials")

        monkeypatch.setattr(inbound, "_connect", refuse)

        with pytest.raises(imaplib.IMAP4.error):
            inbound.fetch(account)

        error = fresh(account).imap_last_error
        assert "AUTHENTICATIONFAILED" in error
        assert "b'" not in error  # the bytes are decoded, not repr'd

    def test_the_sweep_keeps_going_and_records_the_failure(self, account, monkeypatch):
        def refuse(acct):
            raise OSError("timed out")

        monkeypatch.setattr(inbound, "_connect", refuse)

        assert inbound.fetch_all() == 0

        account = fresh(account)
        assert account.consecutive_failures == 1
        assert "timed out" in account.imap_last_error

    def test_success_clears_a_previous_error_and_stamps_the_time(self, account, server):
        EmailAccount.objects.filter(pk=account.pk).update(imap_last_error="old problem")
        server.set(mailbox_of(1))

        inbound.fetch(fresh(account))

        account = fresh(account)
        assert account.imap_last_error == ""
        assert account.imap_last_fetch_at is not None

    def test_smtp_success_does_not_wipe_the_imap_error(self, account):
        """On a BOTH account a working outbound path must not hide a broken inbound one."""
        EmailAccount.objects.filter(pk=account.pk).update(imap_last_error="IMAP is down")

        services.record_success(account)

        assert fresh(account).imap_last_error == "IMAP is down"

    def test_describe_decodes_bytes_arguments(self):
        assert inbound.describe(ValueError(b"bad \xd8\xa7")) == "ValueError: bad ا"
        assert inbound.describe(TimeoutError()) == "TimeoutError"


# ═══════════════════════════════════════════════════════════
#  The IMAP connection test
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def admin_client(db):
    user_model = apps.get_model("accounts", "User")
    admin = user_model.objects.create_user(
        email="imap-admin@test.local", password=PASSWORD, account_type="ADMIN"
    )
    admin.is_active = True
    admin.save()
    apps.get_model("administration", "AdminProfile").objects.create(user=admin)
    grant_all_domains(admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture
def customer_client(db):
    customer = apps.get_model("accounts", "User").objects.create_user(
        email="imap-customer@test.local", password=PASSWORD
    )
    customer.is_active = True
    customer.save()

    client = APIClient()
    client.force_authenticate(user=customer)
    return client


@pytest.mark.django_db
class TestCheckConnection:
    def test_it_reports_the_folder_the_count_and_the_last_uid(self, account, server):
        server.set(mailbox_of(5, 6, 9, uidvalidity=777))
        EmailAccount.objects.filter(pk=account.pk).update(imap_last_uid=6)

        result = inbound.check_connection(fresh(account))

        assert result == {
            "ok": True,
            "error": "",
            "folder": "INBOX",
            "messages": 3,
            "last_uid": 9,
            "uidvalidity": 777,
            "cursor": 6,
            "pending": 1,
        }

    def test_it_changes_nothing_in_the_mailbox_or_the_cursor(self, account, server):
        client = server.set(mailbox_of(1, 2, 3))

        inbound.check_connection(account)

        assert client.fetch_calls == []
        assert client.readonly is True
        assert fresh(account).imap_last_uid == 0
        assert InboundMessage.objects.count() == 0

    def test_a_missing_folder_is_reported(self, account, server):
        account.imap_folder = "Nope"
        server.set(FakeIMAP({}, folder_exists=False))

        result = inbound.check_connection(account)

        assert result["ok"] is False
        assert "Nope" in result["error"]
        assert "Nope" in fresh(account).imap_last_error

    def test_a_connection_error_is_reported_not_raised(self, account, monkeypatch):
        def refuse(acct):
            raise OSError("connection refused")

        monkeypatch.setattr(inbound, "_connect", refuse)

        result = inbound.check_connection(account)

        assert result["ok"] is False
        assert "connection refused" in result["error"]

    def test_an_account_without_a_host_says_so(self, account):
        account.imap_host = ""

        result = inbound.check_connection(account)

        assert result["ok"] is False and result["error"]

    def test_success_clears_the_recorded_error(self, account, server):
        EmailAccount.objects.filter(pk=account.pk).update(imap_last_error="old")
        server.set(mailbox_of(1))

        inbound.check_connection(fresh(account))

        assert fresh(account).imap_last_error == ""

    def test_the_endpoint(self, admin_client, account, server):
        server.set(mailbox_of(1, 2))

        response = admin_client.post(reverse("v1:mailing:account-test-imap", args=[account.pk]))

        assert response.status_code == 200
        assert response.data["ok"] is True
        assert response.data["messages"] == 2

    def test_the_endpoint_returns_200_with_ok_false_on_failure(
        self, admin_client, account, monkeypatch
    ):
        monkeypatch.setattr(
            inbound, "_connect", lambda acct: (_ for _ in ()).throw(OSError("no route"))
        )

        response = admin_client.post(reverse("v1:mailing:account-test-imap", args=[account.pk]))

        assert response.status_code == 200
        assert response.data["ok"] is False
        assert "no route" in response.data["error"]

    def test_a_customer_is_refused(self, customer_client, account):
        response = customer_client.post(reverse("v1:mailing:account-test-imap", args=[account.pk]))
        assert response.status_code == 403

    def test_the_account_payload_exposes_the_cursor_and_health_read_only(
        self, admin_client, account
    ):
        url = reverse("v1:mailing:account-detail", args=[account.pk])
        data = admin_client.get(url).data

        for field in (
            "imap_last_uid",
            "imap_uidvalidity",
            "imap_last_fetch_at",
            "imap_last_error",
            "imap_last_error_at",
        ):
            assert field in data

        admin_client.patch(url, {"imap_last_uid": 99999}, format="json")
        assert fresh(account).imap_last_uid == 0


@pytest.mark.django_db
class TestSmtpVerifyIgnoresInboundOnlyAccounts:
    @pytest.fixture
    def inbound_only(self, account):
        EmailAccount.objects.filter(pk=account.pk).update(direction=MailDirection.INBOUND)
        return fresh(account)

    def test_verify_does_not_try_and_does_not_record_a_failure(self, inbound_only):
        ok, error = services.verify(inbound_only)

        assert ok is False
        assert error == services.NOT_A_SENDING_ACCOUNT
        assert fresh(inbound_only).consecutive_failures == 0

    def test_the_endpoint_marks_it_skipped(self, admin_client, inbound_only):
        response = admin_client.post(reverse("v1:mailing:account-verify", args=[inbound_only.pk]))

        assert response.status_code == 200
        assert response.data["skipped"] is True

    def test_a_sending_account_is_not_skipped(self, admin_client, account, monkeypatch):
        monkeypatch.setattr(services, "verify", lambda acct: (True, ""))

        response = admin_client.post(reverse("v1:mailing:account-verify", args=[account.pk]))

        assert response.data["skipped"] is False

    def test_a_test_message_cannot_be_sent_from_a_receive_only_account(self, inbound_only):
        ok, error = services.send_test(inbound_only, to="a@example.com")

        assert ok is False and error == services.NOT_A_SENDING_ACCOUNT


# ═══════════════════════════════════════════════════════════
#  The inbox list
# ═══════════════════════════════════════════════════════════


def stored(account, number, **fields) -> InboundMessage:
    defaults = {
        "account": account,
        "message_id": f"<list-{number}@client.example>",
        "from_email": "customer@client.example",
        "subject": f"موضوع {number}",
        "received_at": "2026-08-18T10:30:00+03:00",
    }
    return InboundMessage.objects.create(**{**defaults, **fields})


@pytest.mark.django_db
class TestInboxList:
    def test_it_is_ordered_by_arrival_not_by_the_senders_date_header(self, admin_client, account):
        """
        ⚠️  The `Date` header is whatever the sender's clock said. A message stamped months
            ago sorted to a page nobody opens - "the customer replied and it is not there".
        """
        first = stored(account, 1, received_at="2026-08-18T10:00:00+03:00")
        second = stored(account, 2, received_at="2020-01-01T00:00:00+00:00")  # wrong clock
        third = stored(account, 3, received_at="2030-01-01T00:00:00+00:00")  # the future
        for step, message in enumerate((first, second, third)):
            InboundMessage.objects.filter(pk=message.pk).update(
                created_at=f"2026-08-18T12:0{step}:00+00:00"
            )

        response = admin_client.get(reverse("v1:mailing:inbox"))

        assert [row["subject"] for row in response.data["results"]] == [
            "موضوع 3",
            "موضوع 2",
            "موضوع 1",
        ]

    def test_it_is_paginated_with_page_numbers(self, admin_client, account):
        for number in range(30):
            stored(account, number)

        first = admin_client.get(reverse("v1:mailing:inbox"))
        second = admin_client.get(reverse("v1:mailing:inbox"), {"page": 2})

        assert first.data["count"] == 30
        assert first.data["pages"] == 2
        assert len(first.data["results"]) == 25
        assert len(second.data["results"]) == 5

    @pytest.mark.parametrize("state", [InboundState.ASSIGNED, InboundState.SPAM])
    def test_every_status_can_be_filtered(self, admin_client, account, state):
        stored(account, 1, status=state)
        stored(account, 2, status=InboundState.NEW)

        response = admin_client.get(reverse("v1:mailing:inbox"), {"status": state})

        assert [row["status"] for row in response.data["results"]] == [state]

    def test_the_summary_counts_only_new_messages(self, admin_client, account):
        stored(account, 1, status=InboundState.NEW)
        stored(account, 2, status=InboundState.NEW)
        stored(account, 3, status=InboundState.REPLIED)

        response = admin_client.get(reverse("v1:mailing:inbox-summary"))

        assert response.status_code == 200
        assert response.data == {"new": 2}

    def test_the_summary_is_admin_only(self, customer_client):
        assert customer_client.get(reverse("v1:mailing:inbox-summary")).status_code == 403

    def test_the_payload_has_an_arrival_time(self, admin_client, account):
        stored(account, 1)

        row = admin_client.get(reverse("v1:mailing:inbox")).data["results"][0]

        assert row["created_at"]
        assert row["received_at"]


# ═══════════════════════════════════════════════════════════
#  Attachment download
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def message_with_attachment(account, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    inbound_message = inbound.import_message(account, raw(1, subject="صورة", attachment=PNG_BYTES))
    return inbound_message, inbound_message.attachments.get()


def attachment_url(message, attachment) -> str:
    return reverse("v1:mailing:inbox-attachment", args=[message.pk, attachment.pk])


@pytest.mark.django_db
class TestAttachmentDownload:
    def test_an_admin_downloads_the_file(self, admin_client, message_with_attachment):
        message, attachment = message_with_attachment

        response = admin_client.get(attachment_url(message, attachment))

        assert response.status_code == 200
        assert b"".join(response.streaming_content) == PNG_BYTES
        assert response["Content-Type"] == "image/png"

    def test_it_is_always_a_download_never_inline(self, admin_client, message_with_attachment):
        """A file from a stranger is never rendered in the admin's session."""
        message, attachment = message_with_attachment

        response = admin_client.get(attachment_url(message, attachment))

        assert response["Content-Disposition"].startswith("attachment")
        assert "filename*=utf-8''" in response["Content-Disposition"].lower()  # the Arabic name
        assert response["X-Content-Type-Options"] == "nosniff"
        assert "no-store" in response["Cache-Control"]

    def test_the_download_is_audited(self, admin_client, message_with_attachment):
        message, attachment = message_with_attachment

        admin_client.get(attachment_url(message, attachment))

        entry = AuditLog.objects.filter(action=AuditAction.EXPORT).latest("id")
        assert entry.changes == {"message": str(message.pk), "attachment": str(attachment.pk)}
        assert attachment.filename in entry.object_repr

    def test_a_customer_is_refused_and_nothing_is_audited(
        self, customer_client, message_with_attachment
    ):
        message, attachment = message_with_attachment

        response = customer_client.get(attachment_url(message, attachment))

        assert response.status_code == 403
        assert not AuditLog.objects.filter(action=AuditAction.EXPORT).exists()

    def test_an_anonymous_visitor_is_refused(self, message_with_attachment):
        message, attachment = message_with_attachment

        response = APIClient().get(attachment_url(message, attachment))

        assert response.status_code in (401, 403)

    def test_an_attachment_cannot_be_fetched_through_another_message(
        self, admin_client, account, message_with_attachment
    ):
        """The URL names both ids; a mismatch is a 404, not the file."""
        _message, attachment = message_with_attachment
        other = stored(account, 2)

        response = admin_client.get(attachment_url(other, attachment))

        assert response.status_code == 404

    def test_a_missing_file_on_disk_is_a_404_not_a_500(self, admin_client, message_with_attachment):
        message, attachment = message_with_attachment
        attachment.file.storage.delete(attachment.file.name)

        response = admin_client.get(attachment_url(message, attachment))

        assert response.status_code == 404

    def test_the_serializer_no_longer_exposes_the_dead_media_link(
        self, admin_client, message_with_attachment
    ):
        """`file` pointed at `/media/mail/…`, which `config/urls.py` refuses to serve."""
        response = admin_client.get(reverse("v1:mailing:inbox"))

        row = response.data["results"][0]["attachments"][0]
        assert "file" not in row
        assert set(row) == {"id", "filename", "content_type", "size_bytes"}
        assert "/media/" not in response.content.decode()

    def test_the_media_path_itself_stays_blocked(self, message_with_attachment):
        _message, attachment = message_with_attachment

        response = Client().get(f"/media/{attachment.file.name}")

        assert response.status_code == 404

    def test_the_stored_row_is_the_signature_checked_type(self, message_with_attachment):
        _message, attachment = message_with_attachment

        assert isinstance(attachment, InboundAttachment)
        assert attachment.content_type == "image/png"
