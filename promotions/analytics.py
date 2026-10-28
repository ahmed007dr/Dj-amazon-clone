"""
Coupon analytics — "how many times was it used, what was sold through it, who holds it".

⚠️  **What counts as a sale** (the one definition every figure here uses):

        an order that carries the coupon's redemption AND
          · is not CANCELLED         (the stock went back, the money never came)
          · is not REFUNDED          (the sale was reversed — reported apart)
          · has not FAILED payment   (the customer never paid for it)
          · whose redemption was not itself cancelled

    Everything else is *reported separately* (`cancelled_orders`, `refunded_orders`,
    `refunded_amount`, `failed_orders`) so the number the owner reads is trustworthy
    and the gap between "used" and "sold" is visible instead of silently absorbed.
    PENDING / CONFIRMED / PROCESSING / SHIPPED / DELIVERED / COMPLETED all count:
    the customer committed to the order, and the owner wants the volume the code
    brought in, not only what has already shipped. (This matches `reporting`'s
    own "sold order" rule — cancelled and refunded out, everything else in.)

⚠️  **The money columns** (all read from the order, all excluding tax and shipping
    except `order_total`):

        gross_sales     products after price-list / promo discounts, BEFORE the coupon
                          = Order.subtotal − (Order.discount_total − Order.coupon_discount)
        discount_given  Order.coupon_discount
        net_sales       products after the coupon          = gross_sales − discount_given
        order_total     Order.grand_total (what the customer pays, tax + shipping included)

    A FREE_SHIPPING coupon discounts no products, so its `discount_given` is zero —
    the waived shipping is not recorded on the order against a coupon.

⚠️  **How `promotions` reads `orders` without importing it.**

    `promotions` sits below `orders` in the layer contract (docs/backend/02-DEPENDENCIES.md,
    pyproject `[tool.importlinter]`): importing `orders.models` here would invert it.
    The models are resolved by name through the app registry (`apps.get_model`) — the
    same lazy lookup `administration/tax_api.py` uses for `catalog.Product` — so the
    dependency exists at run time as a *read* and in no import statement. The join
    key is `CouponRedemption.order_ref`, a typed copy of the order id.
    The status strings below are plain text for the same reason; a test pins them to
    `orders.models.OrderStatus` so they cannot drift.
"""

from __future__ import annotations

import datetime as dt
import itertools
from collections import defaultdict
from decimal import Decimal

from django.apps import apps
from django.db.models import (
    BooleanField,
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    Max,
    Min,
    OuterRef,
    Q,
    Subquery,
    Sum,
    UUIDField,
    Value,
)
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.utils import timezone

from core.errors import BusinessError, ErrorCode
from core.money import ZERO, quantize
from promotions.models import Coupon, CouponRedemption

# ═══════════════════════════════════════════════════════════
#  The definition of a sale
# ═══════════════════════════════════════════════════════════

#: Mirrors `orders.models.OrderStatus` / `PaymentStatus` — pinned by a test.
STATUS_CANCELLED = "CANCELLED"
STATUS_REFUNDED = "REFUNDED"
PAYMENT_FAILED = "FAILED"

#: Wide enough for any total the shop will ever produce (MoneyField is 12 digits).
_MONEY = DecimalField(max_digits=18, decimal_places=2)
_ZERO_VALUE = Value(Decimal("0.00"), output_field=_MONEY)


def _order_model():
    return apps.get_model("orders", "Order")


def _line_model():
    return apps.get_model("orders", "OrderLine")


# ═══════════════════════════════════════════════════════════
#  The period
# ═══════════════════════════════════════════════════════════


def parse_day(raw: str | None, *, label: str) -> dt.date | None:
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(str(raw))
    except ValueError as exc:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR, detail=f"{label}: صيغة التاريخ يجب أن تكون YYYY-MM-DD"
        ) from exc


