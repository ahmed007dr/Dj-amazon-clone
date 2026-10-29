"""
The referral MEMBERS report — "who invited the new customers, and what did they bring?"

One row per **referrer** (the member whose code was used), ranked. All of it is derived
from rows that already exist (`Referral`, the referees' orders, the points ledger);
nothing is stored for the report.

⚠️  **The period is a cohort**: `date_from` / `date_to` select the referrals *created* in
    that window (the day the invited customer signed up through the member's code). Every
    other figure describes that same cohort:

        invited          every referral in the window
        qualified        those whose referee placed the qualifying order (status REWARDED)
        pending          signed up, no qualifying order yet
        rejected         refused (suspected abuse)
        referee_orders   counted orders the invited customers placed (any date)
        referee_net_sales  those orders' products after discounts, before tax and shipping
        points_awarded   referral-reward points the *member* actually received for them

    "Counted orders" is exactly the coupon reports' rule (`promotions.analytics.plain_sale_q`):
    cancelled, refunded and payment-failed orders are not sales.

⚠️  Points come from the ledger (`PointsEntry`, kind REFERRAL, `reference = referral:<id>`),
    not from "programme points × rewarded referrals": the programme may have been edited
    since, and a member with no loyalty programme is rewarded nothing at all.

⚠️  **How `loyalty` reads `orders` and `accounts`.** Orders and users are resolved by name
    through the app registry (`apps.get_model`) — the same read-only pattern as
    `promotions.analytics` — so no model of another domain is imported here
    (docs/backend/02-DEPENDENCIES.md).
"""

from __future__ import annotations

from django.apps import apps
from django.db.models import Count, Max, Q, Sum
from django.db.models.functions import Coalesce

from core.errors import BusinessError, ErrorCode
from core.money import ZERO, quantize
from loyalty.models import PointsEntry, PointsKind, Referral, ReferralCode, ReferralStatus
from promotions.analytics import net_expr, plain_sale_q

#: Keys the ranking may be ordered by
ORDERING_KEYS = {
    "invited",
    "qualified",
    "pending",
    "rejected",
    "referee_orders",
    "referee_net_sales",
    "points_awarded",
    "last_invited_at",
    "conversion_rate",
}

_REFERENCE_CHUNK = 500


def rate(part: int, whole: int) -> float:
    """`part / whole` as a percentage with two decimals; 0 when there is nothing to divide."""
    return round(part * 100 / whole, 2) if whole else 0.0


def scope(date_from=None, date_to=None):
    """The referrals created inside the period (inclusive on both ends)."""
    queryset = Referral.objects.all()
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)
    return queryset


def _order_model():
    return apps.get_model("orders", "Order")


def _user_model():
    return apps.get_model("accounts", "User")


# ═══════════════════════════════════════════════════════════
#  The figures
# ═══════════════════════════════════════════════════════════


def blank() -> dict:
    return {
        "invited": 0,
        "qualified": 0,
        "pending": 0,
        "rejected": 0,
        "referee_orders": 0,
        "referee_net_sales": ZERO,
        "points_awarded": 0,
        "last_invited_at": None,
        "conversion_rate": 0.0,
    }


def referee_sales(referrals, *, by: str) -> dict:
    """
    `{key: (orders, net_sales)}` for the counted orders of the invited customers.

    `by` is the grouping column on the referral side: 'referrer_id' for the ranking,
    'pk' for the per-referee list. One grouped query either way.
    """
    path = f"customer__user__referred_by__{by}"
    rows = (
        _order_model()
        .objects.filter(plain_sale_q(), customer__user__referred_by__in=referrals)
        .order_by()
        .values(path)
        .annotate(orders=Count("pk"), net=Coalesce(Sum(net_expr()), ZERO))
    )
    return {row[path]: (row["orders"], row["net"] or ZERO) for row in rows}


