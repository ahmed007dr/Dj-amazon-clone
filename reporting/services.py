"""
Reporting.

⚠️  **This domain reads and never writes — ever.**

    It has no models and no `migrations`. Every figure is derived from its source
    at request time: sales from `orders`, stock from `inventory`, and profit
    from `finance`.

    Storing an aggregated copy here creates a third number that must match two
    sources, and at the first divergence between them nobody can settle it. And
    when the volume grows, a cache with an expiry is added — not a parallel
    truth table.

⚠️  And no domain imports `reporting`.

    It is the top layer: it knows everyone and nobody knows it — like `devtools`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import (
    Count,
    DecimalField,
    Exists,
    ExpressionWrapper,
    F,
    OuterRef,
    Q,
    Subquery,
    Sum,
    UUIDField,
    Value,
)
from django.db.models.functions import (
    Coalesce,
    ExtractHour,
    ExtractIsoWeekDay,
    TruncDate,
)
from django.utils import timezone

from core.errors import BusinessError, ErrorCode
from core.money import ZERO, percentage_of, quantize
from orders import guest as guest_services

#: ⚠️  `unit_price × quantity` mixes `Decimal` with an integer.
#
#     Django does not infer the result type from two different operands, so it
#     refuses the aggregation with an obscure `FieldError`. Declaring the type
#     once here is clearer than repeating it in every query — and the financial precision follows
#     it.
#
# ⚠️  And no aggregate in the same call may be named `quantity`.
#
#     Names are resolved in order inside a single `annotate`: naming one
#     `quantity=Sum("quantity")` makes `F("quantity")` here refer to the
#     **aggregate** rather than the field — so Django refuses "an aggregate
#     inside an aggregate" with a message that gives no hint of the cause. Hence the name
#     `units_sold`.
LINE_REVENUE = ExpressionWrapper(
    F("unit_price") * F("quantity"),
    output_field=DecimalField(max_digits=18, decimal_places=2),
)


def _money(queryset, field: str) -> Decimal:
    total = queryset.aggregate(
        total=Coalesce(
            Sum(field),
            Value(ZERO),
            output_field=DecimalField(max_digits=18, decimal_places=2),
        )
    )["total"]
    return quantize(total)


def assert_period(start: date, end: date) -> None:
    """
    ⚠️  An inverted range produces a report of zeros that **looks genuine**.

        No error and no rows, so it reads as "a month with no sales" rather than
        "a wrong range".
    """
    if start > end:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="بداية الفترة بعد نهايتها")


def _sold_orders(start: date, end: date):
    """
    The orders counted as sales in a period.

    ⚠️  **One source for the definition of "a sale"**, used by every report here.

        Defining it in each function makes the sales report exclude cancelled
        orders while the items report includes them — so two numbers on the same
        screen differ and nobody knows which is right.
    """
    from orders.models import Order, OrderStatus

    return Order.objects.filter(created_at__date__gte=start, created_at__date__lte=end).exclude(
        status__in=[OrderStatus.CANCELLED, OrderStatus.REFUNDED]
    )


# ═══════════════════════════════════════════════════════════
#  Sales
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SalesSummary:
    start: date
    end: date
    orders_count: int
    gross_sales: Decimal
    returns_total: Decimal
    net_sales: Decimal
    average_order: Decimal
    customers_count: int


def sales_summary(start: date, end: date) -> SalesSummary:
    from orders.models import Order, OrderStatus

    assert_period(start, end)

    sold = _sold_orders(start, end)
    returned = Order.objects.filter(
        created_at__date__gte=start,
        created_at__date__lte=end,
        status=OrderStatus.REFUNDED,
    )

    gross = _money(sold, "grand_total")
    returns_total = _money(returned, "grand_total")
    count = sold.count()

    return SalesSummary(
        start=start,
        end=end,
        orders_count=count,
        gross_sales=gross,
        returns_total=returns_total,
        net_sales=quantize(gross - returns_total),
        # ⚠️  A division-by-zero guard — a period with no orders is a normal state
        average_order=quantize(gross / count) if count else ZERO,
        # ⚠️  Buyers we can tell apart — accounts and guest emails, never the NULL
        #     group (see `orders.guest.count_distinct_buyers`).
        customers_count=guest_services.count_distinct_buyers(sold),
    )


def sales_by_day(start: date, end: date) -> list[dict]:
    """
    ⚠️  One aggregated query, not one query per day.

        A loop over thirty days means thirty queries on every dashboard open —
        and it is the first screen the admin opens each morning.
    """
    assert_period(start, end)

    rows = (
        _sold_orders(start, end)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(orders=Count("id"), total=Sum("grand_total"))
        .order_by("day")
    )

    return [
        {
            "day": row["day"].isoformat(),
            "orders": row["orders"],
            "total": str(quantize(row["total"] or ZERO)),
        }
        for row in rows
    ]


def sales_by_channel(start: date, end: date) -> list[dict]:
    assert_period(start, end)

    rows = (
        _sold_orders(start, end)
        .values("channel")
        .annotate(orders=Count("id"), total=Sum("grand_total"))
        .order_by("-total")
    )
    return [
        {
            "channel": row["channel"] or "—",
            "orders": row["orders"],
            "total": str(quantize(row["total"] or ZERO)),
        }
        for row in rows
    ]


#: The "most ordered" ordering — by value or by count.
TOP_PRODUCT_ORDERINGS = {"revenue": "-revenue", "quantity": "-units_sold"}


def top_products(start: date, end: date, limit: int = 20, by: str = "revenue") -> list[dict]:
    """
    The most ordered items.

    ⚠️  **The two measures differ and both are correct.**

        By value: a two-pound box of masks sold a thousand times does not
        outrank a thousand-pound device sold twenty times — and the purchasing
        decision is built on value.

        By count: "most ordered" in its literal sense, and it is what the stock
        and shelf-space decision is built on.

        The two figures are therefore always displayed together, and the sort is
        a choice rather than a verdict.

    ⚠️  And an unknown key **is refused, not ignored**.

        Silently falling back to the default makes `?by=units` return an ordering
        by value with no indication at all — so the admin reads a table they
        believe they sorted.
    """
    from orders.models import OrderLine

    assert_period(start, end)

    ordering = TOP_PRODUCT_ORDERINGS.get(by)
    if ordering is None:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            detail=f"ترتيب غير معروف: {by} — المتاح: {' · '.join(TOP_PRODUCT_ORDERINGS)}",
        )

    rows = (
        OrderLine.objects.filter(order__in=_sold_orders(start, end))
        .values("product_id", "product_sku", "product_name_ar", "product_name_en")
        .annotate(units_sold=Sum("quantity"), revenue=Sum(LINE_REVENUE))
        .order_by(ordering)[:limit]
    )

    return [
        {
            "product": str(row["product_id"]),
            "sku": row["product_sku"],
            "name_ar": row["product_name_ar"],
            "name_en": row["product_name_en"],
            "quantity": row["units_sold"],
            "revenue": str(quantize(row["revenue"] or ZERO)),
        }
        for row in rows
    ]


def sales_by_category(start: date, end: date, limit: int = 20) -> list[dict]:
    from orders.models import OrderLine

    assert_period(start, end)

    rows = (
        OrderLine.objects.filter(order__in=_sold_orders(start, end))
        .values(
            "product__category__slug", "product__category__name_ar", "product__category__name_en"
        )
        .annotate(units_sold=Sum("quantity"), revenue=Sum(LINE_REVENUE))
        .order_by("-revenue")[:limit]
    )

    return [
        {
            "slug": row["product__category__slug"] or "—",
            "name_ar": row["product__category__name_ar"] or "—",
            "name_en": row["product__category__name_en"] or "—",
            "quantity": row["units_sold"],
            "revenue": str(quantize(row["revenue"] or ZERO)),
        }
        for row in rows
    ]


# ═══════════════════════════════════════════════════════════
#  Sales and discounts
# ═══════════════════════════════════════════════════════════

#: Wide enough for any total the shop will ever produce (`MoneyField` is 12 digits).
_MONEY = DecimalField(max_digits=18, decimal_places=2)

#: The products' value after every discount — before tax and shipping.
_NET_OF_DISCOUNT = ExpressionWrapper(F("subtotal") - F("discount_total"), output_field=_MONEY)

#: The kinds of discount an order can tell apart, in the order they are shown.
DISCOUNT_SOURCES = ("coupon", "loyalty_points", "item_promotion", "manual")


def _total(expression, *, only: Q | None = None):
    """A `SUM` that reads zero rather than `None` over no rows."""
    return Coalesce(Sum(expression, filter=only), Value(ZERO), output_field=_MONEY)


def sales_discounts(start: date, end: date, limit: int = 20) -> dict:
    """
    What the period sold, what was given away, and through which door.

    ⚠️  **The same orders as every other sales figure** — `_sold_orders`, so
        cancelled and refunded orders are out and everything else is in.

    ⚠️  **"Gross" here is `Order.subtotal`, not `grand_total`.**

        `grand_total` carries tax and shipping, and it is what `/reports/sales/`
        and the Overview call "gross sales". Taking a discount percentage of that
        would divide by money that was never discountable. So the waterfall is
        spelled out and every step is returned:

            gross_before_discount − discount_total = net_after_discount
            net_after_discount + tax_total + shipping_total = invoiced_total

        and `invoiced_total` **is** the Sales tab's `gross_sales` (the same sum of
        `grand_total` over the same orders), which is how the two screens meet.

    ⚠️  `unreconciled` is what the waterfall fails to explain — shown, never hidden.

        It is zero for every online order. It is not for a counter sale that
        carries a promotional price: `pos.services.quote` deducts only the
        cashier's manual percentage from the total while recording the line
        discount in `discount_total`, so the till charged more than this report
        says the customer should have paid. Folding that gap into one of the
        other figures would make the report agree with itself and disagree with
        the cash drawer.

    ⚠️  The discount is split by **what the order recorded**, no further:

            coupon          `coupon_discount` of an ordinary campaign coupon
            loyalty_points  `coupon_discount` of a personal coupon (`Coupon.owner`
                            is set) — loyalty turns points into one, nothing else does
            item_promotion  Σ `OrderLine.discount_amount` (a `PriceOverride`)
            manual          the remainder: the discount the cashier typed at the till

        `manual` is derived, so any discount the order cannot attribute lands there
        rather than vanishing; the four always add up to `discount_total`.

    ⚠️  **Discounts that no order records cannot be reported.**

            · a price-list price (student · wholesale): `list_price` is copied from
              the already-resolved `unit_price`, so the saving against the base
              price is never stored
            · a FREE_SHIPPING coupon: it waives the fee but writes no amount —
              `shipping_discount` is set only by the store-wide free-shipping rule

        The first is simply absent from every figure here. The second shows as a
        coupon order with a zero discount. `shipping_waived` is a memo of the
        rule's waiver and sits **outside** the product discount: it is not part
        of `subtotal`, so adding it would break the waterfall above.

    ⚠️  A coupon is identified by its **redemption**, not by `Order.coupon_code`.

        The cart keeps its code even when the code stops being valid at checkout,
        so an order can carry a code and no discount. The redemption is written
        only when the coupon was actually applied. The per-coupon table lists
        ordinary coupons only: each loyalty coupon is a single-use code, and one
        row per customer redeeming points would bury the campaigns the table is
        read for (their total is on the `loyalty_points` line instead). An order
        discounted by a coupon that has no redemption row — which no current
        write path produces — is therefore in `by_source` and not in `by_coupon`.
    """
    from orders.models import OrderLine
    from promotions.models import Coupon, CouponRedemption

    assert_period(start, end)

    sold = _sold_orders(start, end)

    redemption = CouponRedemption.objects.filter(order_ref=OuterRef("pk"), is_cancelled=False)
    tagged = sold.annotate(
        has_redemption=Exists(redemption),
        uses_points=Exists(redemption.filter(coupon__owner__isnull=False)),
    )

    totals = tagged.aggregate(
        orders=Count("pk"),
        discounted=Count("pk", filter=Q(discount_total__gt=0)),
        with_coupon=Count("pk", filter=Q(has_redemption=True) | Q(coupon_discount__gt=0)),
        subtotal=_total("subtotal"),
        discount=_total("discount_total"),
        coupon=_total("coupon_discount"),
        points=_total("coupon_discount", only=Q(uses_points=True)),
        tax=_total("tax_total"),
        shipping=_total("shipping_total"),
        shipping_waived=_total("shipping_discount"),
        invoiced=_total("grand_total"),
    )

    gross = quantize(totals["subtotal"])
    discount = quantize(totals["discount"])
    net = quantize(gross - discount)
    tax = quantize(totals["tax"])
    shipping = quantize(totals["shipping"])
    invoiced = quantize(totals["invoiced"])

    coupon_all = quantize(totals["coupon"])
    points = quantize(totals["points"])
    item_promotion = _money(OrderLine.objects.filter(order__in=sold), "discount_amount")
    amounts = {
        "coupon": quantize(coupon_all - points),
        "loyalty_points": points,
        "item_promotion": item_promotion,
        "manual": quantize(discount - coupon_all - item_promotion),
    }

    # ── By coupon ──────────────────────────────────────────
    per_coupon = (
        tagged.filter(has_redemption=True, uses_points=False)
        .annotate(
            # ⚠️  `output_field` is explicit: without it SQLite returns the raw 32-digit hex
            #     string instead of a UUID and no row matches the coupon it is looked up by.
            coupon_ref=Subquery(redemption.values("coupon_id")[:1], output_field=UUIDField())
        )
        .values("coupon_ref")
        .annotate(
            orders=Count("pk"),
            gross=Sum("subtotal"),
            given=Sum("coupon_discount"),
            net=Sum(_NET_OF_DISCOUNT),
        )
        .order_by("-given", "-orders")
    )
    coupon_rows = list(per_coupon[:limit])
    coupons = Coupon.all_objects.in_bulk([row["coupon_ref"] for row in coupon_rows])

    by_coupon = []
    for row in coupon_rows:
        coupon = coupons.get(row["coupon_ref"])
        row_gross = quantize(row["gross"] or ZERO)
        row_given = quantize(row["given"] or ZERO)
        by_coupon.append(
            {
                "coupon": str(row["coupon_ref"]),
                # ⚠️  A coupon deleted since the sale still has its orders in the period.
                "code": coupon.code if coupon else "—",
                "name_ar": coupon.name_ar if coupon else "",
                "name_en": coupon.name_en if coupon else "",
                "kind": coupon.kind if coupon else "",
                "holder_name": coupon.holder_name if coupon else "",
                "orders": row["orders"],
                "gross": str(row_gross),
                "discount": str(row_given),
                "discount_percent": str(percentage_of(row_given, row_gross)),
                # After *every* discount on those orders, not only this coupon's
                "net": str(quantize(row["net"] or ZERO)),
            }
        )

    # ── By day ─────────────────────────────────────────────
    # ⚠️  One aggregated query, and only days with a sale — like `sales_by_day`.
    days = (
        sold.annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(orders=Count("id"), gross=Sum("subtotal"), given=Sum("discount_total"))
        .order_by("day")
    )
    by_day = []
    for row in days:
        day_gross = quantize(row["gross"] or ZERO)
        day_given = quantize(row["given"] or ZERO)
        by_day.append(
            {
                "day": row["day"].isoformat(),
                "orders": row["orders"],
                "gross": str(day_gross),
                "discount": str(day_given),
                "net": str(quantize(day_gross - day_given)),
            }
        )

    return {
        "start": str(start),
        "end": str(end),
        "orders_count": totals["orders"],
        "discounted_orders": totals["discounted"],
        "coupon_orders": totals["with_coupon"],
        "coupons_used": per_coupon.count(),
        "gross_before_discount": str(gross),
        "discount_total": str(discount),
        "discount_percent": str(percentage_of(discount, gross)),
        "net_after_discount": str(net),
        "tax_total": str(tax),
        "shipping_total": str(shipping),
        "invoiced_total": str(invoiced),
        "unreconciled": str(quantize(invoiced - (net + tax + shipping))),
        "shipping_waived": str(quantize(totals["shipping_waived"])),
        "by_source": [
            {
                "source": source,
                "amount": str(amounts[source]),
                "share": str(percentage_of(amounts[source], discount)),
            }
            for source in DISCOUNT_SOURCES
        ],
        "by_coupon": by_coupon,
        "by_day": by_day,
    }


# ═══════════════════════════════════════════════════════════
#  Peak hours
# ═══════════════════════════════════════════════════════════


#: The days of the week in ISO order — Monday 1 and Sunday 7.
WEEKDAY_NAMES = {
    1: ("الاثنين", "Monday"),
    2: ("الثلاثاء", "Tuesday"),
    3: ("الأربعاء", "Wednesday"),
    4: ("الخميس", "Thursday"),
    5: ("الجمعة", "Friday"),
    6: ("السبت", "Saturday"),
    7: ("الأحد", "Sunday"),
}


def peak_hours(start: date, end: date) -> dict:
    """
    The distribution of orders across the hours of the week — 168 cells (7 days × 24 hours).

    ⚠️  **In local time, not UTC.**

        "The busiest hour is 17:00 UTC" is not a figure a shift rota in Cairo can
        be built on. `Extract` converts to the effective timezone automatically
        when `USE_TZ` is set, and the timezone is read from the settings.

    ⚠️  And the grid is **always complete**.

        The query returns no row for an hour with no orders, and a heatmap with
        missing cells renders distorted. The zeros are filled in here once,
        rather than in every frontend consuming the report.

    ⚠️  And the basis is **the order's creation time**, not the payment or
        delivery time.

        The load we are measuring is the load on the store and the stock at the
        moment of purchase; delivery time measures load on shipping — a
        different question.
    """
    assert_period(start, end)

    rows = (
        _sold_orders(start, end)
        .annotate(weekday=ExtractIsoWeekDay("created_at"), hour=ExtractHour("created_at"))
        .values("weekday", "hour")
        .annotate(orders=Count("id"), total=Sum("grand_total"))
    )

    grid = {(row["weekday"], row["hour"]): row for row in rows}

    cells = []
    for weekday in range(1, 8):
        for hour in range(24):
            row = grid.get((weekday, hour))
            cells.append(
                {
                    "weekday": weekday,
                    "hour": hour,
                    "orders": row["orders"] if row else 0,
                    "total": str(quantize(row["total"] or ZERO)) if row else str(ZERO),
                }
            )

    def _rollup(key: str, span) -> list[dict]:
        totals = {value: {"orders": 0, "total": ZERO} for value in span}
        for cell in cells:
            bucket = totals[cell[key]]
            bucket["orders"] += cell["orders"]
            bucket["total"] += Decimal(cell["total"])

        return [
            {
                key: value,
                "orders": bucket["orders"],
                "total": str(quantize(bucket["total"])),
                **(
                    {
                        "name_ar": WEEKDAY_NAMES[value][0],
                        "name_en": WEEKDAY_NAMES[value][1],
                    }
                    if key == "weekday"
                    else {}
                ),
            }
            for value, bucket in totals.items()
        ]

    by_hour = _rollup("hour", range(24))
    by_weekday = _rollup("weekday", range(1, 8))

    def _busiest(rows_: list[dict]) -> dict | None:
        # ⚠️  A period with no orders returns `None` rather than the first cell at zero —
        #     "your peak is Monday 12am with zero orders" is worse than no answer.
        top = max(rows_, key=lambda item: item["orders"], default=None)
        return top if top and top["orders"] else None

    return {
        "start": str(start),
        "end": str(end),
        "timezone": str(timezone.get_current_timezone()),
        "orders_count": sum(cell["orders"] for cell in cells),
        "cells": cells,
        "by_hour": by_hour,
        "by_weekday": by_weekday,
        "peak_cell": _busiest(cells),
        "peak_hour": _busiest(by_hour),
        "peak_weekday": _busiest(by_weekday),
    }


# ═══════════════════════════════════════════════════════════
#  Stock
# ═══════════════════════════════════════════════════════════


def inventory_summary() -> dict:
    """
    ⚠️  **Stock value at cost, not at the selling price.**

        Valuing at the selling price shows unrealised profit as though it were
        an owned asset — a fundamental accounting error, and a figure sometimes
        presented to a bank.
    """
    from inventory.models import Batch, Stock

    batches = Batch.objects.filter(quantity_remaining__gt=0)

    value = batches.aggregate(
        total=Coalesce(
            Sum(F("quantity_remaining") * F("unit_cost")),
            Value(ZERO),
            output_field=DecimalField(max_digits=18, decimal_places=2),
        )
    )["total"]

    below_reorder = Stock.objects.filter(quantity_physical__lte=F("reorder_point")).count()

    return {
        "stock_value_at_cost": str(quantize(value)),
        "batches": batches.count(),
        "products_below_reorder": below_reorder,
        "products_out_of_stock": Stock.objects.filter(quantity_physical=0).count(),
    }


def expiry_report(days: int = 90, limit: int = 100) -> list[dict]:
    """
    Batches approaching expiry.

    ⚠️  **The expired are included too, not excluded.**

        Excluding them makes the screen show what "will expire" and hide what
        **has expired and is still in the warehouse** — which is the more
        dangerous: goods that might be sold.
    """
    from inventory.models import Batch

    horizon = timezone.localdate() + timedelta(days=days)

    rows = (
        Batch.objects.filter(
            quantity_remaining__gt=0,
            expires_at__isnull=False,
            expires_at__lte=horizon,
        )
        .select_related("product", "location")
        .order_by("expires_at")[:limit]
    )

    today = timezone.localdate()
    return [
        {
            "batch": batch.number,
            "product": str(batch.product_id),
            "sku": batch.product.sku,
            "name_ar": batch.product.name_ar,
            "name_en": batch.product.name_en,
            "location": batch.location.code,
            "quantity": batch.quantity_remaining,
            "expires_at": batch.expires_at.isoformat(),
            "days_left": (batch.expires_at - today).days,
            # ⚠️  An explicit marker: the expired is highlighted rather than read as "approaching"
            "is_expired": batch.expires_at < today,
            "value_at_cost": str(quantize(batch.quantity_remaining * batch.unit_cost)),
        }
        for batch in rows
    ]


# ═══════════════════════════════════════════════════════════
#  Customer behaviour
# ═══════════════════════════════════════════════════════════


def customer_behaviour(start: date, end: date, limit: int = 20) -> dict:
    """
    ⚠️  **A new customer is measured by their first order, not by their registration date.**

        Someone who registered a year ago and bought today for the first time is
        commercially a new customer; counting them as existing makes every
        marketing campaign look ineffective.
    """
    from customers.models import CustomerProfile

    assert_period(start, end)

    sold = _sold_orders(start, end)

    new_customers = CustomerProfile.objects.filter(
        first_order_at__date__gte=start, first_order_at__date__lte=end
    ).count()

    # ⚠️  Accounts *and* guests (by email), and never the NULL group: a counter
    #     sale or a guest order used to add one phantom "customer" to these figures.
    returning = guest_services.count_returning_buyers(sold)

    top = (
        CustomerProfile.objects.filter(orders__in=sold)
        .annotate(period_total=Sum("orders__grand_total"), period_orders=Count("orders"))
        .order_by("-period_total")[:limit]
    )

    return {
        "new_customers": new_customers,
        "returning_customers": returning,
        "active_customers": guest_services.count_distinct_buyers(sold),
        # Of those, how many bought without an account (a subset, shown separately)
        "guest_customers": guest_services.count_guest_buyers(sold),
        "top_customers": [
            {
                "customer": str(profile.pk),
                "customer_number": profile.customer_number,
                "name": profile.display_name,
                "orders": profile.period_orders,
                "total": str(quantize(profile.period_total or ZERO)),
            }
            for profile in top
        ],
    }


def segment_breakdown(start: date, end: date) -> list[dict]:
    from customers.models import CustomerProfile

    assert_period(start, end)

    rows = (
        CustomerProfile.objects.filter(orders__in=_sold_orders(start, end))
        .values("segment")
        .annotate(customers=Count("id", distinct=True), total=Sum("orders__grand_total"))
        .order_by("-total")
    )

    return [
        {
            "segment": row["segment"],
            "customers": row["customers"],
            "total": str(quantize(row["total"] or ZERO)),
        }
        for row in rows
    ]


# ═══════════════════════════════════════════════════════════
#  Employee and supplier performance
# ═══════════════════════════════════════════════════════════


def employee_leaderboard(start: date, end: date, limit: int = 20) -> list[dict]:
    """
    ⚠️  What is attributed is `owner_employee`, not `created_by` — the same
        definition as `employees.services.performance`, and any difference
        between them makes the rep see two contradictory figures on two screens.
    """
    from employees.models import EmployeeProfile

    assert_period(start, end)

    sold = _sold_orders(start, end)

    rows = (
        EmployeeProfile.objects.filter(user__orders_owned__in=sold)
        .annotate(
            orders=Count("user__orders_owned", distinct=True),
            total=Sum("user__orders_owned__grand_total"),
        )
        .select_related("user", "role")
        .order_by("-total")[:limit]
    )

    return [
        {
            "employee": str(profile.pk),
            "employee_number": profile.employee_number,
            "name": profile.user.full_name,
            "role": profile.role.name_ar,
            "orders": profile.orders,
            "total": str(quantize(profile.total or ZERO)),
        }
        for profile in rows
    ]


def supplier_purchases(start: date, end: date, limit: int = 20) -> list[dict]:
    """What we bought from each supplier — from the purchase orders sent."""
    from suppliers.models import PurchaseOrder, PurchaseOrderStatus

    assert_period(start, end)

    rows = (
        PurchaseOrder.objects.filter(
            created_at__date__gte=start,
            created_at__date__lte=end,
        )
        .exclude(status__in=[PurchaseOrderStatus.DRAFT, PurchaseOrderStatus.CANCELLED])
        .values("supplier_id", "supplier__name_ar", "supplier__name_en")
        .annotate(orders=Count("id"), total=Sum("subtotal"))
        .order_by("-total")[:limit]
    )

    return [
        {
            "supplier": str(row["supplier_id"]),
            "name_ar": row["supplier__name_ar"],
            "name_en": row["supplier__name_en"],
            "orders": row["orders"],
            "total": str(quantize(row["total"] or ZERO)),
        }
        for row in rows
    ]


# ═══════════════════════════════════════════════════════════
#  The combined dashboard
# ═══════════════════════════════════════════════════════════


def overview(start: date, end: date) -> dict:
    """
    ⚠️  **The profit is read from `finance`, not computed here.**

        Computing it again produces a figure that contradicts the profit
        statement, and nobody knows which to believe — the same principle that
        prevented the cost being computed in `commissions`.
    """
    from finance import services as finance_services

    assert_period(start, end)

    sales = sales_summary(start, end)
    pnl = finance_services.profit_and_loss(start, end)

    return {
        "start": str(start),
        "end": str(end),
        "orders_count": sales.orders_count,
        "gross_sales": str(sales.gross_sales),
        "returns_total": str(sales.returns_total),
        "net_sales": str(sales.net_sales),
        "average_order": str(sales.average_order),
        "customers_count": sales.customers_count,
        # From `finance` — one source for profit
        "cogs": str(pnl.cogs),
        "gross_profit": str(pnl.gross_profit),
        "gross_margin": str(pnl.gross_margin),
        "expenses": str(pnl.expenses),
        "net_profit": str(pnl.net_profit),
        "profit_is_reliable": pnl.is_reliable,
        "inventory": inventory_summary(),
        # ⚠️  Five, not twenty — this is a dashboard, not a report. The full list
        #     lives in `/reports/sales/` with its sorting and its limit.
        "top_products": top_products(start, end, limit=5),
    }
