"""
The pricing engine — **the single source of price**.

⚠️  Everyone needing a price calls `price_for()`. Without exception.

    The cart, the order, the point of sale and the catalogue all consume the
    same result. Any parallel calculation anywhere recreates violation H5: two
    different results for the same cart depending on the path.

⚠️  **The frontend is not the source of price.** What the client sends is
    ignored, and the calculation is redone from the source on every operation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Q
from django.utils import timezone

from core.models.tax import TaxClass, TaxSettings
from core.money import ZERO, apply_rate, quantize
from pricing.models import DiscountKind, PriceList, PriceOverride, PriceRule

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PricedLine:
    """
    The pricing result for a single line.

    ⚠️  **Every field here is a historical snapshot** copied onto the order line.

        The tax rate and the price change; an issued invoice does not. Computing
        any of them later from current values falsifies the record.
    """

    quantity: int
    unit_price: Decimal  # The unit price before discount and tax
    list_price: Decimal  # The reference price — for showing "was"
    discount_amount: Decimal  # The line discount
    tax_rate: Decimal  # The rate at the time of sale — a snapshot
    tax_amount: Decimal
    price_list_code: str = ""
    tax_class_code: str = ""
    applied_rules: tuple = field(default_factory=tuple)

    @property
    def subtotal(self) -> Decimal:
        """Before discount and tax."""
        return quantize(self.unit_price * self.quantity)

    @property
    def net(self) -> Decimal:
        """The taxable base — after the discount and before the tax."""
        return quantize(self.subtotal - self.discount_amount)

    @property
    def total(self) -> Decimal:
        """The total including tax."""
        return quantize(self.net + self.tax_amount)

    @property
    def has_discount(self) -> bool:
        return self.discount_amount > 0


@dataclass(frozen=True)
class PricedCart:
    """The total for a cart or an order."""

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
        The final total.

            the total before discount
              − the discounts
              + the tax
              + shipping
        """
        return quantize(self.net_sales + self.tax_total + self.shipping_amount)

    @property
    def item_count(self) -> int:
        return sum(line.quantity for line in self.lines)


# ═══════════════════════════════════════════════════════════
#  Price list selection
# ═══════════════════════════════════════════════════════════


def resolve_price_list(user=None) -> PriceList | None:
    """
    The price list applying to this user.

    ⚠️  The highest priority wins when more than one list matches.

        A verified pharmacy may match both "wholesale" and "professionals" — and
        with no explicit priority the price becomes a matter of row ordering in
        the database.
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
    The price rule applying to this quantity.

    Ordered descending by minimum quantity — the first match wins, so the
    highest satisfied tier is the one applied.
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
    The applicable tax rate.

    ⚠️  Read **now** and copied onto the line. A later change does not touch
        issued invoices. (ADR-30)

    ⚠️  **Zero results from an explicit decision, not from an absence.**

        The previous form was: an expired class ⟵ zero. And that is a silent
        trap — the admin sets `valid_to` when changing the rate and forgets to
        reclassify the products, so they all become exempt with no warning at
        all, discovered only in a tax audit. And under-collecting is a legal
        liability, unlike over-collecting.

        Zero now means **only** three cases:
          1. the tax system is disabled entirely  (`tax.enabled = false`)
          2. the product's class genuinely has a zero rate (exempt · zero-rated)
          3. there is no effective default class in the system at all

        An expired class, by contrast, falls back to the effective default and a
        warning is logged — a higher invoice and a lower risk than silence.
    """
    if not TaxSettings.is_enabled():
        return ZERO, ""

    assigned = getattr(product, "tax_class", None)

    if assigned is not None and assigned.is_currently_valid:
        return assigned.rate, assigned.code

    if assigned is not None:
        logger.warning(
            "الفئة الضريبية %s للمنتج %s خارج فترة سريانها — سقوط إلى الافتراضية",
            assigned.code,
            getattr(product, "sku", product.pk),
        )

    fallback = TaxClass.get_default()
    if fallback is None or not fallback.is_currently_valid:
        # ⚠️  A system with no effective default class: zero is the only possible
        #     behaviour, and the warning is what makes it visible.
        logger.warning("لا فئة ضريبية افتراضية سارية — التسعير بلا ضريبة")
        return ZERO, ""

    return fallback.rate, fallback.code


# ═══════════════════════════════════════════════════════════
#  Pricing
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
    The price of a single line.

    The order:
        1. the applicable list price (or `base_price` as a reference)
        2. + the variant difference
        3. − the promotional discount
        4. + tax on the net
    """
    if quantity < 1:
        quantity = 1

    price_list = price_list or resolve_price_list(user)

    # 1 — the base price
    rule = _rule_for(price_list, product, variant, quantity)
    if rule is not None:
        unit_price = rule.unit_price
        applied = ("price_rule",)
    else:
        unit_price = product.base_price
        applied = ("base_price",)

    # 2 — the variant difference
    if variant is not None and variant.price_adjustment:
        unit_price = quantize(unit_price + variant.price_adjustment)
        applied = (*applied, "variant_adjustment")

    list_price = unit_price

    # 3 — the promotional discount
    discount_amount = ZERO
    override = _override_for(product, variant, price_list)
    if override is not None:
        if override.discount_kind == DiscountKind.PERCENTAGE:
            per_unit = apply_rate(unit_price, override.discount_value)
        else:
            per_unit = min(override.discount_value, unit_price)

        discount_amount = quantize(per_unit * quantity)
        applied = (*applied, "price_override")

    # 4 — tax on the net after the discount
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
    Pricing several lines against one list computed once.

    `items` = an iterable of `(product, quantity, variant)`.
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
    Pricing a complete cart.

    ⚠️  The coupon discount arrives ready **from `promotions`**.

        This domain does not know the coupon rules and does not validate them —
        it consumes the result only. Conflating them recreates the old duplication.
    """
    lines = tuple(price_many(items, user=user))
    shipping_tax = apply_rate(shipping_amount, shipping_tax_rate) if shipping_tax_rate else ZERO

    return PricedCart(
        lines=lines,
        shipping_amount=quantize(shipping_amount),
        shipping_tax_amount=shipping_tax,
        coupon_discount=quantize(coupon_discount),
    )
