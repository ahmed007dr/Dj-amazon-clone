"""
A registry of the per-colour facts the catalogue cannot compute itself.

⚠️  **This module exists for the same reason as `core/visibility.py`** — read
    that one for the long version.

    The product page needs, for every swatch, a price ("what does *this
    customer* pay for the red one?") and an availability ("is red sold out?").
    The first is `pricing`'s answer and the second `inventory`'s, and both sit
    **above** `catalog` in the layer diagram — so the catalogue serialiser
    importing either inverts the direction and `import-linter` rejects it.

    Each domain therefore *announces* a provider at start-up and the catalogue
    asks the registry for whatever was announced; neither imports the other and
    `core` stays free of business rules.

A provider is `provider(product, colors, user) -> {str(color.pk): {field: value}}`:

  * `colors` carry their active variants in `color.active_variants` (a list), so a
    provider never queries per colour for them;
  * it returns only the fields it owns — `price` from pricing; `is_available`,
    `is_low`, `available` from inventory — and the registry merges the dicts.

⚠️  A provider that raises is **skipped, not fatal** (and logged).

    A failure in the price engine must not turn a product page into a 500 — the
    swatch falls back to the colour's own price or the product's, and the cart
    re-prices from the source on every operation anyway.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable

logger = logging.getLogger(__name__)

ColorFactsProvider = Callable[..., "dict[str, dict]"]

#: name → provider
_PROVIDERS: dict[str, ColorFactsProvider] = {}


def register_color_facts(name: str, provider: ColorFactsProvider) -> None:
    """Register a provider — keyed by name and **idempotent** (`ready()` may run twice)."""
    _PROVIDERS[name] = provider


def unregister_color_facts(name: str) -> None:
    """Remove a provider — for the tests that need the bare catalogue."""
    _PROVIDERS.pop(name, None)


def registered_color_facts() -> list[str]:
    return sorted(_PROVIDERS)


def color_facts(
    product, colors: Iterable, *, user=None, only: Iterable[str] | None = None
) -> dict[str, dict]:
    """
    The merged facts of every registered provider, keyed by `str(color.pk)`.

    `only` limits the providers asked — the admin list wants stock and has no use
    for a price computed for a customer.
    """
    colors = list(colors)
    merged: dict[str, dict] = {}
    if not colors:
        return merged

    wanted = None if only is None else set(only)
    for name, provider in _PROVIDERS.items():
        if wanted is not None and name not in wanted:
            continue
        try:
            facts = provider(product, colors, user)
        except Exception:
            logger.exception("مزوّد حقائق الألوان %s فشل — تم تخطّيه", name)
            continue
        for color_id, fields in facts.items():
            merged.setdefault(str(color_id), {}).update(fields)

    return merged
