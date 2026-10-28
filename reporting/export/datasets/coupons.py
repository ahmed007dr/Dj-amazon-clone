"""
The coupon dataset — one row per coupon, with what it brought in.

⚠️  The figures come from `promotions.analytics.summaries`, **the same function the
    admin screen calls** — never a second implementation. A sheet whose "net sales"
    disagrees with the drawer the owner just closed is the failure that ends trust in
    both, and "which statuses count as a sale" is defined exactly once, there.

⚠️  The holder's *name* is exported; the holder's *note* is not.

    The note is free text typed by an admin — "gave it to Dr X, her number is …" is a
    realistic entry. Columns are an allowlist (see `registry`), and nobody has decided
    that a free-text field belongs in a file that gets e-mailed around. No contact
    column exists in this dataset, so there is no `sensitive` gate to pass.
"""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from core.permissions import CanManagePricing
from promotions import analytics
from promotions.models import Coupon, CouponKind
from reporting.export.datasets import _common
from reporting.export.registry import Column, Dataset, Filter, Group, register
from reporting.export.writer import Kind


def _coupon_qs(filters: dict):
    queryset = Coupon.objects.all()

    if search := (filters.get("search") or "").strip():
        queryset = queryset.filter(
            Q(code__icontains=search)
            | Q(name_ar__icontains=search)
            | Q(name_en__icontains=search)
            | Q(holder_name__icontains=search)
        )
    if filters.get("has_holder") == "true":
        queryset = queryset.exclude(holder_name="")

    return queryset.order_by("-created_at")


def _count(filters: dict) -> int:
    # ⚠️  Validates the period here too: `count` runs before any row is read, so a
    #     malformed date is a clear 400 rather than an error half-way through the file.
    _common.period(filters)
    return _coupon_qs(filters).count()


def _status(coupon: Coupon, now) -> str:
    """The one word the owner wants: why does (or doesn't) this code work today?"""
    if not coupon.is_active:
        return "موقوف"
    if coupon.starts_at > now:
        return "مجدول"
    if coupon.ends_at is not None and coupon.ends_at <= now:
        return "منتهٍ"
    if coupon.is_exhausted:
        return "مستنفد"
    return "جارٍ"


def _rows(filters: dict, include_contact: bool):
    start, end = _common.period(filters)
    coupons = list(_coupon_qs(filters))
    stats = analytics.summaries([coupon.pk for coupon in coupons], start, end)
    now = timezone.now()

    for coupon in coupons:
        row = stats[coupon.pk]
        yield (
            coupon.code,
            coupon.name_ar,
            coupon.holder_name,
            _status(coupon, now),
            _common.labelled(coupon.kind, CouponKind.choices),
            coupon.value if coupon.kind != CouponKind.FREE_SHIPPING else None,
            coupon.usage_limit,
            row["times_used"],
            row["orders"],
            row["customers"],
            row["gross_sales"],
            row["discount_given"],
            row["net_sales"],
            row["order_total"],
            row["average_order_value"],
            row["cancelled_orders"] + row["refunded_orders"] + row["failed_orders"],
            row["refunded_amount"],
            row["first_used_at"],
            row["last_used_at"],
            coupon.starts_at,
            coupon.ends_at,
        )


register(
    Dataset(
        key="coupons",
        label="الكوبونات",
        group=Group.SALES,
        permission=CanManagePricing,
        note=(
            "كوبون لكل صف: الحامل والاستخدام والمبيعات. "
            "المبيعات تستثني الطلبات الملغاة والمستردة وفاشلة الدفع وتُعرض منفصلة. "
            "الفترة اختيارية وتخص الاستخدام والمبيعات"
        ),
        filters=[
            Filter(key="start", label="من تاريخ", kind="date"),
            Filter(key="end", label="إلى تاريخ", kind="date"),
            Filter(key="search", label="بحث (كود · اسم · حامل)", kind="text"),
            Filter(key="has_holder", label="له حامل فقط", kind="bool"),
        ],
        columns=lambda contact: [
            Column("الكود", width=18),
            Column("الاسم", width=24),
            Column("الحامل", width=24),
            Column("الحالة", width=12),
            Column("النوع", width=14),
            Column("القيمة", Kind.MONEY),
            Column("حد الاستخدام", Kind.INT),
            Column("مرات الاستخدام", Kind.INT),
            Column("الطلبات المحتسبة", Kind.INT),
            Column("العملاء", Kind.INT),
            Column("المبيعات قبل الكوبون", Kind.MONEY),
            Column("الخصم الممنوح", Kind.MONEY),
            Column("صافي المبيعات", Kind.MONEY),
            Column("إجمالي الطلبات", Kind.MONEY),
            Column("متوسط الطلب", Kind.MONEY),
            Column("طلبات مستبعدة", Kind.INT),
            Column("قيمة المستردّ", Kind.MONEY),
            Column("أول استخدام", Kind.DATETIME),
            Column("آخر استخدام", Kind.DATETIME),
            Column("يبدأ", Kind.DATETIME),
            Column("ينتهي", Kind.DATETIME),
        ],
        rows=_rows,
        count=_count,
    )
)
