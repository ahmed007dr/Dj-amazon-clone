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


def validate_upload(uploaded_file, *, allowed_types=None, max_size=None) -> None:
    """
    فحص الملف المرفوع قبل تخزينه.

    ⚠️  `content_type` يأتي من العميل ويمكن تزويره — فهو فحص أولي
        لا نهائي. الفحص العميق بقراءة توقيع الملف (magic bytes)
        يُضاف مع رفع صور المنتجات في المرحلة ٣.
    """
    allowed_types = allowed_types or ALLOWED_DOCUMENT_TYPES
    max_size = max_size or MAX_DOCUMENT_SIZE

    if uploaded_file.size > max_size:
        raise ValidationError(
            f"حجم الملف يتجاوز الحد المسموح ({max_size // (1024 * 1024)} ميجابايت)"
        )

    content_type = getattr(uploaded_file, "content_type", None)
    if content_type and content_type not in allowed_types:
        raise ValidationError("نوع الملف غير مسموح")
