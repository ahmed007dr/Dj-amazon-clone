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

#: ⚠️  A socket timeout is mandatory. `imaplib` has none by default: a server that accepts the
#:     connection and then says nothing would pin the cron job (or the web worker serving the
#:     "test connection" button) until the operating system gave up, minutes later.
IMAP_TIMEOUT = 20

#: ⚠️  How many consecutive runs may fail on the **same** message before it is skipped.
#:
#:     Retrying a message that failed once is right — a dropped connection, a lock — but
#:     retrying a genuinely unreadable one forever stops every message behind it. So a UID
#:     gets this many runs (the cron fires every five minutes), then is skipped *loudly*:
#:     the skip is written to `imap_last_error`, which the account card shows.
MAX_UID_RETRIES = 5


class MailboxError(Exception):
    """The server answered, but not with what a pull needs (a folder that does not exist…)."""


def describe(exc: BaseException) -> str:
    """
    A readable one-line reason for an exception raised by `imaplib` / `socket`.

    ⚠️  `imaplib` puts its message in `args` as **bytes**, so `str(exc)` prints
        `b'[AUTHENTICATIONFAILED] Invalid credentials'` — which looks like a bug in the screen.
    """
    parts = [
        arg.decode("utf-8", errors="replace") if isinstance(arg, bytes) else str(arg)
        for arg in exc.args
    ]
    text = " ".join(part for part in parts if part).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def _connect(account: EmailAccount):
    if account.imap_security == MailSecurity.SSL:
        client = imaplib.IMAP4_SSL(account.imap_host, account.imap_port, timeout=IMAP_TIMEOUT)
    else:
        client = imaplib.IMAP4(account.imap_host, account.imap_port, timeout=IMAP_TIMEOUT)
        if account.imap_security == MailSecurity.TLS:
            client.starttls()

    # ⚠️  An IMAP username may differ from the SMTP one; and falling back to it
    #     makes the simple account (the same credentials for both) work with no duplicate entry.
    username = account.imap_username or account.username
    password = account.secret(CredentialKey.IMAP_PASSWORD) or account.password

    try:
        client.login(username, password)
    except Exception:
        _close(client)
        raise
    return client


def _close(client) -> None:
    if client is None:
        return
    try:
        client.logout()
    except Exception:
        logger.debug("تعذّر إغلاق اتصال IMAP")


def _quote(folder: str) -> str:
    """
    A mailbox name as an IMAP string.

    ⚠️  `imaplib` sends the name verbatim, so `Sent Items` arrives as two arguments and the
        server answers `BAD`. Quoting always is harmless for `INBOX` too.
    """
    return '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _uidvalidity(client) -> int:
    try:
        _code, data = client.response("UIDVALIDITY")
        raw = data[0] if data else None
        return int(raw) if raw else 0
    except (TypeError, ValueError):
        return 0


def _open_folder(client, account: EmailAccount) -> tuple[str, int, int]:
    """
    Select the folder **read-only**: `(folder, message count, UIDVALIDITY)`.

    ⚠️  The status is checked. `imaplib` returns `("NO", …)` for a folder that does not
        exist instead of raising, so a mistyped name used to look exactly like an empty
        mailbox — zero messages, no error, forever.

    ⚠️  Read-only, and `BODY.PEEK` below: the pull must not flip the "unread" flag on the
        messages a human is also reading in webmail.
    """
    folder = account.imap_folder or "INBOX"
    status, data = client.select(_quote(folder), readonly=True)

    if status != "OK":
        detail = ""
        if data and data[0]:
            first = data[0]
            detail = first.decode("utf-8", errors="replace") if isinstance(first, bytes) else first
        raise MailboxError(f"تعذّر فتح المجلد «{folder}» — {detail or status}")

    try:
        exists = int(data[0]) if data and data[0] else 0
    except (TypeError, ValueError):
        exists = 0

    return folder, exists, _uidvalidity(client)


def _search_uids(client, criterion: str) -> list[int]:
    status, data = client.uid("search", None, criterion)
    if status != "OK":
        raise MailboxError(f"فشل البحث في الصندوق ({criterion}): {status}")
    return sorted(int(raw) for raw in ((data[0] if data else b"") or b"").split())


