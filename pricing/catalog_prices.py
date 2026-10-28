"""
What each product — and each variant — costs *this viewer*, for a whole listing at once.

⚠️  The listing asks `pricing`; it never decides a price itself.

    This is the **same engine** as the cart's: every figure below is a `price_for()`
    result, not a second formula. What is different is only how its inputs are loaded —
    `PriceBook` costs two queries per product, which on a page of twenty cards is forty;
    here the price-list rules of the whole page are one `IN` query and each product gets
    a book already holding its rows.

⚠️  The figure is `unit_price`: price-list rule → colour price → reference price → + the
    variant difference. **Promotions are deliberately not in it** (the product page has
    never shown them either — they are applied to the cart line), and neither is tax.

Registered with `core.price_facts` from `PricingConfig.ready` — the catalogue serialiser
cannot import this layer (see that module).
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from core.money import ZERO
from pricing import services
from pricing.models import PriceRule


class _ListingBook:
    """
    A `PriceBook` for one product whose rows were loaded in bulk, by someone else.

    It answers `price_for`'s three questions the way `PriceBook` does — with the very same
    selection rule (`services._most_specific`) so the two cannot disagree — except that it
    never has a promotion or a tax to report: a listing shows neither.
    """

    tax = (ZERO, "")

    def __init__(self, price_list, rules: list[PriceRule]):
        self.price_list = price_list
        self._rules = rules

    def rule(self, variant, quantity: int):
        wanted = [r for r in self._rules if r.min_quantity <= quantity]
        return services._most_specific(wanted, variant)

    def override(self, variant):
        return None


def listing_price_facts(products, variants, user) -> dict[str, dict[str, Decimal]]:
    """
    `{"products": {pk: Decimal}, "variants": {pk: Decimal}}` — a fixed handful of queries.

    One price list for the viewer, one `IN` query for the page's rules, and — when the
    caller attached `variant.color` in memory (the product page does) — nothing per variant.
    """
    price_list = services.resolve_price_list(user)

    rules: dict = defaultdict(list)
    if price_list is not None:
        queryset = PriceRule.objects.filter(
            price_list=price_list, product_id__in=[p.pk for p in products], is_active=True
        ).order_by("-min_quantity")
        for rule in queryset:
            rules[rule.product_id].append(rule)

    books = {p.pk: _ListingBook(price_list, rules.get(p.pk, [])) for p in products}
    by_id = {p.pk: p for p in products}

    def price(product, variant=None) -> Decimal:
        line = services.price_for(
            product, 1, user=user, variant=variant, price_list=price_list, book=books[product.pk]
        )
        return line.unit_price

    return {
        "products": {str(p.pk): price(p) for p in products},
        "variants": {
            str(v.pk): price(by_id[v.product_id], v) for v in variants if v.product_id in by_id
        },
    }
