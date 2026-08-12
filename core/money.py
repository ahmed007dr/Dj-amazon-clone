"""
المال.

⚠️  ممنوع `float` في أي حساب مالي. `Decimal` حصرًا.
    الخطأ الحالي في النموذج القديم: FloatField في ٩ مواضع.

مع عمولات ومرتجعات وضرائب، فروق الفاصلة العائمة تتراكم
حتى تكسر أي مطابقة محاسبية.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

# ═══════════════════════════════════════════════════════════
#  الثوابت
# ═══════════════════════════════════════════════════════════

MONEY_MAX_DIGITS = 12  # حتى 9,999,999,999.99
MONEY_DECIMAL_PLACES = 2

RATE_MAX_DIGITS = 5  # حتى 999.99 %
RATE_DECIMAL_PLACES = 2

ZERO = Decimal("0.00")


# ═══════════════════════════════════════════════════════════
#  الحقول
# ═══════════════════════════════════════════════════════════


def MoneyField(verbose_name=None, **kwargs):  # noqa: N802
    """حقل مبلغ مالي."""
    kwargs.setdefault("max_digits", MONEY_MAX_DIGITS)
    kwargs.setdefault("decimal_places", MONEY_DECIMAL_PLACES)
    return models.DecimalField(verbose_name, **kwargs)


def RateField(verbose_name=None, **kwargs):  # noqa: N802
    """حقل نسبة مئوية — ضريبة · خصم · عمولة."""
    kwargs.setdefault("max_digits", RATE_MAX_DIGITS)
    kwargs.setdefault("decimal_places", RATE_DECIMAL_PLACES)
    return models.DecimalField(verbose_name, **kwargs)


# ═══════════════════════════════════════════════════════════
#  العمليات
# ═══════════════════════════════════════════════════════════


def quantize(amount: Decimal) -> Decimal:
    """
    تقريب إلى دقة العملة.

    ROUND_HALF_UP هو السلوك المتوقع تجاريًا (0.125 → 0.13)،
    بخلاف افتراضي بايثون ROUND_HALF_EVEN (0.125 → 0.12).
    """
    exponent = Decimal(1).scaleb(-MONEY_DECIMAL_PLACES)
    return Decimal(amount).quantize(exponent, rounding=ROUND_HALF_UP)


def apply_rate(amount: Decimal, rate: Decimal) -> Decimal:
    """
    تطبيق نسبة مئوية.

        apply_rate(Decimal('100.00'), Decimal('14.00'))  →  Decimal('14.00')
    """
    return quantize(Decimal(amount) * Decimal(rate) / Decimal("100"))


def percentage_of(part: Decimal, whole: Decimal) -> Decimal:
    """نسبة الجزء إلى الكل. يعيد صفرًا عند القسمة على صفر."""
    whole = Decimal(whole)
    if whole == 0:
        return ZERO
    exponent = Decimal(1).scaleb(-RATE_DECIMAL_PLACES)
    return (Decimal(part) / whole * Decimal("100")).quantize(exponent, rounding=ROUND_HALF_UP)


def to_string(amount: Decimal) -> str:
    """
    التمثيل في JSON — **نص لا رقم**.

    JSON.parse في جافاسكربت يحوّل الأرقام إلى double فتُفقد الدقة:
    450.00 تصير 450، و0.1+0.2 تصير 0.30000000000000004.
    النص يعبر بلا تشويه. (ADR-31)
    """
    return str(quantize(amount))


def get_currency() -> str:
    return getattr(settings, "DEFAULT_CURRENCY", "EGP")


# ═══════════════════════════════════════════════════════════
#  العملات
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