def parse_period(params) -> tuple[dt.date | None, dt.date | None]:
    """
    `date_from` / `date_to` from a query dict — inclusive on both ends.

    ⚠️  An inverted range is refused: it would produce a table of zeros that looks
        exactly like "nobody used the code".
    """
    date_from = parse_day(params.get("date_from"), label="date_from")
    date_to = parse_day(params.get("date_to"), label="date_to")
    if date_from and date_to and date_from > date_to:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="بداية الفترة بعد نهايتها")
    return date_from, date_to


def _redemptions(coupon_ids, date_from, date_to):
    """The redemption rows in scope — `coupon_ids=None` means every coupon."""
    queryset = CouponRedemption.objects.all()
    if coupon_ids is not None:
        queryset = queryset.filter(coupon_id__in=coupon_ids)
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)
    return queryset


# ═══════════════════════════════════════════════════════════
#  Orders, tagged with the redemption they carry
# ═══════════════════════════════════════════════════════════


def _is_cancelled_q() -> Q:
    return Q(status=STATUS_CANCELLED) | Q(link_cancelled=True)


def _is_refunded_q() -> Q:
    return ~_is_cancelled_q() & Q(status=STATUS_REFUNDED)


def _is_failed_q() -> Q:
    return ~_is_cancelled_q() & ~Q(status=STATUS_REFUNDED) & Q(payment_status=PAYMENT_FAILED)


def _is_sale_q() -> Q:
    return ~_is_cancelled_q() & ~Q(status=STATUS_REFUNDED) & ~Q(payment_status=PAYMENT_FAILED)


def _gross_expr():
    return ExpressionWrapper(
        F("subtotal") - F("discount_total") + F("coupon_discount"), output_field=_MONEY
    )


def _net_expr():
    return ExpressionWrapper(F("subtotal") - F("discount_total"), output_field=_MONEY)


def tagged_orders(coupon_ids, date_from=None, date_to=None):
    """
    Orders that used a coupon in scope, annotated with the redemption they carry.

    ⚠️  One query shape for every figure — the single place the order ↔ redemption
        link is expressed. `coupon_ref` / `redeemer` / `link_cancelled` are correlated
        sub-selects on the indexed `order_ref`, so there is no per-row query.
    """
    link = CouponRedemption.objects.filter(order_ref=OuterRef("pk")).order_by("created_at")
    scoped = _redemptions(coupon_ids, date_from, date_to).filter(order_ref__isnull=False)

    return (
        _order_model()
        .objects.filter(pk__in=scoped.values("order_ref"))
        # ⚠️  `output_field` is explicit: without it SQLite hands back the raw 32-digit hex
        #     string instead of a UUID, the grouped rows stop matching the coupon ids
        #     they are looked up by, and every coupon silently reads as "no sales".
        .annotate(
            coupon_ref=Subquery(link.values("coupon_id")[:1], output_field=UUIDField()),
            redeemer=Subquery(link.values("user_id")[:1], output_field=UUIDField()),
            link_cancelled=Subquery(link.values("is_cancelled")[:1], output_field=BooleanField()),
        )
    )


def _sum(expression, condition) -> Coalesce:
    return Coalesce(Sum(expression, filter=condition), _ZERO_VALUE, output_field=_MONEY)


def _order_aggregates() -> dict:
    sale = _is_sale_q()
    return {
        "orders": Count("pk", filter=sale),
        "customers": Count("redeemer", filter=sale, distinct=True),
        "gross_sales": _sum(_gross_expr(), sale),
        "discount_given": _sum(F("coupon_discount"), sale),
        "net_sales": _sum(_net_expr(), sale),
        "order_total": _sum(F("grand_total"), sale),
        "cancelled_orders": Count("pk", filter=_is_cancelled_q()),
        "refunded_orders": Count("pk", filter=_is_refunded_q()),
        "refunded_amount": _sum(F("grand_total"), _is_refunded_q()),
        "failed_orders": Count("pk", filter=_is_failed_q()),
    }


_MONEY_KEYS = (
    "gross_sales",
    "discount_given",
    "net_sales",
    "order_total",
    "refunded_amount",
)
_COUNT_KEYS = ("orders", "customers", "cancelled_orders", "refunded_orders", "failed_orders")


