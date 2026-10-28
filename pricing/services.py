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

from accounts.models import AccountType
from core import features
from core.models.tax import TaxClass, TaxSettings
from core.money import ZERO, apply_rate, quantize
from pricing.models import DiscountKind, PriceList, PriceListKind, PriceOverride, PriceRule

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


def _student_prices_withheld(user) -> bool:
    """
    Is this user kept off the student price lists until their ID card is approved?

    ⚠️  Only while the owner has the switch **on**, and only for a student account.

        With the switch off, student prices follow the account type alone — exactly
        as before the verification workflow existed. With it on, a student whose
        card has not been approved pays the ordinary price: a list for verified
        students that anyone can reach by ticking "I am a student" is not a list
        for students.

        The cheap checks come first, so the setting is read only for the one
        kind of user it can affect.
    """
    return (
        getattr(user, "account_type", None) == AccountType.STUDENT
        and not getattr(user, "is_verified", False)
        and features.student_verification_enforced()
    )


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

    if user is not None and _student_prices_withheld(user):
        # Falls through to the default list, as for any account no list matches
        candidates = candidates.exclude(kind=PriceListKind.STUDENT)

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


def _most_specific(ordered, variant):
    """
    From rows already in priority order, the one that applies to `variant`:
    a row written for **that variant** first, otherwise the product-level row.

    ⚠️  The fallback is the point.

        These lookups used to match the variant *exactly*, so `variant=None` rows
        (the ones every price list and promotion is written with) never applied to
        a line that carried a variant. The same item cost less as a plain product
        than as its size M — and a store that added colours would have seen every
        coloured line quietly drop out of its promotions.
    """
    if variant is not None:
        for row in ordered:
            if row.variant_id == variant.pk:
                return row
    for row in ordered:
        if row.variant_id is None:
            return row
    return None


def _color_of(variant):
    """
    The variant's colour, or `None`.

    ⚠️  Read through the relation's `color_id` first so a plain variant (the
        common case: sizes) costs no query. A caller that already holds the
        colour — the cart and the counter `select_related("variant__color")` —
        pays none for a coloured one either.
    """
    if variant is None or getattr(variant, "color_id", None) is None:
        return None
    color = variant.color
    return None if color.deleted_at is not None else color


def _rule_for(price_list, product, variant, quantity: int, *, book=None) -> PriceRule | None:
    """
    The price rule applying to this quantity.

    Ordered descending by minimum quantity — the first match wins, so the
    highest satisfied tier is the one applied. For a variant line its own rules
    are tried first, then the product's (see `_most_specific`).
    """
    if price_list is None:
        return None
    if book is not None:
        return book.rule(variant, quantity)

    queryset = PriceRule.objects.filter(
        price_list=price_list,
        product=product,
        is_active=True,
        min_quantity__lte=quantity,
    )
    if variant is None:
        return queryset.filter(variant__isnull=True).order_by("-min_quantity").first()

    return _most_specific(
        list(
            queryset.filter(Q(variant=variant) | Q(variant__isnull=True)).order_by("-min_quantity")
        ),
        variant,
    )


def _active_overrides(product, price_list):
    now = timezone.now()
    return (
        PriceOverride.objects.filter(product=product, is_active=True, starts_at__lte=now)
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        .filter(Q(price_list__isnull=True) | Q(price_list=price_list))
        .order_by("-starts_at")
    )


def _override_for(product, variant, price_list, *, book=None) -> PriceOverride | None:
    if book is not None:
        return book.override(variant)

    queryset = _active_overrides(product, price_list)
    if variant is None:
        return queryset.filter(variant__isnull=True).first()

    return _most_specific(
        list(queryset.filter(Q(variant=variant) | Q(variant__isnull=True))), variant
    )


class PriceBook:
    """
    Every row `price_for` would query for **one product**, loaded once.

    ⚠️  For the page that prices many variants of the same product — a colour
        picker shows one price per swatch. Calling `price_for` per swatch costs
        four or five queries each; the book is a fixed three whatever the number
        of colours, and it answers with the very same selection rules
        (`_most_specific`), so the two paths cannot disagree.
    """

    def __init__(self, product, price_list: PriceList | None):
        self.product = product
        self.price_list = price_list
        self._rules = (
            list(
                PriceRule.objects.filter(
                    price_list=price_list, product=product, is_active=True
                ).order_by("-min_quantity")
            )
            if price_list is not None
            else []
        )
        self._overrides = list(_active_overrides(product, price_list))
        self.tax = _tax_rate_for(product)

    def rule(self, variant, quantity: int) -> PriceRule | None:
        return _most_specific([r for r in self._rules if r.min_quantity <= quantity], variant)

    def override(self, variant) -> PriceOverride | None:
        return _most_specific(self._overrides, variant)


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
    book: PriceBook | None = None,
) -> PricedLine:
    """
    The price of a single line.

    The order:
        1. the applicable list price — a price-list / student rule —
           otherwise the **colour's own price**, otherwise `base_price`
        2. + the variant difference
        3. − the promotional discount
        4. + tax on the net

    ⚠️  A price-list rule beats the colour price, not the other way round.

        The owner's decision: a student on the student list pays the student price
        for any colour. The colour price is the *shop's* price for that colour —
        what a customer on no special list pays instead of the product's.

    `book` is for callers pricing many variants of one product (see `PriceBook`);
    the result is identical to the unbatched call.
    """
    if quantity < 1:
        quantity = 1

    # ⚠️  With a `book` the list is already decided — including "there is none". A falsy
    #     `price_list` must not send the engine off to resolve it again for every variant.
    if book is not None:
        price_list = book.price_list
    else:
        price_list = price_list or resolve_price_list(user)

    # 1 — the base price
    rule = _rule_for(price_list, product, variant, quantity, book=book)
    color = _color_of(variant)
    if rule is not None:
        unit_price = rule.unit_price
        applied = ("price_rule",)
    elif color is not None and color.price_override is not None:
        unit_price = color.price_override
        applied = ("color_price",)
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
    override = _override_for(product, variant, price_list, book=book)
    if override is not None:
        if override.discount_kind == DiscountKind.PERCENTAGE:
            per_unit = apply_rate(unit_price, override.discount_value)
        else:
            per_unit = min(override.discount_value, unit_price)

        discount_amount = quantize(per_unit * quantity)
        applied = (*applied, "price_override")

    # 4 — tax on the net after the discount
    tax_rate, tax_class_code = book.tax if book is not None else _tax_rate_for(product)
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