def _points(referrals, stats: dict) -> None:
    """
    Add each member's referral-reward points to `stats`.

    ⚠️  Matched on the reference text `referral:<id>` the reward writes — and on the
        entry belonging to the *referrer's* account, since the referee gets an entry
        with the same reference. Chunked, so a long list never exceeds a database's
        parameter limit; the query count grows by one per 500 rewarded referrals.
    """
    owner = {
        f"referral:{pk}": referrer_id
        for pk, referrer_id in referrals.filter(status=ReferralStatus.REWARDED).values_list(
            "pk", "referrer_id"
        )
    }
    references = list(owner)
    for start in range(0, len(references), _REFERENCE_CHUNK):
        chunk = references[start : start + _REFERENCE_CHUNK]
        rows = PointsEntry.objects.filter(
            kind=PointsKind.REFERRAL, reference__in=chunk
        ).values_list("reference", "customer__user_id", "points")
        for reference, user_id, points in rows:
            if owner.get(reference) == user_id and user_id in stats:
                stats[user_id]["points_awarded"] += points


def member_stats(date_from=None, date_to=None) -> dict:
    """`{referrer_user_id: figures}` for every member who invited someone in the period."""
    referrals = scope(date_from, date_to)

    stats: dict = {}
    grouped = (
        referrals.order_by()
        .values("referrer_id")
        .annotate(
            invited=Count("pk"),
            qualified=Count("pk", filter=Q(status=ReferralStatus.REWARDED)),
            pending=Count("pk", filter=Q(status=ReferralStatus.PENDING)),
            rejected=Count("pk", filter=Q(status=ReferralStatus.REJECTED)),
            last_invited_at=Max("created_at"),
        )
    )
    for row in grouped:
        entry = blank()
        entry.update({key: row[key] for key in ("invited", "qualified", "pending", "rejected")})
        entry["last_invited_at"] = row["last_invited_at"]
        stats[row["referrer_id"]] = entry

    for referrer_id, (orders, net) in referee_sales(referrals, by="referrer_id").items():
        if referrer_id in stats:
            stats[referrer_id]["referee_orders"] = orders
            stats[referrer_id]["referee_net_sales"] = net

    _points(referrals, stats)

    for entry in stats.values():
        entry["referee_net_sales"] = quantize(entry["referee_net_sales"])
        entry["conversion_rate"] = rate(entry["qualified"], entry["invited"])
    return stats


def totals(stats: dict) -> dict:
    """The block above the table: what the whole programme brought, from the same rows."""
    invited = sum(entry["invited"] for entry in stats.values())
    qualified = sum(entry["qualified"] for entry in stats.values())
    return {
        "members": len(stats),
        "invited": invited,
        "qualified": qualified,
        "pending": sum(entry["pending"] for entry in stats.values()),
        "rejected": sum(entry["rejected"] for entry in stats.values()),
        "referee_orders": sum(entry["referee_orders"] for entry in stats.values()),
        "referee_net_sales": quantize(sum((e["referee_net_sales"] for e in stats.values()), ZERO)),
        "points_awarded": sum(entry["points_awarded"] for entry in stats.values()),
        "conversion_rate": rate(qualified, invited),
    }


# ═══════════════════════════════════════════════════════════
#  The people
# ═══════════════════════════════════════════════════════════


def _name(first: str, last: str, display: str, email: str) -> str:
    return display or f"{first or ''} {last or ''}".strip() or email


def referrers(ids) -> dict:
    """`{user_id: {id, name, email, account_type, code}}` — two queries for any number of ids."""
    ids = list(ids)
    if not ids:
        return {}

    people = {}
    users = (
        _user_model()
        .objects.filter(pk__in=ids)
        .values_list(
            "pk",
            "first_name",
            "last_name",
            "email",
            "account_type",
            "customer_profile__display_name_ar",
        )
    )
    for pk, first, last, email, account_type, display in users:
        people[pk] = {
            "id": pk,
            "name": _name(first, last, display, email),
            "email": email,
            "account_type": account_type,
            "code": "",
        }
    for user_id, code in ReferralCode.objects.filter(user_id__in=ids).values_list(
        "user_id", "code"
    ):
        if user_id in people:
            people[user_id]["code"] = code
    return people


