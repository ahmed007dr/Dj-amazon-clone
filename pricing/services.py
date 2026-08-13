"""
محرك التسعير — **المصدر الوحيد للسعر**.

⚠️  كل من يحتاج سعرًا يستدعي `price_for()`. بلا استثناء.

    السلة والطلب ونقطة البيع والكتالوج — كلها تستهلك نفس النتيجة.
    أي حساب موازٍ في أي مكان يعيد إنتاج الانتهاك H5: نتيجتان
    مختلفتان لنفس السلة حسب المسار.

⚠️  **الواجهة ليست مصدر السعر.** ما يرسله العميل يُتجاهَل ويُعاد
    الحساب من المصدر عند كل عملية.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from core.models.tax import TaxClass, TaxSettings
from core.money import ZERO, apply_rate, quantize
from pricing.models import DiscountKind, PriceList, PriceOverride, PriceRule


@dataclass(frozen=True)
class PricedLine:
    """
    نتيجة تسعير سطر واحد.

    ⚠️  **كل حقل هنا لقطة تاريخية** تُنسخ إلى سطر الطلب.

        النسبة الضريبية والسعر يتغيّران؛ الفاتورة الصادرة لا
        تتغيّر. حساب أي منها لاحقًا من القيم الحالية يزوّر السجل.
    """

    quantity: int
    unit_price: Decimal  # سعر الوحدة قبل الخصم والضريبة
    list_price: Decimal  # السعر المرجعي — لعرض «قبل الخصم»
    discount_amount: Decimal  # خصم السطر
    tax_rate: Decimal  # النسبة وقت البيع — لقطة
    tax_amount: Decimal
    price_list_code: str = ""
    tax_class_code: str = ""
    applied_rules: tuple = field(default_factory=tuple)

    @property
    def subtotal(self) -> Decimal:
        """قبل الخصم والضريبة."""
        return quantize(self.unit_price * self.quantity)

    @property
    def net(self) -> Decimal:
        """الوعاء الضريبي — بعد الخصم قبل الضريبة."""
        return quantize(self.subtotal - self.discount_amount)

    @property
    def total(self) -> Decimal:
        """الإجمالي شامل الضريبة."""
        return quantize(self.net + self.tax_amount)

    @property
    def has_discount(self) -> bool:
        return self.discount_amount > 0


@dataclass(frozen=True)
class PricedCart:
    """إجمالي سلة أو طلب."""

    lines: tuple
    shipping_amount: Decimal = ZERO
    shipping_tax_amount: Decimal = ZERO
    coupon_discount: Decimal = ZERO
    currency: str = "EGP"

    @property
    def subtotal(self) -> Decimal:
        return quantize(sum((line.subtotal for line in self.lines), ZERO))

    @property
    def line_discount(self) -> Decimal:
        return quantize(sum((line.discount_amount for line in self.lines), ZERO))

    @property
    def discount_total(self) -> Decimal:
        return quantize(self.line_discount + self.coupon_discount)

    @property
    def net_sales(self) -> Decimal:
        return quantize(self.subtotal - self.discount_total)

    @property
    def tax_total(self) -> Decimal:
        return quantize(
            sum((line.tax_amount for line in self.lines), ZERO) + self.shipping_tax_amount
        )

    @property
    def total(self) -> Decimal:
        """
        الإجمالي النهائي.

            الإجمالي قبل الخصم
              − الخصومات
              + الضريبة
              + الشحن
        """
        return quantize(self.net_sales + self.tax_total + self.shipping_amount)

    @property
    def item_count(self) -> int:
        return sum(line.quantity for line in self.lines)


# ═══════════════════════════════════════════════════════════
#  اختيار قائمة الأسعار
# ═══════════════════════════════════════════════════════════


def resolve_price_list(user=None) -> PriceList | None:
    """
    قائمة الأسعار المنطبقة على هذا المستخدم.

    ⚠️  الأعلى أولوية يفوز عند تطابق أكثر من قائمة.

        صيدلية موثّقة قد تطابق «جملة» و«مهنيون» معًا — بلا أولوية
        صريحة يصير السعر رهن ترتيب الصفوف في قاعدة البيانات.
    """
    today = timezone.localdate()
    candidates = PriceList.objects.filter(is_active=True, valid_from__lte=today).filter(
        Q(valid_to__isnull=True) | Q(valid_to__gte=today)
    )

    account_type = getattr(user, "account_type", None) if user else None

    if account_type:
        matched = [
            price_list
            for price_list in candidates
            if account_type in (price_list.account_types or [])
        ]
        if matched:
            return max(matched, key=lambda pl: pl.priority)

    return candidates.filter(is_default=True).first()


def _rule_for(price_list, product, variant, quantity: int) -> PriceRule | None:
    """
    قاعدة السعر المنطبقة على هذه الكمية.

    الترتيب تنازلي بالكمية الدنيا — أول تطابق يفوز، فالشريحة
    الأعلى المستوفاة هي المطبَّقة.
    """
    if price_list is None:
        return None

    return (
        PriceRule.objects.filter(
            price_list=price_list,
            product=product,
            variant=variant,
            is_active=True,
            min_quantity__lte=quantity,
        )
        .order_by("-min_quantity")
        .first()
    )


def _override_for(product, variant, price_list) -> PriceOverride | None:
    now = timezone.now()
    return (
        PriceOverride.objects.filter(
            product=product,
            variant=variant,
            is_active=True,
            starts_at__lte=now,
        )
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        .filter(Q(price_list__isnull=True) | Q(price_list=price_list))
        .order_by("-starts_at")
        .first()
    )


def _tax_rate_for(product) -> tuple[Decimal, str]:
    """
    النسبة الضريبية المنطبقة.

    ⚠️  تُقرأ **الآن** وتُنسخ إلى السطر. تغيّرها لاحقًا لا يمس
        الفواتير الصادرة. (ADR-30)
    """
    if not TaxSettings.is_enabled():
        return ZERO, ""

    tax_class = getattr(product, "tax_class", None) or TaxClass.get_default()
    if tax_class is None or not tax_class.is_currently_valid:
        return ZERO, ""

    return tax_class.rate, tax_class.code


# ═══════════════════════════════════════════════════════════
#  التسعير
# ═══════════════════════════════════════════════════════════


def price_for(
    product,
    quantity: int = 1,
    *,
    user=None,
    variant=None,
    price_list: PriceList | None = None,
) -> PricedLine:
    """
    سعر سطر واحد.

    الترتيب:
        ١. سعر القائمة المنطبقة (أو `base_price` مرجعًا)
        ٢. + فرق النسخة
        ٣. − الخصم الترويجي
        ٤. + الضريبة على الصافي
    """
    if quantity < 1:
        quantity = 1

    price_list = price_list or resolve_price_list(user)

    # ١ — السعر الأساسي
    rule = _rule_for(price_list, product, variant, quantity)
    if rule is not None:
        unit_price = rule.unit_price
        applied = ("price_rule",)
    else:
        unit_price = product.base_price
        applied = ("base_price",)

    # ٢ — فرق النسخة
    if variant is not None and variant.price_adjustment:
        unit_price = quantize(unit_price + variant.price_adjustment)
        applied = (*applied, "variant_adjustment")

    list_price = unit_price

    # ٣ — الخصم الترويجي
    discount_amount = ZERO
    override = _override_for(product, variant, price_list)
    if override is not None:
        if override.discount_kind == DiscountKind.PERCENTAGE:
            per_unit = apply_rate(unit_price, override.discount_value)
        else:
            per_unit = min(override.discount_value, unit_price)

        discount_amount = quantize(per_unit * quantity)
        applied = (*applied, "price_override")

    # ٤ — الضريبة على الصافي بعد الخصم
    tax_rate, tax_class_code = _tax_rate_for(product)
    net = quantize(unit_price * quantity - discount_amount)
    tax_amount = apply_rate(net, tax_rate) if tax_rate else ZERO

    return PricedLine(
        quantity=quantity,
        unit_price=unit_price,
        list_price=list_price,
        discount_amount=discount_amount,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        price_list_code=price_list.code if price_list else "",
        tax_class_code=tax_class_code,
        applied_rules=applied,
    )


def price_many(items, *, user=None) -> list[PricedLine]:
    """
    تسعير عدة أسطر بقائمة واحدة محسوبة مرة.

    `items` = تكرار من `(product, quantity, variant)`.
    """
    price_list = resolve_price_list(user)
    return [
        price_for(product, quantity, user=user, variant=variant, price_list=price_list)
        for product, quantity, variant in items
    ]


def price_cart(
    items,
    *,
    user=None,
    shipping_amount: Decimal = ZERO,
    shipping_tax_rate: Decimal = ZERO,
    coupon_discount: Decimal = ZERO,
) -> PricedCart:
    """
    تسعير سلة كاملة.

    ⚠️  خصم الكوبون يأتي **من `promotions`** جاهزًا.

        هذا النطاق لا يعرف قواعد الكوبونات ولا يحققها — يستهلك
        النتيجة فقط. الخلط بينهما يعيد إنتاج التكرار القديم.
    """
    lines = tuple(price_many(items, user=user))
    shipping_tax = apply_rate(shipping_amount, shipping_tax_rate) if shipping_tax_rate else ZERO

    return PricedCart(
        lines=lines,
        shipping_amount=quantize(shipping_amount),
        shipping_tax_amount=shipping_tax,
        coupon_discount=quantize(coupon_discount),
    )
