"""
A registry of "what does *this viewer* pay?" for the catalogue's listings.

⚠️  **This module exists for the same reason as `core/color_facts.py`** — read that one
    for the long version.

    A product card and a product page show a price, and "the price" is `pricing`'s
    answer, not the catalogue's. `pricing` sits **above** `catalog` in the layer
    diagram, so the catalogue serialiser importing it inverts the direction and
    `import-linter` rejects it. `pricing` therefore *announces* a provider at
    start-up and the catalogue asks the registry; neither imports the other.

    Until now a card showed `base_price` — the *reference* price — and only the colour
    swatches asked `pricing`. That was fine while nothing was compared with it. A struck-
    through "price before discount" is a comparison with **the price this customer
    pays**, so the card and the page need the same figure the cart will charge: a
    student on the student list must not be shown a 100 % reference price beside a
    "was" that only makes sense against their own.

A provider is `provider(products, variants, user) -> {"products": {...}, "variants": {...}}`
where each inner dict maps `str(pk)` to a `Decimal` unit price (before promotions and
tax — exactly `PricedLine.unit_price`). It must cost a **fixed** number of queries
however many products are passed: a list page calls it once for the whole page.

⚠️  A provider that raises is **skipped, not fatal** (and logged). The card falls back
    to the reference price, and the cart re-prices from the source on every operation.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from decimal import Decimal

logger = logging.getLogger(__name__)

PriceProvider = Callable[..., "dict[str, dict[str, Decimal]]"]

#: name → provider
_PROVIDERS: dict[str, PriceProvider] = {}


def register_price_provider(name: str, provider: PriceProvider) -> None:
    """Register a provider — keyed by name and **idempotent** (`ready()` may run twice)."""
    _PROVIDERS[name] = provider


def unregister_price_provider(name: str) -> None:
    """Remove a provider — for the tests that need the bare catalogue."""
    _PROVIDERS.pop(name, None)


def registered_price_providers() -> list[str]:
    return sorted(_PROVIDERS)


def viewer_prices(
    products: Iterable, variants: Iterable = (), *, user=None
) -> dict[str, dict[str, Decimal]]:
    """
    `{"products": {pk: price}, "variants": {pk: price}}` for whoever `user` is.

    Missing keys mean "nobody could say" (no provider, or it failed): the caller falls
    back to the reference price, which is the honest answer to "what is this worth?".
    """
    products, variants = list(products), list(variants)
    merged: dict[str, dict[str, Decimal]] = {"products": {}, "variants": {}}
    if not products:
        return merged

    for name, provider in _PROVIDERS.items():
        try:
            found = provider(products, variants, user)
        except Exception:
            logger.exception("مزوّد الأسعار %s فشل — تم تخطّيه", name)
            continue
        merged["products"].update(found.get("products", {}))
        merged["variants"].update(found.get("variants", {}))

    return merged
