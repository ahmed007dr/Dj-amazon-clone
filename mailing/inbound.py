"""
Inbound mail — pulling incoming mail over IMAP.

⚠️  **The separation of parsing from transport is deliberate.**

    `import_message()` takes the message bytes and produces a row: a pure
    function testable against every real case (an encoded header · a multipart
    body · a forged attachment · an auto-reply). And `fetch()` alone touches the
    network.

    Merging them made parsing coverage impossible without a live IMAP server —
    that is, no coverage at all, while parsing is where all the defects live.

⚠️  **And no extra library**: `imaplib` and `email` are in the standard library.
    Inbound here is one or two mailboxes read every few minutes.
"""

from __future__ import annotations

import hashlib
import imaplib
import logging
from email import message_from_bytes
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from core.files import detect_file_type
from mailing.models import (
    CredentialKey,
    EmailAccount,
    InboundAttachment,
    InboundMessage,
    MailSecurity,
)

logger = logging.getLogger(__name__)

#: The maximum attachment size stored — the message is kept and its oversized attachment dropped
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

#: The accepted attachment types — by signature, not by header (ADR-45)
ALLOWED_ATTACHMENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


def decode(value: str | None) -> str:
    """
    An encoded header ← readable text.

    ⚠️  An Arabic subject arrives like this: `=?UTF-8?B?2YXYsdit2KjYpw==?=`.
        Displaying it raw on the support screen makes the message look corrupt,
        so it gets ignored.
    """
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        # ⚠️  A malformed header does not drop the message — raw text beats nothing
        return value


def is_auto_reply(message) -> bool:
    """
    Is this an automated message?

    ⚠️  **Protection against mail loops.**

        Two auto-replies facing each other generate thousands of messages in
        minutes: "your message was received" is answered by "I am on holiday",
        which is answered by "your message was received"… and the result is the
        domain being blacklisted — which then rebounds onto the order mail and
        every password reset.

        And the check covers four headers, not one: every provider uses a different one.
    """
    auto_submitted = (message.get("Auto-Submitted") or "").strip().lower()
    if auto_submitted and auto_submitted != "no":
        return True

    precedence = (message.get("Precedence") or "").strip().lower()
    if precedence in ("bulk", "list", "junk", "auto_reply"):
        return True

    if message.get("X-Auto-Response-Suppress"):
        return True

    # A mailing list: replying to it goes to every subscriber
    return bool(message.get("List-Id") or message.get("List-Unsubscribe"))


def _part_text(part) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        # ⚠️  An encoding the system does not know: we read as UTF-8 and replace the bad bytes.
        #     Dropping a message because its sender declared an odd encoding is a net loss.
        return payload.decode("utf-8", errors="replace")


def extract_bodies(message) -> tuple[str, str]:
    """(plain text, HTML) — and the text is what gets displayed."""
    if not message.is_multipart():
        text = _part_text(message)
        if message.get_content_type() == "text/html":
            return "", text
        return text, ""

    text_parts, html_parts = [], []

    for part in message.walk():
        if part.get_content_maintype() == "multipart":
            continue
        if part.get_filename():
            continue

        if part.get_content_type() == "text/plain":
            text_parts.append(_part_text(part))
        elif part.get_content_type() == "text/html":
            html_parts.append(_part_text(part))

    return "\n".join(text_parts).strip(), "\n".join(html_parts).strip()


def _received_at(message):
    raw = message.get("Date")
    if not raw:
        return timezone.now()
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return timezone.now()

    if parsed is None:
        return timezone.now()
    # ⚠️  A date with no timezone is treated as server time, not as UTC
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


@transaction.atomic
def import_message(account: EmailAccount, raw: bytes) -> InboundMessage | None:
    """
    Message bytes ← a row in the inbox. **Re-runnable.**

    ⚠️  Duplication is prevented by the `Message-ID` from the message itself.

        The pull happens every few minutes, and any interruption mid-way
        re-covers what was already pulled. Without a stable key one email
        appears ten times in the support inbox and two staff reply to it.

    Returns `None` if the message already exists.
    """
    message = message_from_bytes(raw)

    message_id = (message.get("Message-ID") or "").strip()
    if not message_id:
        # ⚠️  A message with no id: we derive a stable one from its content rather
        #     than generating a random one — a random one makes every pull re-import it.
        message_id = f"<sha:{hashlib.sha256(raw).hexdigest()}>"

    if InboundMessage.objects.filter(account=account, message_id=message_id).exists():
        return None

    from_name, from_email = parseaddr(decode(message.get("From")))
    text, html = extract_bodies(message)

    inbound = InboundMessage.objects.create(
        account=account,
        message_id=message_id[:998],
        in_reply_to=(message.get("In-Reply-To") or "").strip()[:998],
        references=(message.get("References") or "").strip(),
        from_email=from_email[:254],
        from_name=from_name[:255],
        to_email=decode(message.get("To"))[:998],
        subject=decode(message.get("Subject"))[:500],
        body_text=text,
        body_html=html,
        received_at=_received_at(message),
        size_bytes=len(raw),
        is_auto=is_auto_reply(message),
    )

    _store_attachments(inbound, message)
    return inbound


