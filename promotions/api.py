"""
Coupon endpoints.

⚠️  **There is no public coupon list at all.**

    Exposing them makes every visitor try the highest available discount instead
    of the code they were sent in their campaign. And validating a specific code
    happens in the cart (`cart/coupon/`), where the customer enters it — not here.

⚠️  And redemption does not pass through here: `promotions.services` redeems it
    inside the order's transaction. These endpoints edit the campaigns and read
    their history.
"""

from decimal import Decimal

from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from core.permissions import CanManagePricing
from promotions import analytics, analytics_customers, analytics_report, services
from promotions import serializers as s
from promotions.models import Coupon, CouponRedemption


def filter_coupons(queryset, params):
    """
    The coupon list's filters — shared by the CRUD list and the analytics ranking.

    ⚠️  One copy, so "running" and "expired" mean the same thing on both screens,
        and a holder searched for in one is found in the other.
    """
    now = timezone.now()

    if search := (params.get("search") or "").strip():
        queryset = queryset.filter(
            Q(code__icontains=search)
            | Q(name_ar__icontains=search)
            | Q(name_en__icontains=search)
            | Q(holder_name__icontains=search)
            | Q(holder_note__icontains=search)
        )

    # ⚠️  The status is computed in the query, not in Python: filtering after
    #     pagination gives short pages with nobody noticing.
    status_filter = params.get("status")
    if status_filter == "running":
        queryset = queryset.filter(is_active=True, starts_at__lte=now).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gt=now)
        )
    elif status_filter == "expired":
        queryset = queryset.filter(ends_at__lte=now)
    elif status_filter == "scheduled":
        queryset = queryset.filter(starts_at__gt=now)

    if params.get("has_holder") == "true":
        queryset = queryset.exclude(holder_name="")

    # ⚠️  The scope: `all` = the whole catalogue, `products` = limited to chosen products,
    #     `categories` = limited to categories, `scoped` = either. Judged on the stored rows
    #     (the through tables, a deleted product included — the engine does the same), with
    #     `EXISTS` rather than a join so a coupon with ten products is still one row and the
    #     analytics ranking that shares this filter never double-counts it.
    scope = params.get("scope")
    if scope in ("all", "products", "categories", "scoped"):
        has_products = Exists(Coupon.products.through.objects.filter(coupon_id=OuterRef("pk")))
        has_categories = Exists(Coupon.categories.through.objects.filter(coupon_id=OuterRef("pk")))
        if scope == "all":
            queryset = queryset.filter(~has_products, ~has_categories)
        elif scope == "products":
            queryset = queryset.filter(has_products)
        elif scope == "categories":
            queryset = queryset.filter(has_categories)
        else:
            queryset = queryset.filter(has_products | has_categories)

    # Open to visitors or not (`?guests=allowed` / `?guests=blocked`)
    guests = params.get("guests")
    if guests in ("allowed", "blocked"):
        queryset = queryset.filter(allow_guests=(guests == "allowed"))

    return queryset


class CouponListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [CanManagePricing]
    serializer_class = s.CouponSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        # ⚠️  `scope_prefetch` keeps the scope summary at a constant number of queries per page
        queryset = Coupon.objects.prefetch_related(*s.scope_prefetch())
        return filter_coupons(queryset, self.request.query_params).order_by("-created_at")

    def list(self, request, *args, **kwargs):
        """
        ⚠️  `times_used` and `net_sales` for the whole page in **two grouped queries**.

            The serializer reads them from the context instead of asking per row;
            a page of 25 costs the same as a page of 1. They follow the
            `date_from` / `date_to` the stat cards use, so the table and the cards
            above it always describe the same period.
        """
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        items = page if page is not None else list(queryset)

        date_from, date_to = analytics.parse_period(request.query_params)
        stats = analytics.summaries([coupon.pk for coupon in items], date_from, date_to)

        serializer = self.get_serializer(
            items, many=True, context={**self.get_serializer_context(), "coupon_stats": stats}
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def perform_create(self, serializer):
        coupon = serializer.save()
        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.CREATE,
            object_repr=f"كوبون {coupon.code}",
            changes={"kind": coupon.kind, "value": str(coupon.value)},
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )


class CouponDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [CanManagePricing]
    serializer_class = s.CouponSerializer
    queryset = Coupon.objects.prefetch_related(*s.scope_prefetch())

    def perform_update(self, serializer):
        coupon = serializer.save()
        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"كوبون {coupon.code}",
            changes={"fields": sorted(serializer.validated_data)},
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_destroy(self, instance):
        """
        ⚠️  **A used coupon is never deleted — it is disabled.**

            The redemption records point at it, and deleting it makes "how much
            was this order sold for, and why?" a question with no answer. And
            disabling prevents new use while keeping the history intact.
        """
        if instance.usage_count:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail=(
                    f"استُخدم هذا الكوبون {instance.usage_count} مرة — "
                    "أوقفه بدل حذفه لتبقى سجلات الصرف مفهومة"
                ),
                status_code=409,
            )

        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.DELETE,
            object_repr=f"كوبون {instance.code}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )
        instance.delete()


class CouponRedemptionListAPI(generics.ListAPIView):
    """
    The redemption log — **read-only**.

    ⚠️  Corrections go through a new entry, not by editing the old one: this is
        a financial record the campaign's impact is measured from.
    """

    permission_classes = [CanManagePricing]
    serializer_class = s.CouponRedemptionSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = CouponRedemption.objects.select_related("coupon", "user")

        if coupon := self.request.query_params.get("coupon"):
            queryset = queryset.filter(coupon_id=coupon)
        if self.request.query_params.get("cancelled") != "true":
            queryset = queryset.filter(is_cancelled=False)

        return queryset.order_by("-created_at")


# ═══════════════════════════════════════════════════════════
#  Analytics
# ═══════════════════════════════════════════════════════════


