"""
A registry of visibility filters for the catalogue.

⚠️  **This module exists because of the layer contract, not in spite of it.**

    The requirement is plain: an item whose available quantity is zero must not
    appear in the storefront. The quantity lives in `inventory.Stock`, and
    `inventory` sits **above** `catalog` in the layer diagram
    (`pricing | inventory | reviews` over
    `customers | administration | academic | catalog | shipping`).

    So `catalog.selectors` importing `inventory` inverts the direction and
    `import-linter` rejects it — rightly: the catalogue answers "what is this
    item?", and the moment it knows a stock table it starts answering "how much
    of it is there?" as well, which is the very split ADR-6 was written for.

    The registry inverts the direction the way `payments.events` does one layer
    up: `inventory` announces "here is how you tell an item is in stock",
    `catalog` asks for whatever filters were announced, and neither imports the
    other. `core` holds the dictionary and knows no business domain — which is
    what keeps the "Core is infrastructure" contract intact too.

⚠️  And it is a **filter**, not a list of ids.

    Returning ids means loading every out-of-stock product into memory to
    exclude it, and a page of twenty ends up carrying the whole catalogue. A `Q`
    merges into the query, so the database does the exclusion, the count stays
    right, and pagination does not yield short pages.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from django.db.models import Q

logger = logging.getLogger(__name__)

#: name → the callable producing the filter
_PRODUCT_FILTERS: dict[str, Callable[..., Q]] = {}


def register_product_filter(name: str, builder: Callable[..., Q]) -> None:
    """
    Register a filter applied to every public catalogue query.

    ⚠️  Keyed by name and **idempotent**.

        `AppConfig.ready` runs more than once under the auto-reloader, and
        appending to a list there stacks the same filter several times over —
        the query still returns the right answer, so nothing surfaces until a
        profiler shows the same subquery repeated five times.
    """
    _PRODUCT_FILTERS[name] = builder


def unregister_product_filter(name: str) -> None:
    """Remove a filter — used by the tests that need the unfiltered catalogue."""
    _PRODUCT_FILTERS.pop(name, None)


def registered_product_filters() -> list[str]:
    return sorted(_PRODUCT_FILTERS)


def product_visibility_filter(**context) -> Q:
    """
    The conjunction of every registered filter.

    `context` is passed through to the builders — `location` is the one in use
    today: the counter filters by its own register's stock, and the storefront
    by every sellable location.

    ⚠️  An empty registry returns an empty `Q`, which changes no query.

        `inventory` is installed in every configuration we ship, but a filter
        that raises when it is absent turns an optional domain into a mandatory
        one — and the failure would appear as an empty catalogue, not as an
        error naming its cause.
    """
    condition = Q()

    for name, builder in _PRODUCT_FILTERS.items():
        try:
            condition &= builder(**context)
        except Exception:
            # ⚠️  A broken filter must not empty the shop.
            #
            #     Excluding everything on a failure means a storefront with no
            #     items and no explanation; skipping the filter shows an item
            #     that may be out of stock — which the cart refuses anyway two
            #     clicks later. The louder failure is the wrong one here.
            logger.exception("فلتر رؤية المنتجات %s فشل — تم تخطّيه", name)

    return condition
