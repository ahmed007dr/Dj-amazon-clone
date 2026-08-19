"""
Money.

⚠️  `float` is forbidden in any financial calculation. `Decimal` exclusively.
    The existing defect in the legacy model: FloatField in 9 places.

With commissions, returns and taxes, floating-point discrepancies accumulate
until they break any accounting reconciliation.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

# ═══════════════════════════════════════════════════════════
#  Constants
# ═══════════════════════════════════════════════════════════

MONEY_MAX_DIGITS = 12  # up to 9,999,999,999.99
MONEY_DECIMAL_PLACES = 2

RATE_MAX_DIGITS = 5  # up to 999.99 %
RATE_DECIMAL_PLACES = 2

ZERO = Decimal("0.00")


# ═══════════════════════════════════════════════════════════
#  Fields
# ═══════════════════════════════════════════════════════════


def MoneyField(verbose_name=None, **kwargs):  # noqa: N802
    """A monetary amount field."""
    kwargs.setdefault("max_digits", MONEY_MAX_DIGITS)
    kwargs.setdefault("decimal_places", MONEY_DECIMAL_PLACES)
    return models.DecimalField(verbose_name, **kwargs)


def RateField(verbose_name=None, **kwargs):  # noqa: N802
    """A percentage field — tax · discount · commission."""
    kwargs.setdefault("max_digits", RATE_MAX_DIGITS)
    kwargs.setdefault("decimal_places", RATE_DECIMAL_PLACES)
    return models.DecimalField(verbose_name, **kwargs)


# ═══════════════════════════════════════════════════════════
#  Operations
# ═══════════════════════════════════════════════════════════


def quantize(amount: Decimal) -> Decimal:
    """
    Round to the currency's precision.

    ROUND_HALF_UP is the commercially expected behaviour (0.125 → 0.13), unlike
    Python's ROUND_HALF_EVEN default (0.125 → 0.12).
    """
    exponent = Decimal(1).scaleb(-MONEY_DECIMAL_PLACES)
    return Decimal(amount).quantize(exponent, rounding=ROUND_HALF_UP)


def apply_rate(amount: Decimal, rate: Decimal) -> Decimal:
    """
    Apply a percentage rate.

        apply_rate(Decimal('100.00'), Decimal('14.00'))  →  Decimal('14.00')
    """
    return quantize(Decimal(amount) * Decimal(rate) / Decimal("100"))


def percentage_of(part: Decimal, whole: Decimal) -> Decimal:
    """The part as a percentage of the whole. Returns zero on division by zero."""
    whole = Decimal(whole)
    if whole == 0:
        return ZERO
    exponent = Decimal(1).scaleb(-RATE_DECIMAL_PLACES)
    return (Decimal(part) / whole * Decimal("100")).quantize(exponent, rounding=ROUND_HALF_UP)


def to_string(amount: Decimal) -> str:
    """
    The JSON representation — **a string, not a number**.

    JavaScript's JSON.parse converts numbers to double, so precision is lost:
    450.00 becomes 450, and 0.1+0.2 becomes 0.30000000000000004.
    A string crosses undistorted. (ADR-31)
    """
    return str(quantize(amount))


def get_currency() -> str:
    return getattr(settings, "DEFAULT_CURRENCY", "EGP")


# ═══════════════════════════════════════════════════════════
#  Currencies
# ═══════════════════════════════════════════════════════════


class Currency(models.TextChoices):
    EGP = "EGP", _("جنيه مصري")
    USD = "USD", _("دولار أمريكي")
    EUR = "EUR", _("يورو")
    SAR = "SAR", _("ريال سعودي")
    AED = "AED", _("درهم إماراتي")


def CurrencyField(verbose_name=None, **kwargs):  # noqa: N802
    kwargs.setdefault("max_length", 3)
    kwargs.setdefault("choices", Currency.choices)
    kwargs.setdefault("default", Currency.EGP)
    return models.CharField(verbose_name or _("العملة"), **kwargs)
