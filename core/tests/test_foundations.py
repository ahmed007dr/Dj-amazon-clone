"""
اختبارات الأساس.

تثبّت أن القرارات المعمارية مطبَّقة فعلًا في الكود، لا في الوثائق فقط.
"""

from decimal import Decimal

import pytest
from django.apps import apps
from django.db import models

from core.identifiers import (
    CROCKFORD_ALPHABET,
    business_number,
    hash_token,
    random_code,
    random_filename,
    secure_token,
    verify_token,
)
from core.money import ZERO, apply_rate, percentage_of, quantize, to_string

# ═══════════════════════════════════════════════════════════
#  المال —  ADR-31
# ═══════════════════════════════════════════════════════════


class TestMoney:
    def test_no_float_fields_anywhere(self):
        """
        ⛔ الخطأ الأخطر في النموذج القديم: FloatField للمال في ٩ مواضع.

        مع عمولات ومرتجعات وضرائب، فروق الفاصلة العائمة تتراكم
        حتى تكسر أي مطابقة محاسبية.
        """
        offenders = []
        for model in apps.get_models():
            if model._meta.app_label in ("auth", "admin", "contenttypes", "sessions"):
                continue
            for field in model._meta.get_fields():
                if isinstance(field, models.FloatField):
                    offenders.append(f"{model._meta.label}.{field.name}")

        assert not offenders, f"FloatField ممنوع — وُجد في: {offenders}"

    def test_rounding_is_half_up_not_half_even(self):
        """ROUND_HALF_UP هو السلوك التجاري المتوقع، لا افتراضي بايثون."""
        assert quantize(Decimal("0.125")) == Decimal("0.13")
        assert quantize(Decimal("0.135")) == Decimal("0.14")

    def test_tax_calculation(self):
        assert apply_rate(Decimal("450.00"), Decimal("14.00")) == Decimal("63.00")
        assert apply_rate(Decimal("100.00"), Decimal("0.00")) == ZERO

    def test_percentage_of_handles_zero_division(self):
        assert percentage_of(Decimal("50"), Decimal("0")) == ZERO
        assert percentage_of(Decimal("50"), Decimal("200")) == Decimal("25.00")

    def test_money_serialises_as_string(self):
        """JSON.parse يحوّل الأرقام إلى double فتُفقد الدقة."""
        assert to_string(Decimal("450.00")) == "450.00"
        assert to_string(Decimal("450")) == "450.00"
        assert isinstance(to_string(Decimal("0.1")), str)


# ═══════════════════════════════════════════════════════════
#  المعرّفات —  ADR-25 · ADR-26 · ADR-29
# ═══════════════════════════════════════════════════════════

#: نماذج داخلية عالية الحجم — لا تظهر في رابط أبدًا فتبقى BigInt (ADR-28)
INTERNAL_BIGINT_MODELS = {
    ("core", "AuditLog"),
    ("accounts", "UserSession"),
    ("accounts", "AccountStatusChange"),
    ("accounts", "SecurityToken"),
}

#: نماذج بمفتاح طبيعي — المفتاح نفسه هو المعنى، لا رقم تسلسلي.
#: `tax.enabled` معرّف مقصود ومقروء، ولا يكشف حجم نشاط.
NATURAL_KEY_MODELS = {
    ("core", "SystemSetting"),
}


class TestIdentifiers:
    """
    فحوص معمارية عبر سجل التطبيقات — بمراجع نصية لا استيراد.

    استيراد نطاق عمل هنا يكسر حدود `core`، وقد التقطه import-linter
    فعلًا عند أول محاولة. `apps.get_model` بحث نصي فلا ينشئ تبعية.
    """

    def test_exposed_models_use_uuid_pk(self):
        """كل نموذج يظهر في رابط أو استجابة يحمل UUIDv7. (ADR-25)"""
        offenders = []
        for model in apps.get_models():
            label = model._meta.app_label
            if label in ("auth", "admin", "contenttypes", "sessions", "token_blacklist"):
                continue
            key = (label, model.__name__)
            if key in INTERNAL_BIGINT_MODELS or key in NATURAL_KEY_MODELS:
                continue
            if not isinstance(model._meta.pk, models.UUIDField):
                offenders.append(model._meta.label)

        assert not offenders, f"نماذج مكشوفة بلا UUID: {offenders}"

    def test_internal_high_volume_tables_stay_bigint(self):
        """UUID على جدول لا يظهر في رابط تكلفة بلا مقابل."""
        for app_label, model_name in INTERNAL_BIGINT_MODELS:
            model = apps.get_model(app_label, model_name)
            assert isinstance(model._meta.pk, models.BigAutoField), (
                f"{model._meta.label} يجب أن يبقى BigInt"
            )

    def test_uuid7_is_time_ordered(self):
        """
        v7 مرتّب زمنيًا فيحافظ على موضعية فهرس B-tree،
        بخلاف v4 العشوائي بالكامل. (ADR-26)
        """
        from core.models.base import uuid7

        ids = [str(uuid7()) for _ in range(50)]
        assert ids == sorted(ids)

    def test_business_number_is_not_sequential(self):
        numbers = {business_number("ORD") for _ in range(100)}
        assert len(numbers) == 100

        sample = business_number("ORD")
        prefix, year, code = sample.split("-")
        assert prefix == "ORD"
        assert len(year) == 4
        assert len(code) == 6

    def test_crockford_alphabet_excludes_ambiguous_letters(self):
        """I L O U تُربك النطق والكتابة اليدوية."""
        for ch in "ILOU":
            assert ch not in CROCKFORD_ALPHABET

    def test_random_filename_is_not_enumerable(self):
        """المسارات الحالية media/brand/01.jpg قابلة للتعداد."""
        name = random_filename("photo.JPG")
        assert name.endswith(".jpg")
        assert name.count("/") == 2
        assert len({random_filename("a.png") for _ in range(100)}) == 100


