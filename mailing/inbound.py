"""
الاستقبال — سحب البريد الوارد عبر IMAP.

⚠️  **الفصل بين التحليل والنقل مقصود.**

    `import_message()` تأخذ بايتات الرسالة وتُنتج صفًّا: دالة خالصة
    قابلة للاختبار بكل حالة حقيقية (ترويسة مرمَّزة · جسم متعدد
    الأجزاء · مرفق مزوّر · ردّ آلي). و`fetch()` وحدها تلمس الشبكة.

    الدمج كان يجعل تغطية التحليل مستحيلة بلا خادم IMAP حيّ — أي بلا
    تغطية، بينما التحليل هو موضع كل الأخطاء.

⚠️  **ولا مكتبة إضافية**: `imaplib` و`email` في المكتبة القياسية.
    الاستقبال هنا صندوق واحد أو اثنان تُقرأ كل بضع دقائق.
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

#: أقصى حجم مرفق يُخزَّن — الرسالة تُحفَظ ومرفقها الضخم يُهمَل
MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024

#: أنواع المرفقات المقبولة — بتوقيعها لا بترويستها (ADR-45)
ALLOWED_ATTACHMENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


def decode(value: str | None) -> str:
    """
    ترويسة مرمَّزة ← نص مقروء.

    ⚠️  الموضوع العربي يصل هكذا: `=?UTF-8?B?2YXYsdit2KjYpw==?=`.
        عرضه خامًا في شاشة الدعم يجعل الرسالة تبدو تالفة فتُتجاهَل.
    """
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        # ⚠️  ترويسة مشوّهة لا تُسقط الرسالة — النص الخام أفضل من لا شيء
        return value


def is_auto_reply(message) -> bool:
    """
    هل هذه رسالة آلية؟

    ⚠️  **حماية من حلقات البريد.**

        ردّان آليان متقابلان يولّدان آلاف الرسائل في دقائق: «رسالتك
        وصلت» يردّ عليها «أنا في إجازة» فيردّ عليها «رسالتك وصلت»…
        والنتيجة إدراج الدومين في القوائم السوداء — ثم يعود الأثر
        على بريد الطلبات وإعادة تعيين كلمات المرور كلها.

        والفحص على أربع ترويسات لا واحدة: كل مزوّد يستعمل غيرها.
    """
    auto_submitted = (message.get("Auto-Submitted") or "").strip().lower()
    if auto_submitted and auto_submitted != "no":
        return True

    precedence = (message.get("Precedence") or "").strip().lower()
    if precedence in ("bulk", "list", "junk", "auto_reply"):
        return True

    if message.get("X-Auto-Response-Suppress"):
        return True

    # قائمة بريدية: الردّ عليها يذهب إلى كل المشتركين
    return bool(message.get("List-Id") or message.get("List-Unsubscribe"))


def _part_text(part) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        # ⚠️  ترميز غير معروف للنظام: نقرأ بـ UTF-8 ونستبدل التالف.
        #     إسقاط الرسالة لأن مرسلها أعلن ترميزًا غريبًا خسارة صافية.
        return payload.decode("utf-8", errors="replace")


def extract_bodies(message) -> tuple[str, str]:
    """(نص صريح، HTML) — والنص هو ما يُعرَض."""
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
    # ⚠️  تاريخ بلا منطقة زمنية يُعامَل كتوقيت الخادم لا كـ UTC
    return parsed if timezone.is_aware(parsed) else timezone.make_aware(parsed)


@transaction.atomic
def import_message(account: EmailAccount, raw: bytes) -> InboundMessage | None:
    """
    بايتات رسالة ← صفّ في الوارد. **قابلة لإعادة التشغيل.**

    ⚠️  الازدواج يُمنَع بـ`Message-ID` من الرسالة نفسها.

        السحب يقع كل بضع دقائق، وأي انقطاع في منتصفه يعيد المرور على
        ما سُحب. وبلا مفتاح ثابت يظهر البريد الواحد عشر مرات في صندوق
        الدعم فيردّ عليه موظفان.

    تعيد `None` إن كانت الرسالة موجودة سلفًا.
    """
    message = message_from_bytes(raw)

    message_id = (message.get("Message-ID") or "").strip()
    if not message_id:
        # ⚠️  رسالة بلا معرّف: نشتقّ واحدًا ثابتًا من محتواها بدل
        #     توليد عشوائي — العشوائي يجعل كل سحب يستوردها من جديد.
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
    ⚠️  **أخطر مسار رفع في النظام**: بلا مستخدم مسجَّل ولا حدّ ولا نيّة
        معلومة — يكفي أن يعرف المهاجم عنوان صندوقنا.

        ولذلك: فحص التوقيع لا الترويسة (ADR-45)، وسقف حجم صريح، وما
        لا يُعرف توقيعه **لا يُخزَّن**. والرسالة تبقى في الحالتين:
        إسقاطها بسبب مرفق مرفوض يخفي شكوى عميل حقيقية.
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
            # ⚠️  الاسم `فاتورة.pdf` لا يعني شيئًا — التوقيع وحده يحكم
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
#  النقل — الجزء الوحيد الذي يلمس الشبكة
# ═══════════════════════════════════════════════════════════


def _connect(account: EmailAccount):
    if account.imap_security == MailSecurity.SSL:
        client = imaplib.IMAP4_SSL(account.imap_host, account.imap_port)
    else:
        client = imaplib.IMAP4(account.imap_host, account.imap_port)
        if account.imap_security == MailSecurity.TLS:
            client.starttls()

    # ⚠️  اسم مستخدم IMAP قد يخالف اسم SMTP؛ والسقوط إليه يجعل
    #     الحساب البسيط (نفس البيانات للطرفين) يعمل بلا تكرار إدخال.
    username = account.imap_username or account.username
    password = account.secret(CredentialKey.IMAP_PASSWORD) or account.password

    client.login(username, password)
    return client


def fetch(account: EmailAccount, *, limit: int = 50) -> int:
    """
    سحب الجديد من صندوق واحد.

    ⚠️  **`UID` لا ترتيب الرسائل.**

        أرقام التسلسل في IMAP تتغيّر مع كل حذف: الرسالة رقم ٧ تصير
        ٦ حين تُحذف واحدة قبلها. و`UID` ثابت مدى عمر الصندوق —
        وبدونه يعيد كل سحب استيراد ما استُورد أو يقفز فوق رسائل.

    ⚠️  و`UID n:*` تعيد آخر رسالة دائمًا حتى لو لم يصل جديد — سلوك
        موصوف في المعيار. الترشيح على `uid > last` أدناه إلزامي، لا
        احتياط.
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
                # ⚠️  رسالة واحدة تالفة يجب ألا توقف الصندوق كله —
                #     وإلا عطّل بريدٌ مشوّه الدعمَ إلى أن يلاحظ أحد.
                logger.exception("تعذّر استيراد الرسالة %s من %s", uid, account.code)

            # ⚠️  المؤشّر يتقدّم حتى على الفاشلة: بلا ذلك تعيد كل دورة
            #     محاولة نفس الرسالة التالفة إلى الأبد ولا تصل إلى ما
            #     بعدها. الفشل مسجَّل، والصندوق يتقدّم.
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
    المهمة الدورية: كل صناديق الاستقبال المفعّلة.

    ⚠️  فشل صندوق لا يوقف البقية — نفس قاعدة `run_periodic`.
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
