"""
Inbound mail tests.

⚠️  **Tested against real message bytes, not against imagined objects.**

    Every defect is in the parsing, not the transport: an encoded Arabic header ·
    a multipart body · an attachment claiming to be a PDF · an auto-reply. And
    separating `import_message` from `fetch` is what makes that possible with no
    IMAP server.
"""

from email.message import EmailMessage

import pytest

from mailing import inbound
from mailing.models import (
    EmailAccount,
    InboundMessage,
    MailDirection,
    MailTransport,
)

#: A genuinely valid PNG — the signature alone is not enough, because the check reads the bytes
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082"
)


@pytest.fixture
def mailbox(db):
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


def build(**overrides) -> bytes:
    message = EmailMessage()
    message["Message-ID"] = overrides.pop("message_id", "<abc-123@client.example>")
    message["From"] = overrides.pop("sender", "عميل غاضب <customer@client.example>")
    message["To"] = "support@example.com"
    message["Subject"] = overrides.pop("subject", "استفساري عن الطلب")
    message["Date"] = "Tue, 18 Aug 2026 10:30:00 +0300"

    for header, value in overrides.pop("headers", {}).items():
        message[header] = value

    message.set_content(overrides.pop("body", "أين طلبي؟"))

    for name, data, subtype in overrides.pop("attachments", []):
        message.add_attachment(data, maintype="application", subtype=subtype, filename=name)

    return message.as_bytes()


@pytest.mark.django_db
class TestImport:
    def test_arabic_headers_are_decoded(self, mailbox):
        """
        ⚠️  An Arabic subject arrives encoded (`=?UTF-8?B?…?=`). Displaying it
            raw makes the message look corrupt on the support screen, so it gets ignored.
        """
        message = inbound.import_message(mailbox, build())

        assert message.subject == "استفساري عن الطلب"
        assert message.from_name == "عميل غاضب"
        assert message.from_email == "customer@client.example"
        assert "أين طلبي؟" in message.body_text

    def test_the_same_message_is_never_imported_twice(self, mailbox):
        """
        ⚠️  The pull happens every few minutes, and any interruption re-covers
            what was already pulled. Without a stable key one email appears ten
            times in the support inbox and two staff reply to it.
        """
        raw = build()

        assert inbound.import_message(mailbox, raw) is not None
        assert inbound.import_message(mailbox, raw) is None
        assert InboundMessage.objects.count() == 1

    def test_a_message_without_an_id_gets_a_stable_one(self, mailbox):
        """
        ⚠️  An id derived from the content, not a random one: a random one makes
            every pull re-import the same message.
        """
        message = EmailMessage()
        message["From"] = "anon@client.example"
        message["Subject"] = "بلا معرّف"
        message.set_content("نص")
        raw = message.as_bytes()

        first = inbound.import_message(mailbox, raw)

        assert first is not None
        assert first.message_id.startswith("<sha:")
        assert inbound.import_message(mailbox, raw) is None

    def test_html_is_stored_but_stays_out_of_the_text_field(self, mailbox):
        message = EmailMessage()
        message["Message-ID"] = "<html-1@client.example>"
        message["From"] = "customer@client.example"
        message["Subject"] = "بـHTML"
        message.set_content("النص الصريح")
        message.add_alternative("<p>نص <script>alert(1)</script></p>", subtype="html")

        stored = inbound.import_message(mailbox, message.as_bytes())

        assert "النص الصريح" in stored.body_text
        assert "<script>" not in stored.body_text
        assert "<script>" in stored.body_html  # kept for the archive and never displayed


@pytest.mark.django_db
class TestLoopProtection:
    @pytest.mark.parametrize(
        "headers",
        [
            {"Auto-Submitted": "auto-replied"},
            {"Precedence": "bulk"},
            {"X-Auto-Response-Suppress": "All"},
            {"List-Id": "<news.example.com>"},
        ],
    )
    def test_automatic_messages_are_flagged(self, mailbox, headers):
        """
        ⚠️  Two auto-replies facing each other generate thousands of messages in
            minutes: "your message was received" ← "I am on holiday" ← "your
            message was received"… and they end with the domain blacklisted,
            taking order mail and every password reset down with it.

            And the check covers four headers, not one: every provider uses a different one.
        """
        message = inbound.import_message(mailbox, build(headers=headers))

        assert message.is_auto is True

    def test_a_human_message_is_not_flagged(self, mailbox):
        assert inbound.import_message(mailbox, build()).is_auto is False

    def test_replying_to_an_automatic_message_is_refused(self, mailbox):
        from core.errors import BusinessError
        from mailing import services

        message = inbound.import_message(mailbox, build(headers={"Precedence": "bulk"}))

        with pytest.raises(BusinessError):
            services.reply(message, body="شكرًا لك")