def _finish(raw: dict | None) -> dict:
    """Quantised money, plain ints, and the average guarded against a division by zero."""
    raw = raw or {}
    row = {key: quantize(raw.get(key) or ZERO) for key in _MONEY_KEYS}
    row.update({key: int(raw.get(key) or 0) for key in _COUNT_KEYS})
    row["average_order_value"] = (
        quantize(row["order_total"] / row["orders"]) if row["orders"] else ZERO
    )
    return row


# ═══════════════════════════════════════════════════════════
#  Summaries
# ═══════════════════════════════════════════════════════════


def _redemption_stats(coupon_ids, date_from, date_to) -> dict:
    used = Q(is_cancelled=False)
    rows = (
        _redemptions(coupon_ids, date_from, date_to)
        .order_by()
        .values("coupon_id")
        .annotate(
            times_used=Count("pk", filter=used),
            cancelled_redemptions=Count("pk", filter=Q(is_cancelled=True)),
            first_used_at=Min("created_at", filter=used),
            last_used_at=Max("created_at", filter=used),
        )
    )
    return {row["coupon_id"]: row for row in rows}


def summaries(coupon_ids, date_from=None, date_to=None) -> dict:
    """
    `{coupon_id: summary}` for the given coupons — **two grouped queries, whatever the count.**

    ⚠️  This is the only place per-coupon figures are computed. The list column, the
        ranking, the drawer and the Excel export all call it, so the same coupon
        shows the same number everywhere.

    Coupons with no activity in the period are present with zeros.
    """
    if coupon_ids is not None:
        coupon_ids = list(coupon_ids)

    used = _redemption_stats(coupon_ids, date_from, date_to)

    sold = {
        row["coupon_ref"]: row
        for row in tagged_orders(coupon_ids, date_from, date_to)
        .order_by()
        .values("coupon_ref")
        .annotate(**_order_aggregates())
        if row["coupon_ref"] is not None
    }

    wanted = coupon_ids if coupon_ids is not None else set(used) | set(sold)
    result = {}
    for coupon_id in wanted:
        redemption = used.get(coupon_id, {})
        row = _finish(sold.get(coupon_id))
        row["times_used"] = int(redemption.get("times_used") or 0)
        row["cancelled_redemptions"] = int(redemption.get("cancelled_redemptions") or 0)
        row["first_used_at"] = redemption.get("first_used_at")
        row["last_used_at"] = redemption.get("last_used_at")
        result[coupon_id] = row
    return result


def totals(date_from=None, date_to=None) -> dict:
    """
    One row across **every** coupon.

    ⚠️  Not the sum of `summaries()`: `customers` is a distinct count, and a person
        who used two codes is one customer, not two.
    """
    used = Q(is_cancelled=False)
    redemptions = _redemptions(None, date_from, date_to).aggregate(
        times_used=Count("pk", filter=used),
        cancelled_redemptions=Count("pk", filter=Q(is_cancelled=True)),
        coupons_used=Count("coupon_id", filter=used, distinct=True),
        last_used_at=Max("created_at", filter=used),
    )
    orders = tagged_orders(None, date_from, date_to).aggregate(**_order_aggregates())

    row = _finish(orders)
    row.update(
        times_used=int(redemptions["times_used"] or 0),
        cancelled_redemptions=int(redemptions["cancelled_redemptions"] or 0),
        coupons_used=int(redemptions["coupons_used"] or 0),
        last_used_at=redemptions["last_used_at"],
    )
    return row


def coupon_counts() -> dict:
    """
    How many coupons exist and in which state — one aggregate query.

    ⚠️  The same predicates as `Coupon.is_running` / `is_expired`, expressed in SQL
        (the list endpoint's status filter does the same): counting in Python would
        load every coupon to answer a number.
    """
    now = timezone.now()
    live = Q(is_active=True, starts_at__lte=now) & (Q(ends_at__isnull=True) | Q(ends_at__gt=now))
    exhausted = Q(usage_limit__isnull=False, usage_count__gte=F("usage_limit"))

    row = Coupon.objects.aggregate(
        coupons=Count("pk"),
        running=Count("pk", filter=live & ~exhausted),
        exhausted=Count("pk", filter=live & exhausted),
        expired=Count("pk", filter=Q(ends_at__lte=now)),
        scheduled=Count("pk", filter=Q(starts_at__gt=now)),
        inactive=Count("pk", filter=Q(is_active=False)),
        with_holder=Count("pk", filter=~Q(holder_name="")),
    )
    return {key: int(value or 0) for key, value in row.items()}