def _store_attachments(inbound: InboundMessage, message) -> int:
    """
    ⚠️  **The most dangerous upload path in the system**: no logged-in user, no
        limit and no known intent — an attacker need only know our mailbox address.

        Hence: signature checking rather than header (ADR-45), an explicit size
        cap, and anything whose signature is unrecognised **is not stored**. And
        the message is kept in both cases: dropping it because of a rejected
        attachment hides a genuine customer complaint.
    """
    stored = 0

    for part in message.walk():
        filename = part.get_filename()
        if not filename:
            continue

        payload = part.get_payload(decode=True)
        if not payload:
            continue

        if len(payload) > MAX_ATTACHMENT_BYTES:
            logger.warning("مرفق تجاوز الحد في الرسالة %s: %s", inbound.pk, filename)
            continue

        blob = ContentFile(payload)
        content_type = detect_file_type(blob)

        if content_type not in ALLOWED_ATTACHMENT_TYPES:
            # ⚠️  The name `invoice.pdf` means nothing — the signature alone decides
            logger.warning(
                "مرفق مرفوض في الرسالة %s: %s (النوع الحقيقي %s)",
                inbound.pk,
                filename,
                content_type,
            )
            continue

        attachment = InboundAttachment(
            message=inbound,
            filename=decode(filename)[:255],
            content_type=content_type,
            size_bytes=len(payload),
        )
        attachment.file.save(decode(filename)[:255], blob, save=False)
        attachment.save()
        stored += 1

    return stored


# ═══════════════════════════════════════════════════════════
#  Transport — the only part that touches the network
# ═══════════════════════════════════════════════════════════


def _connect(account: EmailAccount):
    if account.imap_security == MailSecurity.SSL:
        client = imaplib.IMAP4_SSL(account.imap_host, account.imap_port)
    else:
        client = imaplib.IMAP4(account.imap_host, account.imap_port)
        if account.imap_security == MailSecurity.TLS:
            client.starttls()

    # ⚠️  An IMAP username may differ from the SMTP one; and falling back to it
    #     makes the simple account (the same credentials for both) work with no duplicate entry.
    username = account.imap_username or account.username
    password = account.secret(CredentialKey.IMAP_PASSWORD) or account.password

    client.login(username, password)
    return client


def fetch(account: EmailAccount, *, limit: int = 50) -> int:
    """
    Pull what is new from a single mailbox.

    ⚠️  **`UID`, not message sequence numbers.**

        Sequence numbers in IMAP change with every deletion: message number 7
        becomes 6 when one before it is deleted. And a `UID` is stable for the
        lifetime of the mailbox — without it every pull either re-imports what
        was imported or skips messages.

    ⚠️  And `UID n:*` always returns the last message even when nothing new has
        arrived — behaviour described in the standard. Filtering on `uid > last`
        below is mandatory, not a precaution.
    """
    if not account.receives or not account.imap_host:
        return 0

    client = _connect(account)
    imported = 0

    try:
        client.select(account.imap_folder or "INBOX")
        status, data = client.uid("search", None, f"UID {account.imap_last_uid + 1}:*")

        if status != "OK":
            logger.warning("فشل البحث في صندوق %s: %s", account.code, status)
            return 0

        uids = [int(raw) for raw in (data[0] or b"").split()]
        uids = sorted(uid for uid in uids if uid > account.imap_last_uid)[:limit]

        highest = account.imap_last_uid

        for uid in uids:
            try:
                status, payload = client.uid("fetch", str(uid), "(RFC822)")
                if status != "OK" or not payload or not payload[0]:
                    continue

                if import_message(account, payload[0][1]) is not None:
                    imported += 1
            except Exception:
                # ⚠️  One corrupt message must not stop the whole mailbox —
                #     or a malformed email disables support until somebody notices.
                logger.exception("تعذّر استيراد الرسالة %s من %s", uid, account.code)

            # ⚠️  The cursor advances even past a failed message: without that, every
            #     cycle retries the same corrupt message forever and never reaches
            #     what follows it. The failure is logged, and the mailbox moves on.
            highest = max(highest, uid)

        if highest > account.imap_last_uid:
            EmailAccount.objects.filter(pk=account.pk).update(imap_last_uid=highest)

    finally:
        try:
            client.logout()
        except Exception:
            logger.debug("تعذّر إغلاق اتصال IMAP لـ%s", account.code)

    return imported


def fetch_all(limit: int = 50) -> int:
    """
    The periodic task: every enabled inbound mailbox.

    ⚠️  One mailbox failing does not stop the rest — the same rule as `run_periodic`.
    """
    total = 0

    for account in EmailAccount.objects.filter(is_active=True, direction__in=("IN", "BOTH")):
        try:
            total += fetch(account)
        except Exception as exc:
            logger.exception("فشل سحب البريد من %s", account.code)
            from mailing.services import record_failure

            record_failure(account, str(exc))

    return total