@pytest.mark.django_db
class TestAttachments:
    def test_a_real_image_is_stored(self, mailbox):
        message = EmailMessage()
        message["Message-ID"] = "<img-1@client.example>"
        message["From"] = "customer@client.example"
        message["Subject"] = "صورة المنتج التالف"
        message.set_content("انظر الصورة")
        message.add_attachment(PNG_BYTES, maintype="image", subtype="png", filename="damage.png")

        stored = inbound.import_message(mailbox, message.as_bytes())

        attachment = stored.attachments.get()
        assert attachment.content_type == "image/png"
        assert attachment.size_bytes == len(PNG_BYTES)

    def test_a_disguised_executable_is_refused(self, mailbox):
        """
        ⚠️  **The most dangerous upload path in the system**: no logged-in user
            and no limit — an attacker need only know our mailbox address.

            And the name `invoice.pdf` means nothing: the true type is read from
            the file's first bytes (ADR-45). And anything whose signature is
            unrecognised is not stored.
        """
        message = EmailMessage()
        message["Message-ID"] = "<evil-1@client.example>"
        message["From"] = "attacker@client.example"
        message["Subject"] = "فاتورتك"
        message.set_content("مرفق")
        message.add_attachment(
            b"MZ\x90\x00\x03\x00\x00\x00PE executable",
            maintype="application",
            subtype="pdf",
            filename="فاتورة.pdf",
        )

        stored = inbound.import_message(mailbox, message.as_bytes())

        assert stored is not None  # the message stays
        assert stored.attachments.count() == 0  # and the attachment does not

    def test_an_oversized_attachment_is_skipped_and_the_message_kept(self, mailbox, monkeypatch):
        """
        ⚠️  Dropping the message because of a rejected attachment hides a
            genuine customer complaint. The attachment is discarded, and the
            text reaches support.
        """
        monkeypatch.setattr(inbound, "MAX_ATTACHMENT_BYTES", 10)

        message = EmailMessage()
        message["Message-ID"] = "<big-1@client.example>"
        message["From"] = "customer@client.example"
        message["Subject"] = "ملف كبير"
        message.set_content("مرفق ضخم")
        message.add_attachment(PNG_BYTES, maintype="image", subtype="png", filename="big.png")

        stored = inbound.import_message(mailbox, message.as_bytes())

        assert stored is not None
        assert stored.attachments.count() == 0


@pytest.mark.django_db
class TestReply:
    def test_reply_threads_into_the_customer_conversation(self, mailbox):
        """
        ⚠️  Without `In-Reply-To` our answer appears to the customer as a
            separate message rather than a reply — so they read it without their
            question in front of them and ask again.
        """
        from mailing import services
        from mailing.models import InboundState

        message = inbound.import_message(
            mailbox, build(headers={"References": "<older@client.example>"})
        )

        outbound = services.reply(message, body="طلبك في الطريق")

        assert outbound.to_email == "customer@client.example"
        assert outbound.subject.startswith("Re: ")
        assert outbound.in_reply_to == message.message_id
        # ⚠️  Appending, not replacing: replacing breaks the thread at the customer's end
        assert "<older@client.example>" in outbound.references
        assert message.message_id in outbound.references

        message.refresh_from_db()
        assert message.status == InboundState.REPLIED

    def test_reply_goes_through_the_queue_like_any_mail(self, mailbox):
        """The worst message to lose is the one a human wrote once."""
        from mailing import services
        from mailing.models import DeliveryState

        message = inbound.import_message(mailbox, build())
        outbound = services.reply(message, body="نعتذر عن التأخير")

        assert outbound.status == DeliveryState.PENDING


@pytest.mark.django_db
class TestFetchGuards:
    def test_an_outbound_only_account_is_never_polled(self, mailbox):
        """
        A mailbox with no inbound direction is never pulled from — and
        connecting to an unconfigured server would have failed and been logged
        as a fault that does not exist.
        """
        mailbox.direction = MailDirection.OUTBOUND
        mailbox.save()

        assert inbound.fetch(mailbox) == 0

    def test_an_account_without_an_imap_host_is_skipped(self, mailbox):
        mailbox.imap_host = ""
        mailbox.save()

        assert inbound.fetch(mailbox) == 0

    def test_one_broken_mailbox_does_not_stop_the_others(self, mailbox, monkeypatch):
        """
        ⚠️  The same rule as `run_periodic`: one mailbox failing does not stop
            the rest, or a defect in a neglected mailbox disables all of support's mail.
        """
        broken = EmailAccount.objects.create(
            code="broken-box",
            label_ar="معطّل",
            label_en="Broken",
            direction=MailDirection.INBOUND,
            from_email="x@example.com",
            imap_host="imap.invalid",
        )
        calls = []

        def fake_fetch(account, **kwargs):
            calls.append(account.code)
            if account.code == "broken-box":
                raise OSError("تعذّر الاتصال")
            return 3

        monkeypatch.setattr(inbound, "fetch", fake_fetch)

        assert inbound.fetch_all() == 3
        assert set(calls) == {"support", "broken-box"}

        broken.refresh_from_db()
        assert broken.consecutive_failures == 1
        assert broken.last_error


@pytest.mark.django_db
class TestPeriodicRegistration:
    def test_the_sweep_reports_zero_when_no_mailbox_is_configured(self, db):
        """No configured mailbox = zero, not an exception: a fresh install with no inbound mail."""
        assert inbound.fetch_all() == 0