def remaining_uses(coupon: Coupon, times_used_by_owner: int | None = None) -> dict:
    """
    What is left of a coupon's limits.

    ⚠️  `remaining_total` is None for an unlimited coupon — "no limit" must not be
        rendered as zero left. `owner_remaining` exists only for a personal coupon,
        where "how many more times can *they* use it" is a real question; for a
        general campaign the per-customer limit is a rule, not a balance.
    """
    remaining_total = (
        max(coupon.usage_limit - coupon.usage_count, 0) if coupon.usage_limit is not None else None
    )
    owner_remaining = None
    if coupon.owner_id is not None:
        used = (
            times_used_by_owner
            if times_used_by_owner is not None
            else CouponRedemption.objects.filter(
                coupon=coupon, user_id=coupon.owner_id, is_cancelled=False
            ).count()
        )
        owner_remaining = max(coupon.usage_limit_per_user - used, 0)

    return {
        "usage_limit": coupon.usage_limit,
        "usage_count": coupon.usage_count,
        "usage_limit_per_user": coupon.usage_limit_per_user,
        "remaining_total": remaining_total,
        "owner_remaining": owner_remaining,
    }


def customers_at_limit(coupon: Coupon) -> int:
    """How many customers have used this coupon up to their personal limit."""
    per_user = (
        CouponRedemption.objects.filter(coupon=coupon, is_cancelled=False)
        .order_by()
        .values("user_id")
        .annotate(n=Count("pk"))
        .filter(n__gte=coupon.usage_limit_per_user)
    )
    return per_user.count()


# ═══════════════════════════════════════════════════════════
#  The product breakdown
# ═══════════════════════════════════════════════════════════


