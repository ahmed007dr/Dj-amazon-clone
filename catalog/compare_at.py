"""
The "price before discount" (compare-at) arithmetic — plain functions over plain values.

⚠️  **The server decides whether the old price is shown; the browser only draws it.**

    A product carries an optional `compare_at_price`, an owner-typed figure: "this
    used to cost 100". It is a *claim about the past*, not part of the price the
    customer pays (that stays `pricing`'s answer), and it is shown only while it is
    still true for the person looking:

        shown  ⟺  compare_at  >  the price THIS viewer pays

    A student on a student price list pays less than the shelf price, so for them
    the old price is more impressive; a viewer whose price list *raises* the price
    above the old figure sees nothing struck through — striking a price that is
    lower than the current one is a visual lie. Every storefront payload goes
    through `shown_compare_at`, so there is exactly one place that rule lives.

⚠️  This module imports **no model and no other domain**: `catalog` cannot import
    `pricing`, and the importer, the cart and the admin serializers all need the very
    same arithmetic. They hand over the viewer's price; this module never fetches one.

⚠️  `discount_percent` is **rounded down** and computed in integer cents.

    "-20%" must never be a flattering round-up (19.6 % shown as 20 %), and a float
    division would make 30.00 → 24.00 report 19 % because 0.2 is not exactly 0.2.
"""

from __future__ import annotations

from decimal import Decimal

from core.money import quantize

#: Shown in the admin form's error and the API's field error — Arabic first, then English,
#: because the admin panel is bilingual and the server has no per-request catalogue here.
MESSAGE = (
    "يجب أن يكون السعر قبل الخصم أكبر من السعر الحالي "
    "(Price before discount must be greater than the current price)"
)


def _cents(amount) -> int:
    return int((Decimal(str(amount)) * 100).to_integral_value())


def compare_at_error(compare_at, price) -> str | None:
    """
    The validation message when `compare_at` is set but **not strictly greater** than `price`.

    `None` for "no compare-at" or "fine". Equal is rejected: a struck-through price equal
    to the current one is no discount at all, and "-0%" is how that mistake reaches a shelf.
    """
    if compare_at is None or price is None:
        return None
    return None if Decimal(str(compare_at)) > Decimal(str(price)) else MESSAGE


def shown_compare_at(compare_at, price) -> Decimal | None:
    """`compare_at` when it is strictly above the viewer's `price`, else `None` (show nothing)."""
    if compare_at is None or price is None:
        return None
    compare_at, price = Decimal(str(compare_at)), Decimal(str(price))
    return compare_at if compare_at > price else None


def discount_percent(compare_at, price) -> int | None:
    """
    The saving as a whole percentage, **rounded down** — `None` when nothing is shown.

    May be `0` (a 0.4 % saving still shows the old price, but is not worth a badge — the
    storefront hides a badge below 1 %).
    """
    shown = shown_compare_at(compare_at, price)
    if shown is None:
        return None
    old = _cents(shown)
    return ((old - _cents(price)) * 100) // old if old > 0 else None


def reference_compare_at(product, color=None, variant=None) -> Decimal | None:
    """
    The raw "old price" that belongs to **this exact item**, before the viewer's price is weighed.

    * a plain product → the product's own;
    * a colour with its **own** compare-at → that one;
    * a colour that inherits the product's price (`price_override` empty) → the product's;
    * a colour with its **own price but no own compare-at** → none. The product's old price
      described the product's price, not this colour's; striking it against a different
      figure would invent a discount nobody typed.
    * a variant's price difference rides along: if "size XL" costs 20 more, so did it before.
      Without that the same saving would read as 20 % on the base size and 16 % on XL.
    """
    if color is not None:
        if color.compare_at_price is not None:
            raw = color.compare_at_price
        elif color.price_override is None:
            raw = product.compare_at_price
        else:
            raw = None
    else:
        raw = product.compare_at_price

    if raw is None:
        return None
    if variant is not None and variant.price_adjustment:
        raw = raw + variant.price_adjustment
    return raw


def display_facts(compare_at, price) -> dict:
    """The two payload fields: `compare_at_price` (a string or `None`) and `discount_percent`."""
    shown = shown_compare_at(compare_at, price)
    return {
        "compare_at_price": None if shown is None else format(quantize(shown), "f"),
        "discount_percent": discount_percent(compare_at, price),
    }
