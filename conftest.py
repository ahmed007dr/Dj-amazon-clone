"""
إعدادات pytest المشتركة.
"""

import shutil
import tempfile

import pytest
from django.core.cache import cache


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
