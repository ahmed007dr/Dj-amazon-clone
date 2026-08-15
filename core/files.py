"""
الملفات الحساسة.

⚠️  المسار المباشر ليس حماية.

    ملف تحت `MEDIA_URL` يُقدَّم لأي من يعرف مساره — بلا مصادقة ولا
    فحص ملكية. والمسارات التسلسلية (`media/brand/01.jpg`) تُخمَّن
    بحلقة بسيطة.

    الحماية طبقتان:
      ١. اسم عشوائي بمسار مجزّأ  →  core.identifiers.random_filename
      ٢. رابط موقّع بصلاحية زمنية  →  هذا الملف
"""

from __future__ import annotations

from django.core import signing
from django.core.exceptions import ValidationError

#: صلاحية الرابط — قصيرة عمدًا.
#: الرابط يُشارَك ويُنسخ ويبقى في تاريخ المتصفح؛ قِصَر عمره يحدّ الضرر.
SIGNED_URL_TTL = 300

SALT = "core.files.signed-url"

#: أنواع مسموحة للوثائق — القائمة البيضاء أأمن من السوداء
ALLOWED_DOCUMENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
}

MAX_DOCUMENT_SIZE = 10 * 1024 * 1024  # ١٠ ميجابايت
MAX_IMAGE_SIZE = 5 * 1024 * 1024


def sign_file_access(resource: str, resource_id, user_id) -> str:
    """
    توقيع وصول لملف بعينه لمستخدم بعينه.

    ⚠️  `user_id` جزء من الحمولة الموقّعة — الرابط لا يعمل لغير
        من صدر له. مشاركته لا تمنح الوصول.
    """
    return signing.dumps(
        {"r": resource, "id": str(resource_id), "u": str(user_id)},
        salt=SALT,
    )


def verify_file_access(signature: str, resource: str, user_id) -> str | None:
    """
    يتحقق ويعيد معرّف المورد، أو `None` عند أي فشل.

    الفشل يشمل: توقيعًا مزوّرًا · انتهاء الصلاحية · موردًا مختلفًا ·
    مستخدمًا مختلفًا.
    """
    try:
        payload = signing.loads(signature, salt=SALT, max_age=SIGNED_URL_TTL)
    except signing.BadSignature:
        return None

    if payload.get("r") != resource:
        return None
    if payload.get("u") != str(user_id):
        return None

    return payload.get("id")


#: أنواع صور المنتجات — أضيق من الوثائق: لا PDF على صفحة منتج
ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

#: توقيع الملف (magic bytes) → نوعه الحقيقي.
#
# ⚠️  **`content_type` يأتي من العميل ويمكن تزويره.**
#
#     رفع `shell.php` بترويسة `image/png` يمرّ الفحص السطحي بالكامل.
#     التوقيع يُقرأ من أول بايتات الملف نفسه، ولا يملك الرافع تغييره
#     بلا تغيير الملف فعلًا.
#
#     المفتاح: (الإزاحة، البايتات) — WebP يحتاج فحصين لأن توقيعه
#     مقسوم: `RIFF` ثم `WEBP` بعد أربعة بايتات لحجم الملف.
_MAGIC_SIGNATURES: list[tuple[str, list[tuple[int, bytes]]]] = [
    ("image/jpeg", [(0, b"\xff\xd8\xff")]),
    ("image/png", [(0, b"\x89PNG\r\n\x1a\n")]),
    ("image/webp", [(0, b"RIFF"), (8, b"WEBP")]),
    ("application/pdf", [(0, b"%PDF-")]),
]

#: أطول توقيع نحتاج قراءته
_MAGIC_READ_SIZE = 16


def detect_file_type(uploaded_file) -> str | None:
    """
    النوع الحقيقي من توقيع الملف — أو `None` لغير المعروف.

    ⚠️  المؤشّر يُعاد إلى الصفر بعد القراءة.

        تركه متقدّمًا يجعل Django يخزّن ملفًا ناقص أول ستة عشر
        بايتًا — أي صورة مكسورة تُرفع «بنجاح» ولا تُعرض أبدًا.
    """
    try:
        uploaded_file.seek(0)
        header = uploaded_file.read(_MAGIC_READ_SIZE)
    finally:
        uploaded_file.seek(0)

    for content_type, parts in _MAGIC_SIGNATURES:
        if all(header[offset : offset + len(magic)] == magic for offset, magic in parts):
            return content_type

    return None


def validate_upload(uploaded_file, *, allowed_types=None, max_size=None) -> None:
    """
    فحص الملف المرفوع قبل تخزينه.

    ⚠️  **الفحص على توقيع الملف لا على ترويسته.**

        `content_type` يأتي من العميل ويمكن تزويره بسطر واحد؛
        والقائمة البيضاء المبنية عليه وحدها حماية شكلية. التوقيع
        يُقرأ من الملف نفسه.

    ⚠️  والملف مجهول التوقيع **يُرفض** لا يُقبل بحذر.

        القبول الافتراضي يجعل كل صيغة لم نفكّر فيها بابًا مفتوحًا،
        والقائمة البيضاء تعني أن الجديد يُضاف بقرار لا بسهو.
    """
    allowed_types = allowed_types or ALLOWED_DOCUMENT_TYPES
    max_size = max_size or MAX_DOCUMENT_SIZE

    if uploaded_file.size > max_size:
        raise ValidationError(
            f"حجم الملف يتجاوز الحد المسموح ({max_size // (1024 * 1024)} ميجابايت)"
        )

    # ⚠️  الحجم صفر يمرّ كل فحص محتوى — ويُخزَّن كملف فارغ يبدو سليمًا
    if uploaded_file.size == 0:
        raise ValidationError("الملف فارغ")

    detected = detect_file_type(uploaded_file)

    if detected is None:
        raise ValidationError("تعذّر التعرّف على نوع الملف")

    if detected not in allowed_types:
        raise ValidationError("نوع الملف غير مسموح")

    # ⚠️  التناقض بين الترويسة والتوقيع مؤشّر تزوير لا خطأ عابر —
    #     يُرفض ويُسجَّل بدل أن يُصحَّح بصمت.
    declared = getattr(uploaded_file, "content_type", None)
    if declared and declared not in allowed_types:
        raise ValidationError("نوع الملف غير مسموح")
