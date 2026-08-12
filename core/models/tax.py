"""
الضريبة.  (ADR-30)

قرار عمل مُعتمد: الضريبة مُفعَّلة.

⚠️  النسبة **لقطة تاريخية**.
    كل سطر طلب يخزّن النسبة المطبَّقة وقت البيع.
    لو تغيّرت من 14% إلى 15% العام القادم، تبقى الفواتير القديمة بـ 14%.
    حسابها لاحقًا من نسبة حالية يزوّر السجل المحاسبي.
"""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models.base import BaseModel
from core.models.translatable import BilingualNameMixin
from core.money import RateField


def today():
    """قيمة افتراضية لحقل DateField — `timezone.now` يعيد datetime لا date."""
    return timezone.now().date()


class TaxClass(BilingualNameMixin, BaseModel):
    """
    فئة ضريبية — قياسي · معفى · صفري.

    `valid_from` / `valid_to` تسمحان بتغيير النسبة بقرار حكومي
    مع بقاء السجل التاريخي سليمًا.
    """

    code = models.SlugField(_("الرمز"), max_length=50, unique=True)

    rate = RateField(
        _("النسبة %"),
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )

    is_default = models.BooleanField(_("الافتراضية"), default=False)
    is_active = models.BooleanField(_("مفعّلة"), default=True, db_index=True)

    valid_from = models.DateField(_("سارية من"), default=today)
    valid_to = models.DateField(_("سارية حتى"), null=True, blank=True)

    class Meta:
        verbose_name = _("فئة ضريبية")
        verbose_name_plural = _("الفئات الضريبية")
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=models.Q(is_default=True, deleted_at__isnull=True),
                name="unique_default_tax_class",
            ),
        ]

    def __str__(self):
        return f"{self.name_ar} ({self.rate}%)"

    @property
    def is_currently_valid(self) -> bool:
        today = timezone.now().date()
        if self.valid_from > today:
            return False
        return self.valid_to is None or self.valid_to >= today

    @classmethod
    def get_default(cls) -> "TaxClass | None":
        return cls.objects.filter(is_default=True, is_active=True).first()


# ═══════════════════════════════════════════════════════════
#  إعدادات الضريبة  →  core.SystemSetting
# ═══════════════════════════════════════════════════════════
#
#   tax.enabled                 هل النظام الضريبي مفعّل؟
#   tax.prices_include_tax      هل الأسعار المعروضة شاملة الضريبة؟
#   tax.default_class           رمز الفئة الافتراضية
#   tax.rounding                'line' لكل سطر · 'total' للإجمالي
#   tax.number_required_for     أنواع الحسابات التي يلزمها رقم ضريبي
#
# ═══════════════════════════════════════════════════════════


class TaxSettings:
    """قارئ مركزي لإعدادات الضريبة."""

    ENABLED = "tax.enabled"
    PRICES_INCLUDE_TAX = "tax.prices_include_tax"
    DEFAULT_CLASS = "tax.default_class"
    ROUNDING = "tax.rounding"
    NUMBER_REQUIRED_FOR = "tax.number_required_for"

    @staticmethod
    def is_enabled() -> bool:
        from core.models.settings import SystemSetting

        return bool(SystemSetting.get(TaxSettings.ENABLED, default=True))

    @staticmethod
    def prices_include_tax() -> bool:
        from core.models.settings import SystemSetting

        return bool(SystemSetting.get(TaxSettings.PRICES_INCLUDE_TAX, default=False))

    @staticmethod
    def rounding_mode() -> str:
        from core.models.settings import SystemSetting

        return SystemSetting.get(TaxSettings.ROUNDING, default="line")