def public(value):
    """
    Money to strings, recursively.

    ⚠️  DRF's JSON encoder turns a `Decimal` into a **float**. Money crosses the wire
        as a string (ADR-31) — a float loses the piastre on a large total.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: public(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [public(item) for item in value]
    return value


#: The keys the ranking may be ordered by
_RANKING_KEYS = {
    "net_sales",
    "gross_sales",
    "discount_given",
    "order_total",
    "orders",
    "customers",
    "times_used",
    "last_used_at",
    "code",
    "holder_name",
    "created_at",
    "new_customers",
    "new_customer_rate",
    "discount_share_of_gross",
}


def _coupon_meta(coupon: Coupon) -> dict:
    return {
        "id": coupon.pk,
        "code": coupon.code,
        "name_ar": coupon.name_ar,
        "name_en": coupon.name_en,
        "holder_name": coupon.holder_name,
        "holder_note": coupon.holder_note,
        "kind": coupon.kind,
        "value": coupon.value,
        "starts_at": coupon.starts_at,
        "ends_at": coupon.ends_at,
        "is_active": coupon.is_active,
        "is_running": coupon.is_running,
        "is_expired": coupon.is_expired,
        "is_exhausted": coupon.is_exhausted,
        "created_at": coupon.created_at,
        # The member a personal coupon belongs to ("who distributed this"); null for a campaign
        "owner": analytics_report.owner_payload(coupon),
    }


#: The keys a holder row may be ordered by (`?group_by=holder`)
_HOLDER_KEYS = {
    "net_sales",
    "gross_sales",
    "discount_given",
    "order_total",
    "orders",
    "customers",
    "times_used",
    "last_used_at",
    "holder_name",
    "coupons",
    "guest_orders",
    "registered_orders",
    "new_customers",
}


def _sort_value(row, key):
    value = row[key]
    return value["count"] if isinstance(value, dict) else value


def _ranked(rows, ordering, allowed, tie_break):
    """Order `rows` by `ordering`; a missing value (never used) sorts last either way."""
    descending = ordering.startswith("-")
    key = ordering.lstrip("-")
    if key not in allowed:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="ترتيب غير مدعوم")

    present = [row for row in rows if _sort_value(row, key) is not None]
    absent = [row for row in rows if _sort_value(row, key) is None]
    present.sort(key=lambda row: (_sort_value(row, key), row[tie_break]), reverse=descending)
    return present + absent


class CouponAnalyticsOverviewAPI(APIView):
    """
    `GET` — totals across every coupon, and the coupons ranked by sales.

        ?date_from=2026-10-01&date_to=2026-10-31   the period (inclusive, optional)
        ?search=&status=&has_holder=true            the same filters as the coupon list
        ?ordering=-net_sales                        default; any key in `_RANKING_KEYS`
        ?group_by=holder                            one row per holder (their codes combined);
                                                    ordering then takes `_HOLDER_KEYS`

    Every coupon row, every holder row and `totals` carry the buyer split: `by_customer_type`
    (registered / guest), `new_customers` / `returning_customers`, `new_customer_rate`,
    `discount_by_customer_type` and `discount_share_of_gross`; the page also carries
    `discount_series` (discount volume over the period, split registered / guest).

    ⚠️  `totals` covers **all** coupons whatever the search says: the cards above a
        filtered table must not change when someone types in the search box.
    """

    permission_classes = [CanManagePricing]

    def get(self, request):
        params = request.query_params
        date_from, date_to = analytics.parse_period(params)

        ordering = params.get("ordering") or "-net_sales"
        group_by = params.get("group_by") or ""
        if group_by not in ("", "coupon", "holder"):
            raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="group_by غير مدعوم")
        by_holder = group_by == "holder"

        coupons = list(filter_coupons(Coupon.objects.select_related("owner"), params))
        stats = analytics.summaries([coupon.pk for coupon in coupons], date_from, date_to)
        # One grouped query for the buyer figures of every coupon (registered / guest, new)
        breakdown = analytics_customers.Breakdown.load(None, date_from, date_to)

        if by_holder:
            rows = _ranked(
                analytics_report.holder_rows(coupons, stats, breakdown),
                ordering,
                _HOLDER_KEYS,
                "holder_name",
            )
        else:
            rows = []
            for coupon in coupons:
                row = _coupon_meta(coupon)
                row.update(stats[coupon.pk])
                row.update(breakdown.block([coupon.pk]))
                row["usage_limit"] = coupon.usage_limit
                row["usage_count"] = coupon.usage_count
                row["remaining_total"] = (
                    max(coupon.usage_limit - coupon.usage_count, 0)
                    if coupon.usage_limit is not None
                    else None
                )
                rows.append(row)
            # None sorts last in either direction: "never used" is not the biggest or smallest
            rows = _ranked(rows, ordering, _RANKING_KEYS, "code")

        paginator = AdminPageNumberPagination()
        page = paginator.paginate_queryset(rows, request, view=self)
        response = paginator.get_paginated_response(public(page))
        totals = analytics.totals(date_from, date_to)
        totals.update(breakdown.block())
        response.data["totals"] = public(totals)
        response.data["counts"] = analytics.coupon_counts()
        response.data["period"] = {"date_from": date_from, "date_to": date_to}
        response.data["group_by"] = "holder" if by_holder else "coupon"
        # Discount volume over the period, split registered / guest — the overview chart
        response.data["discount_series"] = public(
            analytics_report.discount_series(None, date_from, date_to)
        )
        return response


class CouponAnalyticsDetailAPI(APIView):
    """
    `GET` — one coupon: the summary, the products it sold and a daily series.

    ⚠️  The recent orders are a separate endpoint (`.../orders/`) — they paginate,
        and a drawer that opens should not wait for a list it has not scrolled to.
    """

    permission_classes = [CanManagePricing]

    def get(self, request, pk):
        coupon = get_object_or_404(
            Coupon.objects.select_related("owner").prefetch_related("products", "categories"),
            pk=pk,
        )
        date_from, date_to = analytics.parse_period(request.query_params)

        summary = analytics.summaries([coupon.pk], date_from, date_to)[coupon.pk]
        owner_used = None
        if coupon.owner_id is not None:
            owner_used = CouponRedemption.objects.filter(
                coupon=coupon, user_id=coupon.owner_id, is_cancelled=False
            ).count()
        summary.update(analytics.remaining_uses(coupon, owner_used))
        summary["customers_at_limit"] = analytics.customers_at_limit(coupon)
        summary.update(analytics_customers.Breakdown.load([coupon.pk], date_from, date_to).block())

        meta = _coupon_meta(coupon)
        meta.update(
            owner_email=coupon.owner.email if coupon.owner_id else None,
            products_count=len(coupon.products.all()),
            categories_count=len(coupon.categories.all()),
        )

        return Response(
            public(
                {
                    "coupon": meta,
                    "period": {"date_from": date_from, "date_to": date_to},
                    "summary": summary,
                    "products": analytics.product_breakdown(coupon, date_from, date_to),
                    "series": analytics.series(coupon, date_from, date_to),
                    "discount_series": analytics_report.discount_series(
                        [coupon.pk], date_from, date_to
                    ),
                }
            )
        )


class CouponOrdersAPI(APIView):
    """
    `GET` — the orders that used this coupon, newest first, paginated.

        ?only=sales|excluded    counted sales / cancelled·refunded·failed (default: all)

    ⚠️  Contact details are **masked** (`a***@gmail.com`): the page is for reading
        the campaign, not for harvesting the people who used it. The full order is
        one click away in the orders screen, behind its own permission.
    """

    permission_classes = [CanManagePricing]

    def get(self, request, pk):
        coupon = get_object_or_404(Coupon, pk=pk)
        date_from, date_to = analytics.parse_period(request.query_params)

        only = request.query_params.get("only")
        if only not in (None, "", "sales", "excluded"):
            raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="قيمة only غير مدعومة")

        queryset = analytics.orders_queryset(coupon, date_from, date_to, only=only or None)

        paginator = AdminPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(public([analytics.order_row(row) for row in page]))


class CouponCustomersAPI(APIView):
    """
    `GET` — the buyers who used this coupon: registered accounts and guests, paginated.

        ?search=         name · e-mail · phone
        ?ordering=       -net_sales (default) · net_sales · gross_sales · discount · orders ·
                         first_used_at · last_used_at · name · customer_type  (`-` = descending)
        ?customer_type=  REGISTERED | GUEST
        ?new=true|false  only new / only returning customers
        ?date_from= &date_to=   the same period as every other figure

    ⚠️  Unlike the orders list this shows the **full** name, e-mail and phone: it is the
        report of who the code's buyers are. It sits behind the same pricing permission as
        the rest of the coupon admin, and counted orders only (cancelled, refunded and
        payment-failed ones are not buyers of the code — see the module docstring of
        `promotions.analytics`).
    """

    permission_classes = [CanManagePricing]

    def get(self, request, pk):
        coupon = get_object_or_404(Coupon, pk=pk)
        params = request.query_params
        date_from, date_to = analytics.parse_period(params)

        kind = (params.get("customer_type") or "").upper()
        if kind not in ("", "REGISTERED", "GUEST"):
            raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="customer_type غير مدعوم")
        new = params.get("new")
        if new not in (None, "", "true", "false"):
            raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="new غير مدعوم")

        queryset = analytics_report.customers_queryset(
            coupon,
            date_from,
            date_to,
            search=params.get("search") or "",
            ordering=params.get("ordering") or "-net_sales",
            kind=kind.lower() or None,
            new=None if not new else new == "true",
        )

        paginator = AdminPageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(public(analytics_report.customer_rows(page)))


class CouponBulkCreateAPI(APIView):
    """
    `POST` — one template, a list of people, a unique random code for each.

    ⚠️  The response is `name -> code` and is **the only time the codes are shown
        together** in a form meant to be copied — the list screen shows them one by
        one afterwards. Everything is created in one transaction: all or none.
    """

    permission_classes = [CanManagePricing]

    def post(self, request):
        serializer = s.BulkCouponSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)

        holders = data.pop("holders")
        prefix = data.pop("prefix", "")

        coupons = services.create_for_holders(holders, template=data, prefix=prefix)

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.CREATE,
            object_repr=f"كوبونات جماعية ({len(coupons)})",
            # ⚠️  Count and shape, never the codes: the audit log is read by more
            #     people than are meant to hold a working code.
            changes={
                "count": len(coupons),
                "prefix": prefix,
                "kind": data["kind"],
                "value": str(data.get("value", 0)),
            },
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(
            {
                "count": len(coupons),
                "results": [
                    {"id": coupon.pk, "holder_name": coupon.holder_name, "code": coupon.code}
                    for coupon in coupons
                ],
            },
            status=status.HTTP_201_CREATED,
        )
