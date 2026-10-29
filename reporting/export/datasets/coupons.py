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
from promotions import analytics, analytics_report
from promotions.analytics_customers import Breakdown
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
    ids = [coupon.pk for coupon in coupons]
    stats = analytics.summaries(ids, start, end)
    # ⚠️  The same grouped query the screen uses, so "guest orders" and "new customers"
    #     here are the numbers on the screen.
    buyers = Breakdown.load(ids, start, end)
    now = timezone.now()

    for coupon in coupons:
        row = stats[coupon.pk]
        block = buyers.block([coupon.pk])
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
            block["by_customer_type"]["registered"]["orders"],
            block["by_customer_type"]["guest"]["orders"],
            block["new_customers"]["count"],
            block["discount_share_of_gross"],
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
            # Appended, so a saved pivot on the earlier columns keeps working
            Column("طلبات المسجّلين", Kind.INT),
            Column("طلبات الزوار", Kind.INT),
            Column("عملاء جدد", Kind.INT),
            Column("نسبة الخصم من المبيعات (%)", Kind.MONEY),
        ],
        rows=_rows,
        count=_count,
    )
)


# ═══════════════════════════════════════════════════════════
#  Who used the codes — one row per coupon and buyer
# ═══════════════════════════════════════════════════════════

_TYPE_LABELS = {"REGISTERED": "مسجّل", "GUEST": "زائر"}


def _buyer_columns(include_contact: bool) -> list[Column]:
    columns = [
        Column("الكود", width=18),
        Column("الحامل", width=24),
        Column("نوع العميل", width=12),
        Column("اشترى كـ", width=12),
        Column("الطلبات", Kind.INT),
        Column("المبيعات قبل الكوبون", Kind.MONEY),
        Column("الخصم الممنوح", Kind.MONEY),
        Column("صافي المبيعات", Kind.MONEY),
        Column("عميل جديد", Kind.BOOL),
        Column("أول استخدام", Kind.DATETIME),
        Column("آخر استخدام", Kind.DATETIME),
    ]
    if include_contact:
        # ⚠️  Appended at the end: the file with contact details and the one without are
        #     otherwise column-for-column identical.
        #     Without them the sheet is analysis (who is registered, who is new, how much);
        #     with them it is a list of named people — a separate, audited act.
        columns += [
            Column("الاسم", width=26, sensitive=True),
            Column("البريد", width=30, sensitive=True),
            Column("الهاتف", width=18, sensitive=True),
        ]
    return columns


def _buyer_rows(filters: dict, include_contact: bool):
    start, end = _common.period(filters)
    coupons = {coupon.pk: coupon for coupon in _coupon_qs(filters)}
    if not coupons:
        return

    queryset = analytics_report.customers_queryset(
        list(coupons), start, end, ordering="-net_sales"
    ).order_by("coupon_ref", "-net", "customer_id", "guest_key")

    for page in _chunks(queryset.iterator(chunk_size=_common.CHUNK), _common.CHUNK):
        shaped = analytics_report.customer_rows(page)
        for raw, row in zip(page, shaped, strict=True):
            coupon = coupons[raw["coupon_ref"]]
            values = [
                coupon.code,
                coupon.holder_name,
                _TYPE_LABELS[row["customer_type"]],
                _TYPE_LABELS[row["purchased_as"]],
                row["orders"],
                row["gross_sales"],
                row["discount"],
                row["net_sales"],
                row["is_new_customer"],
                row["first_used_at"],
                row["last_used_at"],
            ]
            if include_contact:
                values += [row["name"], row["email"], row["phone"]]
            yield tuple(values)


def _chunks(iterator, size: int):
    batch = []
    for item in iterator:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _buyer_count(filters: dict) -> int:
    start, end = _common.period(filters)
    ids = list(_coupon_qs(filters).values_list("pk", flat=True))
    if not ids:
        return 0
    return analytics_report.customers_queryset(ids, start, end).count()


register(
    Dataset(
        key="coupon_customers",
        label="عملاء الكوبونات",
        group=Group.SALES,
        permission=CanManagePricing,
        has_contact=True,
        note=(
            "صف لكل كوبون وعميل: مسجّل أم زائر، عدد الطلبات والخصم والمبيعات، وهل هو عميل جديد. "
            "الاسم والبريد والهاتف خيار منفصل مسجَّل. "
            "تُحتسب الطلبات المؤهلة فقط (بلا الملغاة والمستردة وفاشلة الدفع)"
        ),
        filters=[
            Filter(key="start", label="من تاريخ", kind="date"),
            Filter(key="end", label="إلى تاريخ", kind="date"),
            Filter(key="search", label="بحث (كود · اسم · حامل)", kind="text"),
            Filter(key="has_holder", label="له حامل فقط", kind="bool"),
        ],
        columns=_buyer_columns,
        rows=_buyer_rows,
        count=_buyer_count,
    )
)