def allocate(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """
    Split `total` across `weights` so the parts **add back to exactly `total`**.

    ⚠️  Largest-remainder, in whole piastres. Rounding each share on its own loses
        or invents a cent per line, and then the product table no longer sums to
        the discount the order actually gave — the one reconciliation an accountant
        will try first.
    """
    cents = int((total * 100).to_integral_value())
    weight_cents = [int((weight * 100).to_integral_value()) for weight in weights]
    weight_sum = sum(weight_cents)
    if cents <= 0 or weight_sum <= 0:
        return [ZERO for _ in weights]

    shares = [cents * weight // weight_sum for weight in weight_cents]
    remainders = [cents * weight % weight_sum for weight in weight_cents]

    leftover = cents - sum(shares)
    # Biggest remainder first; ties go to the earlier line so the result is deterministic
    for index in sorted(range(len(weights)), key=lambda i: (-remainders[i], i))[:leftover]:
        shares[index] += 1

    return [Decimal(share) / 100 for share in shares]


def _scope(coupon: Coupon) -> tuple[set, set]:
    return (
        set(coupon.products.values_list("id", flat=True)),
        set(coupon.categories.values_list("id", flat=True)),
    )


def product_breakdown(coupon: Coupon, date_from=None, date_to=None) -> list[dict]:
    """
    What the coupon's sales contained: one row per product (and colour/variant).

    ⚠️  **The order stores one discount, not one per line** — the coupon is applied to
        the order's eligible subtotal and `OrderLine.discount_amount` holds only the
        price-list / promo discount. So the per-product discount here is an
        *allocation*, pro-rata by each line's value after its own discount:

          · only lines the coupon applies to take a share (a coupon restricted to
            products / categories never "discounts" a line outside them);
          · if the scope was edited after the sale and no line matches any more, all
            lines share it, so the figures still add back to what the order gave;
          · shares are cut with largest-remainder, so they sum to the order's
            `coupon_discount` to the piastre.

        It is an attribution for reading, not a stored fact — the UI says so.

    Only counted sales (see the module docstring) take part. Sorted by revenue.
    """
    sales = tagged_orders([coupon.pk], date_from, date_to).filter(_is_sale_q())
    product_ids, category_ids = _scope(coupon)
    restricted = bool(product_ids or category_ids)

    lines = (
        _line_model()
        .objects.filter(order__in=sales.values("pk"))
        .order_by("order_id", "created_at", "pk")
        .values_list(
            "order_id",
            "product_id",
            "variant_id",
            "product_sku",
            "product_name_ar",
            "product_name_en",
            "variant_sku",
            "color_name_ar",
            "color_name_en",
            "color_hex",
            "quantity",
            "unit_price",
            "discount_amount",
            "product__category_id",
            "order__coupon_discount",
        )
        .iterator(chunk_size=2000)
    )

    rows: dict[tuple, dict] = {}

    for _order_id, group in itertools.groupby(lines, key=lambda line: line[0]):
        order_lines = list(group)
        order_discount = order_lines[0][14]

        values = [max(line[11] * line[10] - line[12], ZERO) for line in order_lines]
        if restricted:
            eligible = [
                line[1] in product_ids or (line[13] is not None and line[13] in category_ids)
                for line in order_lines
            ]
            if not any(eligible):
                eligible = [True] * len(order_lines)
        else:
            eligible = [True] * len(order_lines)

        shares = allocate(
            order_discount,
            [v if ok else ZERO for v, ok in zip(values, eligible, strict=True)],
        )

        for line, value, share in zip(order_lines, values, shares, strict=True):
            key = (line[1], line[2])
            row = rows.get(key)
            if row is None:
                row = rows[key] = {
                    "product": line[1],
                    "variant": line[2],
                    "sku": line[6] or line[3],
                    "product_sku": line[3],
                    "name_ar": line[4],
                    "name_en": line[5],
                    "color_name_ar": line[7],
                    "color_name_en": line[8],
                    "color_hex": line[9],
                    "units": 0,
                    "orders": set(),
                    "revenue": ZERO,
                    "discount": ZERO,
                }
            row["units"] += line[10]
            row["orders"].add(line[0])
            row["revenue"] += value
            row["discount"] += share

    result = []
    for row in rows.values():
        row["orders"] = len(row["orders"])
        row["revenue"] = quantize(row["revenue"])
        row["discount"] = quantize(row["discount"])
        row["net_revenue"] = quantize(row["revenue"] - row["discount"])
        result.append(row)

    result.sort(key=lambda item: (-item["revenue"], item["sku"]))
    return result


# ═══════════════════════════════════════════════════════════
#  The daily series
# ═══════════════════════════════════════════════════════════

#: Beyond this many days a chart of one bar per day is unreadable — switch to months.
DAILY_LIMIT_DAYS = 92


def _month_start(day: dt.date) -> dt.date:
    return day.replace(day=1)


def _next_month(day: dt.date) -> dt.date:
    return (day.replace(day=28) + dt.timedelta(days=4)).replace(day=1)


def _as_date(value) -> dt.date:
    return value.date() if isinstance(value, dt.datetime) else value


def series(coupon: Coupon, date_from=None, date_to=None) -> dict:
    """
    Uses and net sales per day (or per month for a long range) — for a small chart.

    ⚠️  Gaps are filled with zeros. A chart that only has the days something
        happened draws a campaign as one continuous busy line, and a quiet week
        is exactly what the owner wants to see.
    """
    scoped = _redemptions([coupon.pk], date_from, date_to)
    bounds = scoped.aggregate(first=Min("created_at"), last=Max("created_at"))

    first, last_seen = bounds["first"], bounds["last"]
    start = date_from or (_as_date(timezone.localtime(first)) if first else None)
    end = date_to or (_as_date(timezone.localtime(last_seen)) if last_seen else None)
    if start is None or end is None:
        return {"granularity": "day", "points": []}

    monthly = (end - start).days > DAILY_LIMIT_DAYS
    bucket = TruncMonth("created_at") if monthly else TruncDate("created_at")

    uses: dict[dt.date, int] = defaultdict(int)
    for row in (
        scoped.filter(is_cancelled=False)
        .order_by()
        .annotate(bucket=bucket)
        .values("bucket")
        .annotate(n=Count("pk"))
    ):
        uses[_as_date(row["bucket"])] += row["n"]

    sales: dict[dt.date, list] = defaultdict(lambda: [0, ZERO])
    for row in (
        tagged_orders([coupon.pk], date_from, date_to)
        .filter(_is_sale_q())
        .order_by()
        .annotate(bucket=bucket)
        .values("bucket")
        .annotate(n=Count("pk"), net=Sum(_net_expr()))
    ):
        key = _as_date(row["bucket"])
        sales[key][0] += row["n"]
        sales[key][1] += row["net"] or ZERO

    points = []
    cursor = _month_start(start) if monthly else start
    last = _month_start(end) if monthly else end
    while cursor <= last:
        orders_count, net = sales[cursor] if cursor in sales else (0, ZERO)
        points.append(
            {
                "date": cursor.isoformat(),
                "redemptions": uses.get(cursor, 0),
                "orders": orders_count,
                "net_sales": quantize(net),
            }
        )
        cursor = _next_month(cursor) if monthly else cursor + dt.timedelta(days=1)

    return {"granularity": "month" if monthly else "day", "points": points}


# ═══════════════════════════════════════════════════════════
#  The recent orders
# ═══════════════════════════════════════════════════════════


def mask_email(email: str) -> str:
    """`ahmed.k@gmail.com` becomes `a***@gmail.com` — enough to recognise, not to harvest."""
    if not email or "@" not in email:
        return ""
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def mask_phone(phone: str) -> str:
    digits = (phone or "").strip()
    return f"{'*' * max(len(digits) - 3, 0)}{digits[-3:]}" if len(digits) > 3 else ""


def orders_queryset(coupon: Coupon, date_from=None, date_to=None, *, only=None):
    """
    The coupon's orders, newest first, with the figures the list needs.

    `only`: 'sales' for the counted ones, 'excluded' for cancelled / refunded / failed.
    """
    queryset = tagged_orders([coupon.pk], date_from, date_to)
    if only == "sales":
        queryset = queryset.filter(_is_sale_q())
    elif only == "excluded":
        queryset = queryset.exclude(_is_sale_q())

    return (
        queryset.annotate(gross=_gross_expr(), net=_net_expr())
        .order_by("-created_at", "-pk")
        .values(
            "id",
            "number",
            "created_at",
            "status",
            "payment_status",
            "link_cancelled",
            "gross",
            "coupon_discount",
            "net",
            "grand_total",
            "customer__display_name_ar",
            "customer__user__first_name",
            "customer__user__last_name",
            "customer__user__email",
            "recipient_name",
            "recipient_phone",
            "contact_email",
            "channel",
        )
    )


def order_row(row: dict) -> dict:
    """One `orders_queryset` row, shaped for the API. Contact details are masked."""
    full_name = f"{row['customer__user__first_name']} {row['customer__user__last_name']}".strip()
    email = row["customer__user__email"] or row["contact_email"] or ""
    counted = not (
        row["status"] in (STATUS_CANCELLED, STATUS_REFUNDED)
        or row["payment_status"] == PAYMENT_FAILED
        or row["link_cancelled"]
    )
    return {
        "id": row["id"],
        "number": row["number"],
        "created_at": row["created_at"],
        "status": row["status"],
        "payment_status": row["payment_status"],
        "channel": row["channel"],
        "counted": counted,
        "customer_name": row["customer__display_name_ar"] or full_name or row["recipient_name"],
        "contact": mask_email(email) or mask_phone(row["recipient_phone"]),
        "gross_sales": quantize(row["gross"] or ZERO),
        "discount": quantize(row["coupon_discount"] or ZERO),
        "net_sales": quantize(row["net"] or ZERO),
        "order_total": quantize(row["grand_total"] or ZERO),
    }