# ═══════════════════════════════════════════════════════════
#  الرموز الأمنية
# ═══════════════════════════════════════════════════════════


class TestSecurityTokens:
    def test_generator_is_cryptographically_secure(self):
        """
        ⛔ الأصل كان يستخدم `random` (Mersenne Twister) لتوليد
           كود تفعيل الحساب — قابل للتنبؤ.
        """
        import inspect

        from core import identifiers

        source = inspect.getsource(identifiers)
        assert "import secrets" in source
        assert "import random" not in source

    def test_token_verification(self):
        token = secure_token()
        digest = hash_token(token)

        assert verify_token(token, digest)
        assert not verify_token("wrong-token", digest)
        assert token not in digest  # الرمز الصريح لا يظهر في البصمة

    def test_codes_are_unique(self):
        assert len({random_code(8) for _ in range(500)}) == 500


# ═══════════════════════════════════════════════════════════
#  سجل التدقيق
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAuditLog:
    def test_audit_log_is_append_only(self):
        from core.models import AuditAction, AuditLog

        entry = AuditLog.objects.create(action=AuditAction.CREATE, object_repr="اختبار")
        entry.object_repr = "محاولة تعديل"

        with pytest.raises(ValueError, match="للإضافة فقط"):
            entry.save()


# ═══════════════════════════════════════════════════════════
#  الضريبة —  ADR-30
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestTax:
    def test_tax_class_tracks_validity_period(self):
        """النِّسب تتغيّر بقرار حكومي — التاريخي يجب أن يبقى سليمًا."""
        from datetime import date, timedelta

        from core.models import TaxClass

        tax = TaxClass.objects.create(
            name_ar="قياسي",
            name_en="Standard",
            code="standard",
            rate=Decimal("14.00"),
            is_default=True,
        )
        assert tax.is_currently_valid

        tax.valid_to = date.today() - timedelta(days=1)
        tax.save()
        assert not tax.is_currently_valid

    def test_only_one_default_tax_class(self):
        from django.db.utils import IntegrityError

        from core.models import TaxClass

        TaxClass.objects.create(
            name_ar="قياسي",
            name_en="Standard",
            code="standard",
            rate=Decimal("14.00"),
            is_default=True,
        )
        with pytest.raises(IntegrityError):
            TaxClass.objects.create(
                name_ar="مخفّض",
                name_en="Reduced",
                code="reduced",
                rate=Decimal("5.00"),
                is_default=True,
            )


# ═══════════════════════════════════════════════════════════
#  الحذف الناعم
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSoftDelete:
    def test_soft_delete_hides_but_keeps(self):
        """لا يُحذف منتج بِيع فعلًا — الطلبات التاريخية تشير إليه."""
        from core.models import TaxClass

        tax = TaxClass.objects.create(
            name_ar="مؤقت", name_en="Temp", code="temp", rate=Decimal("0.00")
        )
        pk = tax.pk

        tax.delete()

        assert not TaxClass.objects.filter(pk=pk).exists()
        assert TaxClass.all_objects.filter(pk=pk).exists()
        assert TaxClass.all_objects.get(pk=pk).is_deleted

    def test_restore(self):
        from core.models import TaxClass

        tax = TaxClass.objects.create(
            name_ar="مؤقت", name_en="Temp", code="temp2", rate=Decimal("0.00")
        )
        tax.delete()
        TaxClass.all_objects.get(pk=tax.pk).restore()

        assert TaxClass.objects.filter(pk=tax.pk).exists()
