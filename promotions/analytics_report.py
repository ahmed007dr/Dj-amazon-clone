"""
Coupon analytics, part three — the pieces the report screens are built from:
the discount-volume series by buyer type, the customers list and the holder roll-up.

The rules (what counts, who is a registered buyer or a guest, who is new) live in
`promotions.analytics` and `promotions.analytics_customers`; this module only shapes
their results.
"""

from __future__ import annotations

import datetime as dt

from django.apps import apps
from django.db.models import (
    Case,
    CharField,
    Count,
    IntegerField,
    Max,
    Min,
    Q,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Lower, TruncDate, TruncMonth
from django.utils import timezone

from core.errors import BusinessError, ErrorCode
from core.money import ZERO, quantize
from promotions import analytics
from promotions.analytics import _gross_expr, _is_sale_q, _net_expr, tagged_orders
from promotions.analytics_customers import (
    GUEST,
    KINDS,
    REGISTERED,
    TYPE_LABELS,
    Breakdown,
    identified_orders,
)

# ═══════════════════════════════════════════════════════════
#  Discount volume over time, by buyer type
# ═══════════════════════════════════════════════════════════


def _point(date: dt.date) -> dict:
    return {
        "date": date.isoformat(),
        "orders": 0,
        "discount": ZERO,
        "net_sales": ZERO,
        REGISTERED: {"orders": 0, "discount": ZERO, "net_sales": ZERO},
        GUEST: {"orders": 0, "discount": ZERO, "net_sales": ZERO},
    }


def discount_series(coupon_ids, date_from=None, date_to=None) -> dict:
    """
    Orders, discount given and net sales per day (per month for a long range), **split
    by buyer type** — the chart behind "how much discount did we give, and to whom".

    ⚠️  `coupon_ids=None` is every coupon. Gaps are filled with zeros (a quiet week is
        part of the story), and the bucket is the order's day, like `analytics.series`.
    """
    if coupon_ids is not None:
        coupon_ids = list(coupon_ids)

    scoped = analytics._redemptions(coupon_ids, date_from, date_to)
    bounds = scoped.aggregate(first=Min("created_at"), last=Max("created_at"))
    first, last_seen = bounds["first"], bounds["last"]

    start = date_from or (analytics._as_date(timezone.localtime(first)) if first else None)
    end = date_to or (analytics._as_date(timezone.localtime(last_seen)) if last_seen else None)
    if start is None or end is None:
        return {"granularity": "day", "points": []}

    monthly = (end - start).days > analytics.DAILY_LIMIT_DAYS
    bucket = TruncMonth("created_at") if monthly else TruncDate("created_at")

    points: dict[dt.date, dict] = {}
    rows = (
        tagged_orders(coupon_ids, date_from, date_to)
        .filter(_is_sale_q())
        .order_by()
        .annotate(
            bucket=bucket,
            kind=Case(
                When(customer_id__isnull=True, then=Value(GUEST)),
                default=Value(REGISTERED),
                output_field=CharField(),
            ),
        )
        .values("bucket", "kind")
        .annotate(n=Count("pk"), discount=Sum("coupon_discount"), net=Sum(_net_expr()))
    )
    for row in rows:
        day = analytics._as_date(row["bucket"])
        point = points.setdefault(day, _point(day))
        part = point[row["kind"]]
        for target in (part, point):
            target["orders"] += row["n"]
            target["discount"] += row["discount"] or ZERO
            target["net_sales"] += row["net"] or ZERO

    result = []
    cursor = analytics._month_start(start) if monthly else start
    last = analytics._month_start(end) if monthly else end
    while cursor <= last:
        point = points.get(cursor) or _point(cursor)
        for target in (point, point[REGISTERED], point[GUEST]):
            target["discount"] = quantize(target["discount"])
            target["net_sales"] = quantize(target["net_sales"])
        result.append(point)
        cursor = analytics._next_month(cursor) if monthly else cursor + dt.timedelta(days=1)

    return {"granularity": "month" if monthly else "day", "points": result}


# ═══════════════════════════════════════════════════════════
#  The customers list
# ═══════════════════════════════════════════════════════════

#: `?ordering=` key -> the annotation it sorts by
CUSTOMER_ORDERING = {
    "net_sales": "net",
    "gross_sales": "gross",
    "discount": "discount",
    "orders": "orders",
    "first_used_at": "first_at",
    "last_used_at": "last_at",
    "name": "sort_name",
    "customer_type": "is_guest_buyer",
}

_ONE_IF_GUEST = Case(
    When(customer_id__isnull=True, then=Value(1)), default=Value(0), output_field=IntegerField()
)


def customers_queryset(
    coupon,
    date_from=None,
    date_to=None,
    *,
    search="",
    ordering="-net_sales",
    kind=None,
    new=None,
):
    """
    One row per buyer who used the coupon (counted orders only), ready to paginate.

    `kind`: 'registered' / 'guest'. `new`: True / False for new / returning buyers.
    Search is applied *after* the grouping (HAVING) on name, e-mail and phone, so a
    buyer's totals never shrink because only some of their orders matched.
    """
    key = ordering.lstrip("-")
    if key not in CUSTOMER_ORDERING:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="ترتيب غير مدعوم")

    # `coupon` is one coupon (the drawer) or a list of ids (the export: one row per coupon
    # and buyer, in a single query, whatever the number of coupons).
    many = isinstance(coupon, list | tuple | set)
    queryset = identified_orders(list(coupon) if many else [coupon.pk], date_from, date_to)
    if kind == REGISTERED:
        queryset = queryset.filter(customer_id__isnull=False)
    elif kind == GUEST:
        queryset = queryset.filter(customer_id__isnull=True)

    extra = {}
    if "is_guest" in analytics._link_guest_fields():
        extra["link_guest_any"] = Max(
            Case(
                When(link_is_guest=True, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )

    queryset = (
        queryset.order_by()
        .values(*(("coupon_ref",) if many else ()), "customer_id", "guest_key")
        .annotate(
            orders=Count("pk"),
            gross=Sum(_gross_expr()),
            discount=Sum("coupon_discount"),
            net=Sum(_net_expr()),
            first_at=Min("created_at"),
            last_at=Max("created_at"),
            new_flag=Max("first_flag"),
            claimed_any=Max("claimed_at"),
            c_number=Max("customer__customer_number"),
            c_name_ar=Max("customer__display_name_ar"),
            c_first=Max("customer__user__first_name"),
            c_last=Max("customer__user__last_name"),
            c_email=Max("customer__user__email"),
            c_phone=Max("customer__user__phone"),
            g_name=Max("recipient_name"),
            g_email=Max("buyer_email"),
            g_phone=Max("buyer_phone"),
            sort_name=Max(
                Case(
                    When(customer_id__isnull=False, then="customer__display_name_ar"),
                    default="recipient_name",
                    output_field=CharField(),
                )
            ),
            is_guest_buyer=Max(_ONE_IF_GUEST),
            **extra,
        )
    )

    if new is not None:
        queryset = queryset.filter(new_flag=1 if new else 0)

    if term := (search or "").strip():
        queryset = queryset.filter(
            Q(c_name_ar__icontains=term)
            | Q(c_first__icontains=term)
            | Q(c_last__icontains=term)
            | Q(c_email__icontains=term)
            | Q(c_phone__icontains=term)
            | Q(g_name__icontains=term)
            | Q(g_email__icontains=term)
            | Q(g_phone__icontains=term)
        )

    column = CUSTOMER_ORDERING[key]
    sign = "-" if ordering.startswith("-") else ""
    # The tie-breakers make the order total, so a page never repeats or skips a row.
    return queryset.order_by(
        f"{sign}{column}", *(("coupon_ref",) if many else ()), "customer_id", "guest_key"
    )


def account_emails(emails) -> set[str]:
    """Which of these (lower-cased) e-mails belong to an account today — one query."""
    emails = {email for email in emails if email}
    if not emails:
        return set()
    user_model = apps.get_model("accounts", "User")
    return set(
        user_model.objects.annotate(_email=Lower("email"))
        .filter(_email__in=emails)
        .values_list("_email", flat=True)
    )


def customer_rows(rows: list[dict]) -> list[dict]:
    """
    Shape one page of `customers_queryset` for the API.

    ⚠️  `customer_type` is who owns the orders in the report (REGISTERED when an account
        is attached); `purchased_as` is how the purchase was made (GUEST also for a
        guest order that has since been claimed). `has_account_now` is true for a
        registered buyer and for a guest whose e-mail has an account today. One query
        looks the page's guest e-mails up — not one per row.
    """
    guest_emails = {
        (row["g_email"] or "").lower()
        for row in rows
        if row["customer_id"] is None and row["g_email"]
    }
    accounts = account_emails(guest_emails)

    result = []
    for row in rows:
        registered = row["customer_id"] is not None
        full_name = f"{row['c_first'] or ''} {row['c_last'] or ''}".strip()
        email = (row["c_email"] if registered else row["g_email"]) or row["g_email"] or ""
        phone = (row["c_phone"] if registered else row["g_phone"]) or row["g_phone"] or ""
        name = (row["c_name_ar"] or full_name or row["g_name"]) if registered else row["g_name"]
        bought_as_guest = (
            not registered or row["claimed_any"] is not None or bool(row.get("link_guest_any"))
        )
        result.append(
            {
                "customer_key": f"c:{row['customer_id']}"
                if registered
                else f"g:{row['guest_key']}",
                "customer_type": TYPE_LABELS[REGISTERED if registered else GUEST],
                "purchased_as": TYPE_LABELS[GUEST if bought_as_guest else REGISTERED],
                "has_account_now": registered or email.lower() in accounts,
                "customer_id": row["customer_id"],
                "customer_number": row["c_number"] if registered else None,
                "name": name or "",
                "email": email,
                "phone": phone,
                "orders": row["orders"],
                "gross_sales": quantize(row["gross"] or ZERO),
                "net_sales": quantize(row["net"] or ZERO),
                "discount": quantize(row["discount"] or ZERO),
                "first_used_at": row["first_at"],
                "last_used_at": row["last_at"],
                "is_new_customer": bool(row["new_flag"]),
            }
        )
    return result


# ═══════════════════════════════════════════════════════════
#  Members: the account that owns a personal coupon
# ═══════════════════════════════════════════════════════════


def owner_payload(coupon) -> dict | None:
    """
    The member a coupon is personal to (`Coupon.owner`), as a "who distributed this" hint.

    ⚠️  Read from `coupon.owner` — callers `select_related("owner")` so a list of
        coupons costs no query per row.
    """
    if coupon.owner_id is None:
        return None
    owner = coupon.owner
    name = f"{owner.first_name} {owner.last_name}".strip()
    return {
        "id": owner.pk,
        "name": name or owner.email,
        "email": owner.email,
        "account_type": owner.account_type,
    }


def _owners(coupons) -> list[dict]:
    """The members (coupon owners) behind a holder's codes, each with the codes they own."""
    owners: dict = {}
    for coupon in coupons:
        payload = owner_payload(coupon)
        if payload is None:
            continue
        entry = owners.setdefault(payload["id"], {**payload, "codes": []})
        entry["codes"].append(coupon.code)
    return list(owners.values())


# ═══════════════════════════════════════════════════════════
#  The holder roll-up
# ═══════════════════════════════════════════════════════════

_COUNT_SUMS = (
    "times_used",
    "cancelled_redemptions",
    "cancelled_orders",
    "refunded_orders",
    "failed_orders",
)


def holder_rows(coupons, stats: dict, breakdown: Breakdown) -> list[dict]:
    """
    One row per holder: every code they hold, combined.

    ⚠️  Holders are matched by trimmed, case-insensitive name. Coupons with no holder
        are gathered in one `unassigned` row (so the rows still add up to the overall
        totals) — it only exists when such coupons do.

    ⚠️  `customers` and the new / returning split are computed over the *union* of the
        holder's codes: someone who used two of a holder's codes is one customer of
        that holder.
    """
    groups: dict[str, dict] = {}
    for coupon in coupons:
        name = (coupon.holder_name or "").strip()
        group = groups.setdefault(
            name.casefold(), {"holder_name": name, "unassigned": not name, "coupons": []}
        )
        group["coupons"].append(coupon)

    rows = []
    for group in groups.values():
        members = group["coupons"]
        ids = [coupon.pk for coupon in members]
        block = breakdown.block(ids)
        registered = block["by_customer_type"][REGISTERED]
        guest = block["by_customer_type"][GUEST]

        row = {
            "holder_name": group["holder_name"],
            "unassigned": group["unassigned"],
            "coupons": len(members),
            "codes": [
                {"id": coupon.pk, "code": coupon.code, "is_running": coupon.is_running}
                for coupon in members
            ],
            "members": _owners(members),
        }
        for key in _COUNT_SUMS:
            row[key] = sum(stats[pk][key] for pk in ids)
        row["refunded_amount"] = quantize(sum((stats[pk]["refunded_amount"] for pk in ids), ZERO))

        row["orders"] = registered["orders"] + guest["orders"]
        row["registered_orders"] = registered["orders"]
        row["guest_orders"] = guest["orders"]
        row["customers"] = registered["customers"] + guest["customers"]
        row["gross_sales"] = quantize(registered["gross"] + guest["gross"])
        row["discount_given"] = quantize(registered["discount"] + guest["discount"])
        row["net_sales"] = quantize(registered["net"] + guest["net"])
        row["order_total"] = quantize(registered["order_total"] + guest["order_total"])
        row["average_order_value"] = (
            quantize(row["order_total"] / row["orders"]) if row["orders"] else ZERO
        )
        firsts = [stats[pk]["first_used_at"] for pk in ids if stats[pk]["first_used_at"]]
        lasts = [stats[pk]["last_used_at"] for pk in ids if stats[pk]["last_used_at"]]
        row["first_used_at"] = min(firsts) if firsts else None
        row["last_used_at"] = max(lasts) if lasts else None
        row.update(block)
        rows.append(row)

    return rows


__all__ = [
    "CUSTOMER_ORDERING",
    "KINDS",
    "account_emails",
    "customer_rows",
    "customers_queryset",
    "discount_series",
    "holder_rows",
    "owner_payload",
]