def matching_referrers(term: str):
    """Ids of members whose name, e-mail or referral code contains `term`."""
    term = (term or "").strip()
    if not term:
        return None
    users = _user_model().objects.filter(
        Q(email__icontains=term)
        | Q(first_name__icontains=term)
        | Q(last_name__icontains=term)
        | Q(customer_profile__display_name_ar__icontains=term)
        | Q(customer_profile__display_name_en__icontains=term)
        | Q(referral_code__code__icontains=term)
    )
    return set(users.values_list("pk", flat=True))


def ranking(stats: dict, *, ordering: str = "-qualified", only=None) -> list[tuple]:
    """
    `[(referrer_id, figures), ...]` ordered, with `only` (a set of ids) as the search filter.

    Ties are broken by more invited, then more points, then id — so a page never shuffles.
    """
    key = ordering.lstrip("-")
    if key not in ORDERING_KEYS:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="ترتيب غير مدعوم")

    items = [(pk, entry) for pk, entry in stats.items() if only is None or pk in only]
    present = [item for item in items if item[1][key] is not None]
    absent = [item for item in items if item[1][key] is None]
    reverse = ordering.startswith("-")
    present.sort(
        key=lambda item: (
            item[1][key],
            item[1]["invited"],
            item[1]["points_awarded"],
            str(item[0]),
        ),
        reverse=reverse,
    )
    return present + absent


def member_row(referrer_id, entry: dict, people: dict, rank: int) -> dict:
    """One ranking row, shaped for the API."""
    who = people.get(referrer_id) or {
        "id": referrer_id,
        "name": "",
        "email": "",
        "account_type": "",
        "code": "",
    }
    return {
        "rank": rank,
        "referrer": {key: who[key] for key in ("id", "name", "email", "account_type")},
        "code": who["code"],
        **entry,
    }


# ═══════════════════════════════════════════════════════════
#  One member's invited customers
# ═══════════════════════════════════════════════════════════


def invitees_queryset(referrer_id, date_from=None, date_to=None):
    """
    The member's referrals, newest first, each with the referee's counted orders.

    ⚠️  The two figures per referee are correlated sub-selects (one query for the page,
        not one per row).
    """
    from django.db.models import IntegerField, OuterRef, Subquery

    orders = (
        _order_model()
        .objects.filter(plain_sale_q(), customer__user_id=OuterRef("referee_id"))
        .order_by()
        .values("customer__user_id")
    )
    return (
        scope(date_from, date_to)
        .filter(referrer_id=referrer_id)
        .select_related("referee", "referee__customer_profile", "qualifying_order")
        .annotate(
            referee_orders=Coalesce(
                Subquery(
                    orders.annotate(n=Count("pk")).values("n")[:1], output_field=IntegerField()
                ),
                0,
            ),
            referee_net=Subquery(orders.annotate(s=Sum(net_expr())).values("s")[:1]),
        )
        .order_by("-created_at", "-pk")
    )


def invitee_row(referral) -> dict:
    referee = referral.referee
    profile = getattr(referee, "customer_profile", None)
    display = getattr(profile, "display_name_ar", "") if profile else ""
    order = referral.qualifying_order
    return {
        "id": referral.pk,
        "referee": {
            "id": referee.pk,
            "name": _name(referee.first_name, referee.last_name, display, referee.email),
            "email": referee.email,
        },
        "status": referral.status,
        "invited_at": referral.created_at,
        "qualifying_order_number": order.number if order is not None else None,
        "orders": referral.referee_orders,
        "net_sales": quantize(referral.referee_net or ZERO),
        "rewarded_at": referral.rewarded_at,
        "rejection_reason": referral.rejection_reason,
    }