def _fetch_raw(client, uid: int) -> bytes | None:
    """
    The message bytes, or `None` if the message is gone.

    ⚠️  The two non-success answers mean different things:

        status != OK        →  the server refused: **transient**, raise, retry next run
        OK with no payload  →  the message was expunged between the SEARCH and the FETCH:
                                nothing will ever arrive for this UID, so it is not a failure
    """
    status, payload = client.uid("fetch", str(uid), "(BODY.PEEK[])")
    if status != "OK":
        raise MailboxError(f"رفض الخادم جلب الرسالة {uid}: {status}")

    for item in payload or []:
        if isinstance(item, tuple) and len(item) >= 2 and item[1]:
            return item[1]
    return None


def fingerprint(account: EmailAccount) -> str:
    """
    Identifies *which mailbox* the cursor belongs to: host, login and folder.

    ⚠️  Not the password and not the port. A rotated password is still the same mailbox, and
        143 → 993 is the same mailbox over a different door; resetting on either would only
        re-baseline harmlessly, but there is no reason to.
    """
    material = "|".join(
        [
            (account.imap_host or "").strip().lower(),
            (account.imap_username or account.username or "").strip().lower(),
            account.imap_folder or "INBOX",
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _save(account: EmailAccount, changes: dict) -> None:
    """Write straight to the row (no `save()` — no signals, no `updated_at` race) and mirror it."""
    if not changes:
        return
    EmailAccount.objects.filter(pk=account.pk).update(**changes)
    for name, value in changes.items():
        setattr(account, name, value)


def _baseline_reason(account: EmailAccount, current: str, validity: int) -> str:
    """
    Why the stored cursor cannot be trusted — or `""` if it can.

    ⚠️  Three situations, one remedy (start again from the newest messages):

        - the account was pointed at another mailbox (host / login / folder changed): the
          cursor counts that mailbox's UIDs, not this one's;
        - the server reports a different `UIDVALIDITY`: the UID space was renumbered, so
          "everything above 4,200" now means something else entirely — new mail can sit
          *below* the cursor and never be fetched;
        - there is no cursor at all (the first pull).

        A legacy account (cursor > 0, nothing recorded) is **adopted**, not reset: the
        fingerprint is simply stored from now on.
    """
    if account.imap_fingerprint and account.imap_fingerprint != current:
        return "تغيّرت بيانات الاتصال بالصندوق (الخادم/المستخدم/المجلد)"

    if account.imap_uidvalidity and validity and account.imap_uidvalidity != validity:
        return "غيّر الخادم UIDVALIDITY — أُعيد ترقيم الصندوق"

    if account.imap_last_uid == 0 and not account.imap_fingerprint:
        return "أول سحب لهذا الصندوق"

    return ""


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

    ⚠️  **The cursor moves only past a message that is dealt with.**

        It used to advance past a failed message "so one corrupt email cannot block the
        mailbox" — which also meant a *transient* failure (a dropped connection on message 41)
        followed by a success on message 42 moved the cursor beyond 41 for good: a customer's
        email lost with nothing to show for it. Now a failure **stops the run** at that UID and
        the next run retries it; only after `MAX_UID_RETRIES` failed runs is it skipped, and
        that skip is reported on the account.

    ⚠️  **The first pull starts from the newest `limit` messages, not the oldest.**

        A mailbox that has existed for years holds thousands of messages; pulling oldest-first
        in batches of 50 buries the one reply a customer sent today under a backlog nobody
        will ever read, for hours. The older history is skipped on purpose (it is still in
        the mailbox); every later run continues oldest-first from the cursor, so nothing
        that arrives *after* the baseline can be missed. The same baseline is taken again
        when the connection fields or the server's `UIDVALIDITY` change (`_baseline_reason`).
    """
    if not account.receives or not account.imap_host:
        return 0

    changes: dict = {}
    client = None
    imported = 0
    problem = ""

    try:
        client = _connect(account)
        _folder, _exists, validity = _open_folder(client, account)
        current = fingerprint(account)

        cursor = account.imap_last_uid
        retry_uid = account.imap_retry_uid
        retry_count = account.imap_retry_count

        reason = _baseline_reason(account, current, validity)

        if reason:
            logger.warning("إعادة تحديد مؤشر سحب %s: %s", account.code, reason)
            newest = _search_uids(client, "ALL")[-limit:]
            cursor = newest[0] - 1 if newest else 0
            retry_uid = retry_count = 0
            uids = newest
        else:
            found = _search_uids(client, f"UID {cursor + 1}:*")
            uids = [uid for uid in found if uid > cursor][:limit]

        # What we now know about this mailbox is recorded straight away, so even a run that
        # fails on its first message leaves the account with a valid baseline.
        changes.update(imap_fingerprint=current, imap_last_uid=cursor)
        if validity:
            changes["imap_uidvalidity"] = validity

        for uid in uids:
            try:
                raw = _fetch_raw(client, uid)
                if raw is not None and import_message(account, raw) is not None:
                    imported += 1
            except Exception as exc:
                logger.exception("تعذّر استيراد الرسالة %s من %s", uid, account.code)

                retry_count = retry_count + 1 if retry_uid == uid else 1
                retry_uid = uid
                problem = f"UID {uid}: {describe(exc)}"

                if retry_count < MAX_UID_RETRIES:
                    break  # keep the cursor behind it — the next run retries this message

                problem = f"تُخطّيت الرسالة UID {uid} بعد {retry_count} محاولات — {problem}"
                cursor, retry_uid, retry_count = uid, 0, 0
                continue

            cursor = uid
            if retry_uid == uid:
                retry_uid = retry_count = 0

        changes.update(imap_last_uid=cursor, imap_retry_uid=retry_uid, imap_retry_count=retry_count)

        now = timezone.now()
        changes["imap_last_fetch_at"] = now
        changes["imap_last_error"] = problem
        if problem:
            changes["imap_last_error_at"] = now

    except Exception as exc:
        changes["imap_last_error"] = describe(exc)[:2000]
        changes["imap_last_error_at"] = timezone.now()
        raise

    finally:
        _close(client)
        _save(account, changes)

    return imported


def check_connection(account: EmailAccount) -> dict:
    """
    "Test connection" for the **inbound** side: log in, open the folder, count.

    ⚠️  Distinct from `services.verify`, which does an SMTP handshake. An inbound-only
        account has no SMTP at all, and a BOTH account can have a perfectly working SMTP
        and a broken IMAP — a green "verified" next to a mailbox nobody can read is exactly
        how this went unnoticed.

        It changes nothing in the mailbox and does not move the cursor; it only
        reports, and records a failure (or clears one) on the account card.
    """
    result = {
        "ok": False,
        "error": "",
        "folder": account.imap_folder or "INBOX",
        "messages": 0,
        "last_uid": 0,
        "uidvalidity": 0,
        "cursor": account.imap_last_uid,
        "pending": 0,
    }

    if not account.imap_host:
        result["error"] = "خادم IMAP غير مضبوط"
        return result

    client = None
    try:
        client = _connect(account)
        folder, exists, validity = _open_folder(client, account)
        uids = _search_uids(client, "ALL")
    except Exception as exc:
        result["error"] = describe(exc)
        _save(
            account,
            {"imap_last_error": result["error"][:2000], "imap_last_error_at": timezone.now()},
        )
        return result
    finally:
        _close(client)

    result.update(
        ok=True,
        folder=folder,
        messages=exists,
        last_uid=uids[-1] if uids else 0,
        uidvalidity=validity,
        pending=sum(1 for uid in uids if uid > account.imap_last_uid),
    )
    _save(account, {"imap_last_error": ""})
    return result


def fetch_all(limit: int = 50) -> int:
    """
    The periodic task: every enabled inbound mailbox.

    ⚠️  One mailbox failing does not stop the rest — the same rule as `run_periodic`.
    """
    total = 0

    for account in EmailAccount.objects.filter(is_active=True, direction__in=("IN", "BOTH")):
        try:
            total += fetch(account, limit=limit)
        except Exception as exc:
            logger.exception("فشل سحب البريد من %s", account.code)
            from mailing.services import record_failure

            record_failure(account, describe(exc))

    return total
