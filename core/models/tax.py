"""
Tax.  (ADR-30)

An approved business decision: tax is enabled.

⚠️  The rate is **a historical snapshot**.
    Every order line stores the rate applied at the time of sale.
    If it changes from 14% to 15% next year, old invoices stay at 14%.
    Computing it later from the current rate falsifies the accounting record.
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
    """
    A default value for a `DateField`.

    ⚠️  `timezone.localdate()`, not `timezone.now().date()`.

        The latter gives the **UTC** date. With `TIME_ZONE='Africa/Cairo'` it is
        12:30am in Cairo while UTC is still on the previous day — so a tax rate
        is applied a day early or stays in force a day too long.
    """
    return timezone.localdate()


class TaxClass(BilingualNameMixin, BaseModel):
    """
    A tax class — standard · exempt · zero-rated.

    `valid_from` / `valid_to` allow the rate to change by government decree
    while the historical record stays intact.
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
        # The local date, not UTC — see `today()` above
        today = timezone.localdate()
        if self.valid_from > today:
            return False
        return self.valid_to is None or self.valid_to >= today

    @classmethod
    def get_default(cls) -> "TaxClass | None":
        return cls.objects.filter(is_default=True, is_active=True).first()


# ═══════════════════════════════════════════════════════════
#  Tax settings  →  core.SystemSetting
# ═══════════════════════════════════════════════════════════
#
#   tax.enabled                 is the tax system enabled?
#   tax.prices_include_tax      are displayed prices tax-inclusive?
#   tax.default_class           the default class code
#   tax.rounding                'line' per line · 'total' on the total
#   tax.number_required_for     the account types that require a tax number
#
# ═══════════════════════════════════════════════════════════


class TaxSettings:
    """A central reader for the tax settings."""

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
