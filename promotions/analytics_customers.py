"""
Coupon analytics, part two — **who bought**: registered vs guest, new vs returning,
the discount volume by buyer type, the holder rollup and the customers list.

⚠️  Same rules as `promotions.analytics`, which this module builds on and never contradicts:
    the same orders count (`_is_sale_q`), the same period (`date_from` / `date_to` on
    the redemption), the same money columns. Only the *grouping* is new.

⚠️  **How buyers are told apart** (full discussion in `analytics`, "Who bought"):

        REGISTERED   the order has a customer account         → one buyer per customer profile
        GUEST        it has none (customer NULL at order time) → one buyer per normalised e-mail
                                                                 (else phone, else the order)

    A guest order later claimed by an account counts as REGISTERED in every total
    (the account owns it now) but the customers list keeps `purchased_as: "GUEST"`
    and says `has_account_now: true`, so the owner sees both facts.

⚠️  **NEW customer** = the buyer's FIRST EVER counted order is a coupon order inside the
    scope being measured; otherwise RETURNING.

        · "first ever" looks at every counted order, coupon or not, before this one;
        · a registered buyer is matched by customer id;
        · a guest is matched by e-mail (their earlier guest orders AND any registered
          order whose account e-mail is the same), else by phone;
        · with a period set, a buyer whose first order was before the period is
          RETURNING — "new" means new to the shop, not new to the date filter;
        · a buyer is new or returning as a whole (never both): if they used the code
          twice, both orders belong to the new customer.
        · an order with no e-mail and no phone cannot be matched to anyone → new.

⚠️  Everything is aggregated by the database in one grouped query
    ((coupon, buyer) per row); only the small roll-up is done in Python, so the number
    of queries does not grow with the number of coupons, orders or customers.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db.models import (
    BooleanField,
    Case,
    CharField,
    Count,
    Exists,
    IntegerField,
    Max,
    OuterRef,
    Q,
    Sum,
    Value,
    When,
)

from core.money import ZERO, quantize
from promotions.analytics import (
    _gross_expr,
    _is_sale_q,
    _net_expr,
    _order_model,
    buyer_email_expr,
    buyer_phone_expr,
    guest_key_expr,
    plain_sale_q,
    tagged_orders,
)

REGISTERED = "registered"
GUEST = "guest"
KINDS = (REGISTERED, GUEST)

#: `customer_type` as the API writes it
TYPE_LABELS = {REGISTERED: "REGISTERED", GUEST: "GUEST"}


def percent(part, whole) -> float:
    """`part / whole` as a percentage with two decimals; 0 when there is nothing to divide."""
    if not whole:
        return 0.0
    return float(round(Decimal(part) * 100 / Decimal(whole), 2))


# ═══════════════════════════════════════════════════════════
#  The orders, with the buyer worked out in SQL
# ═══════════════════════════════════════════════════════════


def identified_orders(coupon_ids, date_from=None, date_to=None):
    """
    The counted coupon orders in scope, each annotated with who bought and whether it
    was that buyer's first ever counted order.

    ⚠️  `first_flag` is 1 / 0 from a correlated `EXISTS` on earlier counted orders —
        indexed by customer for accounts and by e-mail for guests, and evaluated only
        for the branch that applies to the row.
    """
    order = _order_model()

    def earlier():
        return order.objects.filter(plain_sale_q()).filter(
            Q(created_at__lt=OuterRef("created_at"))
            | Q(created_at=OuterRef("created_at"), pk__lt=OuterRef("pk"))
        )

    registered_prior = earlier().filter(customer_id=OuterRef("customer_id"))
    # A guest's earlier purchases: as a guest with that e-mail, or as an account with it.
    email_prior = earlier().filter(
        Q(contact_email__iexact=OuterRef("buyer_email"))
        | Q(customer__user__email__iexact=OuterRef("buyer_email"))
    )
    phone_prior = earlier().filter(recipient_phone=OuterRef("buyer_phone"))

    return (
        tagged_orders(coupon_ids, date_from, date_to)
        .filter(_is_sale_q())
        .annotate(
            buyer_email=buyer_email_expr(),
            buyer_phone=buyer_phone_expr(),
            guest_key=Case(
                When(customer_id__isnull=True, then=guest_key_expr()),
                output_field=CharField(),
            ),
        )
        .annotate(
            has_prior=Case(
                When(customer_id__isnull=False, then=Exists(registered_prior)),
                When(buyer_email__isnull=False, then=Exists(email_prior)),
                When(buyer_phone__isnull=False, then=Exists(phone_prior)),
                default=Value(False),
                output_field=BooleanField(),
            )
        )
        .annotate(
            first_flag=Case(
                When(has_prior=True, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
    )


def _buyer_rows(coupon_ids, date_from, date_to):
    """One row per (coupon, buyer): the order figures and whether the buyer is new."""
    return list(
        identified_orders(coupon_ids, date_from, date_to)
        .order_by()
        .values("coupon_ref", "customer_id", "guest_key")
        .annotate(
            orders=Count("pk"),
            gross=Sum(_gross_expr()),
            discount=Sum("coupon_discount"),
            net=Sum(_net_expr()),
            order_total=Sum("grand_total"),
            new_flag=Max("first_flag"),
        )
    )


# ═══════════════════════════════════════════════════════════
#  The roll-up
# ═══════════════════════════════════════════════════════════


class _Acc:
    """Running totals for one scope (a coupon, a holder, or everything)."""

    def __init__(self):
        self.kinds = {
            kind: {
                "orders": 0,
                "gross": ZERO,
                "discount": ZERO,
                "net": ZERO,
                "order_total": ZERO,
                "buyers": set(),
            }
            for kind in KINDS
        }
        #: buyer -> [is_new, net, discount, orders]
        self.buyers: dict[tuple, list] = {}

    def add(self, row: dict) -> None:
        kind = REGISTERED if row["customer_id"] is not None else GUEST
        buyer = (kind, row["customer_id"] if kind == REGISTERED else row["guest_key"])

        bucket = self.kinds[kind]
        bucket["orders"] += row["orders"]
        bucket["gross"] += row["gross"] or ZERO
        bucket["discount"] += row["discount"] or ZERO
        bucket["net"] += row["net"] or ZERO
        bucket["order_total"] += row["order_total"] or ZERO
        bucket["buyers"].add(buyer)

        entry = self.buyers.setdefault(buyer, [False, ZERO, ZERO, 0])
        entry[0] = entry[0] or bool(row["new_flag"])
        entry[1] += row["net"] or ZERO
        entry[2] += row["discount"] or ZERO
        entry[3] += row["orders"]

    def block(self) -> dict:
        by_type = {}
        for kind in KINDS:
            bucket = self.kinds[kind]
            by_type[kind] = {
                "orders": bucket["orders"],
                "customers": len(bucket["buyers"]),
                "gross": quantize(bucket["gross"]),
                "discount": quantize(bucket["discount"]),
                "net": quantize(bucket["net"]),
                "order_total": quantize(bucket["order_total"]),
            }

        fresh = [entry for entry in self.buyers.values() if entry[0]]
        back = [entry for entry in self.buyers.values() if not entry[0]]

        def summary(entries):
            return {
                "count": len(entries),
                "orders": sum(entry[3] for entry in entries),
                "net_sales": quantize(sum((entry[1] for entry in entries), ZERO)),
                "discount": quantize(sum((entry[2] for entry in entries), ZERO)),
            }

        gross = by_type[REGISTERED]["gross"] + by_type[GUEST]["gross"]
        discount = by_type[REGISTERED]["discount"] + by_type[GUEST]["discount"]
        return {
            "by_customer_type": by_type,
            "new_customers": summary(fresh),
            "returning_customers": summary(back),
            "new_customer_rate": percent(len(fresh), len(self.buyers)),
            "discount_by_customer_type": {
                REGISTERED: by_type[REGISTERED]["discount"],
                GUEST: by_type[GUEST]["discount"],
            },
            "discount_share_of_gross": percent(discount, gross),
        }


class Breakdown:
    """
    The buyer figures for a set of coupons, from **one** grouped query.

    `block([coupon_id, ...])` rolls up any subset (one coupon, a holder's codes);
    `block()` is everything — with each buyer counted once however many codes they used.
    """

    def __init__(self, rows: list[dict]):
        self._by_coupon: dict = defaultdict(list)
        for row in rows:
            if row["coupon_ref"] is not None:
                self._by_coupon[row["coupon_ref"]].append(row)

    @classmethod
    def load(cls, coupon_ids, date_from=None, date_to=None) -> Breakdown:
        if coupon_ids is not None:
            coupon_ids = list(coupon_ids)
        return cls(_buyer_rows(coupon_ids, date_from, date_to))

    def block(self, coupon_ids=None) -> dict:
        acc = _Acc()
        wanted = self._by_coupon.keys() if coupon_ids is None else coupon_ids
        for coupon_id in wanted:
            for row in self._by_coupon.get(coupon_id, ()):
                acc.add(row)
        return acc.block()


def empty_block() -> dict:
    return _Acc().block()
