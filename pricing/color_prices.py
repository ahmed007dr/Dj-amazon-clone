"""
What each colour of a product costs *this customer* — for the product page.

⚠️  The page asks `pricing`; it never adds `price_override` to `base_price` itself.

    The browser used to add the variant difference to the reference price on its
    own, which is the second calculation of the same price that
    `pricing.services` exists to prevent. Here the swatch price is whatever
    `price_for` returns for that colour's variant — so a student's list price, a
    colour price and a size difference arrive already combined, and the cart
    charges the figure the swatch showed.

Registered with `core.color_facts` from `PricingConfig.ready` — the catalogue
serialiser cannot import this layer (see that module).
"""

from __future__ import annotations

from pricing import services


def color_price_facts(product, colors, user) -> dict[str, dict]:
    """
    `{color_id: {"price": "120.00"}}` — one entry per colour that has a variant.

    One `PriceBook` and one price list for the whole product, so the cost is a
    fixed handful of queries however many colours there are.
    """
    price_list = services.resolve_price_list(user)
    book = services.PriceBook(product, price_list)

    facts: dict[str, dict] = {}
    for color in colors:
        variants = getattr(color, "active_variants", None)
        if variants is None:
            variants = list(color.variants.filter(is_active=True))
        if not variants:
            # A colour with no variant cannot be bought, so it has no price to show;
            # the serialiser falls back to the colour's own price or the product's.
            continue

        variant = variants[0]
        # The in-memory link spares the engine a query to fetch the colour again.
        variant.color = color

        line = services.price_for(
            product, 1, user=user, variant=variant, price_list=price_list, book=book
        )
        facts[str(color.pk)] = {"price": str(line.unit_price)}

    return facts
