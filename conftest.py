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
