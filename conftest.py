"""
إعدادات pytest المشتركة.
"""

import shutil
import tempfile

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True, scope="session")
def fast_password_hashing():
    """
    ⚠️  تجزئة كلمات المرور تهيمن على زمن أي اختبار يُنشئ مستخدمين.

        PBKDF2 مُعايَر ليكون **بطيئًا عمدًا** — وهو صحيح في الإنتاج
        وعبء خالص في الاختبار. بذرة التطوير وحدها تُنشئ ١٧ حسابًا،
        فتقضي معظم وقتها في التجزئة لا فيما تختبره.

        هذا لا يخلق فجوة سلوكية: `check_password` تعمل كما هي،
        ومدققات قوة كلمة المرور تبقى كاملة كما في الإنتاج.
    """
    from django.conf import settings

    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def isolated_media(settings):
    """
    ⚠️  الملفات المرفوعة أثناء الاختبار تُكتب في `MEDIA_ROOT` الحقيقي
        وتتراكم هناك إلى الأبد.

    تحويلها إلى مجلد مؤقت يُحذف بعد كل اختبار يمنع التلوث، ويضمن
    أن اختبارًا لا يرى ملفات اختبار آخر.
    """
    temp_dir = tempfile.mkdtemp(prefix="test-media-")
    settings.MEDIA_ROOT = temp_dir
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════
#  ملفات اختبار حقيقية التوقيع
# ═══════════════════════════════════════════════════════════
#
# ⚠️  `b"fake-pdf"` لم يعد يمرّ — وهذا مقصود.
#
#     `validate_upload` تقرأ توقيع الملف لا ترويسته، لأن الترويسة
#     يزوّرها الرافع بسطر واحد. فبايتات وهمية بترويسة `application/pdf`
#     هي بالضبط الهجوم الذي نصدّه، ولا يصح أن تمرّ في اختبار.
#
#     البدائل هنا أصغر ملف صالح من كل نوع: توقيع حقيقي في أوله،
#     وحشو بعده. تكفي للفحص ولا تحمل حجمًا.

PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + b"0" * 64
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"0" * 64
#: الحجم في البايتات ٤–٧ جزء من التوقيع الحقيقي لكنه لا يُفحَص
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 64


def upload(name: str, content: bytes, content_type: str):
    """ملف مرفوع صالح التوقيع لاختبارات الرفع."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, content, content_type=content_type)


def pdf_upload(name: str = "document.pdf"):
    return upload(name, PDF_BYTES, "application/pdf")


def real_png_bytes(size=(8, 8)) -> bytes:
    """
    صورة PNG صالحة فعلًا — لا توقيعًا فقط.

    ⚠️  `ImageField` يفكّ الصورة بـ Pillow بعد فحص التوقيع.

        بايتات تبدأ بتوقيع PNG وتنتهي بحشو تمرّ `validate_upload`
        ثم يرفضها Pillow — فيفشل الاختبار في طبقة غير التي يقصدها.
    """
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def png_upload(name: str = "image.png"):
    return upload(name, real_png_bytes(), "image/png")


@pytest.fixture(autouse=True)
def clear_cache():
    """
    الكاش يعبر حدود الاختبارات.

    مجموعة الحسابات الموقوفة ومفاتيح تحديد المعدل تبقى بين
    الاختبارات فتُسقط اختبارات لاحقة لأسباب غير مفهومة.
    """
    cache.clear()
    yield
    cache.clear()
