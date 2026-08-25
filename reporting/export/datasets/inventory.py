"""
Stock datasets — what is on the shelf, in which batch, and what moved.

⚠️  `المتاح` is computed the way `Stock.available` computes it, and nowhere else.

    Physical − reserved − damaged − expired, floored at zero. Writing the
    subtraction out again here would create a second definition of the only
    number that matters when selling — and the two would disagree the first
    time a reservation expired mid-export.
"""

from __future__ import annotations

from django.db.models import F, Value
from django.db.models.functions import Greatest
from django.utils import timezone

from core.permissions import CanManageInventory
from inventory.models import Batch, Stock, StockAlert, StockMovement
from reporting.export.datasets import _common
from reporting.export.registry import Column, Dataset, Filter, Group, register
from reporting.export.writer import Kind

# ═══════════════════════════════════════════════════════════
#  Available stock
# ═══════════════════════════════════════════════════════════

#: ⚠️  `Stock.available` is a Python property, so it cannot be filtered or
#:     sorted in the database and calling it per row would need model instances.
#:     This is the same arithmetic as an annotation — and the docstring above is
#:     the contract that keeps the two in step.
_AVAILABLE = Greatest(
    F("quantity_physical")
    - F("quantity_reserved")
    - F("quantity_damaged")
    - F("quantity_expired"),
    Value(0),
)


def _stock_qs(filters: dict):
    queryset = Stock.objects.select_related("product", "product__category", "location", "variant")

    if location := filters.get("location"):
        queryset = queryset.filter(location__code=location)
    if filters.get("in_stock") == "true":
        queryset = queryset.annotate(_available=_AVAILABLE).filter(_available__gt=0)
    if filters.get("below_reorder") == "true":
        # ⚠️  `reorder_point > 0` as well: a product with no reorder point set is
        #     not "below" anything, and including them makes every product in
        #     the catalogue look like it needs ordering.
        queryset = queryset.annotate(_available=_AVAILABLE).filter(
            reorder_point__gt=0, _available__lte=F("reorder_point")
        )

    return queryset.order_by("product__sku", "location__code")


def _stock_rows(filters: dict, include_contact: bool):
    rows = (
        _stock_qs(filters)
        .annotate(available=_AVAILABLE)
        .values_list(
            "product__sku",
            "product__name_ar",
            "product__category__path",
            "variant__sku",
            "location__code",
            "location__name_ar",
            "quantity_physical",
            "quantity_reserved",
            "available",
            "quantity_damaged",
            "quantity_expired",
            "reorder_point",
            "critical_point",
            "last_counted_at",
        )
        .iterator(chunk_size=_common.CHUNK)
    )
    yield from rows


register(
    Dataset(
        key="stock-levels",
        label="البضاعة المتاحة",
        group=Group.INVENTORY,
        permission=CanManageInventory,
        note="الرصيد الحالي لكل منتج في كل موقع — والمتاح للبيع محسوب",
        filters=[
            Filter(key="location", label="الموقع المخزني", kind="choice", source="locations"),
            Filter(key="in_stock", label="ما له رصيد فقط", kind="bool"),
            Filter(key="below_reorder", label="تحت حد الطلب فقط", kind="bool"),
        ],
        columns=lambda contact: [
            Column("رمز المنتج", width=18),
            Column("اسم المنتج", width=32),
            Column("مسار الفئة", width=26),
            Column("رمز النسخة", width=16),
            Column("رمز الموقع", width=14),
            Column("الموقع", width=20),
            Column("الفعلي", Kind.INT),
            Column("المحجوز", Kind.INT),
            Column("المتاح", Kind.INT),
            Column("التالف", Kind.INT),
            Column("المنتهي", Kind.INT),
            Column("حد الطلب", Kind.INT),
            Column("الحد الحرج", Kind.INT),
            Column("آخر جرد", Kind.DATETIME),
        ],
        rows=_stock_rows,
        count=lambda filters: _stock_qs(filters).count(),
    )
)


# ═══════════════════════════════════════════════════════════
#  Batches and expiry
# ═══════════════════════════════════════════════════════════


def _batch_qs(filters: dict):
    queryset = Batch.objects.select_related("product", "location").filter(quantity_remaining__gt=0)

    if location := filters.get("location"):
        queryset = queryset.filter(location__code=location)
    if filters.get("quarantined") == "true":
        queryset = queryset.filter(is_quarantined=True)

    if raw := filters.get("expiring_within_days"):
        try:
            days = max(0, int(raw))
        except (TypeError, ValueError) as exc:
            from core.errors import BusinessError, ErrorCode

            raise BusinessError(
                ErrorCode.VALIDATION_ERROR, detail="عدد الأيام يجب أن يكون رقمًا"
            ) from exc
        horizon = timezone.localdate() + timezone.timedelta(days=days)
        queryset = queryset.filter(expires_at__isnull=False, expires_at__lte=horizon)

    # ⚠️  FEFO order — nearest to expiry first, matching `Batch.Meta.ordering`.
    #     The whole reason to open this file is "what expires soonest", and a
    #     file sorted by SKU makes the reader sort it again every time.
    return queryset.order_by("expires_at", "product__sku")


def _batch_rows(filters: dict, include_contact: bool):
    today = timezone.localdate()

    for row in (
        _batch_qs(filters)
        .values_list(
            "number",
            "product__sku",
            "product__name_ar",
            "location__code",
            "quantity_received",
            "quantity_remaining",
            "unit_cost",
            "expires_at",
            "manufactured_at",
            "supplier_batch_number",
            "is_quarantined",
            "received_at",
        )
        .iterator(chunk_size=_common.CHUNK)
    ):
        expires_at = row[7]
        # ⚠️  The days-to-expiry column is why this sheet gets opened, and it
        #     cannot be a formula: an exported formula recalculates against the
        #     day the file is *read*, so a report from last month quietly
        #     changes its own numbers.
        remaining = (expires_at - today).days if expires_at else None
        yield (*row[:8], remaining, *row[8:])


register(
    Dataset(
        key="batches",
        label="الدفعات والصلاحيات",
        group=Group.INVENTORY,
        permission=CanManageInventory,
        note="الدفعات التي بها رصيد — مرتّبة بالأقرب انتهاءً",
        filters=[
            Filter(key="location", label="الموقع المخزني", kind="choice", source="locations"),
            Filter(
                key="expiring_within_days",
                label="تنتهي خلال (يوم)",
                kind="text",
                note="اتركه فارغًا لكل الدفعات",
            ),
            Filter(key="quarantined", label="المحجورة فقط", kind="bool"),
        ],
        columns=lambda contact: [
            Column("رقم الدفعة", width=20),
            Column("رمز المنتج", width=18),
            Column("اسم المنتج", width=32),
            Column("الموقع", width=14),
            Column("المستلم", Kind.INT),
            Column("المتبقي", Kind.INT),
            Column("تكلفة الوحدة", Kind.MONEY),
            Column("تاريخ الصلاحية", Kind.DATE),
            Column("الأيام المتبقية", Kind.INT),
            Column("تاريخ الإنتاج", Kind.DATE),
            Column("دفعة المورّد", width=18),
            Column("محجورة", Kind.BOOL),
            Column("تاريخ الاستلام", Kind.DATETIME),
        ],
        rows=_batch_rows,
        count=lambda filters: _batch_qs(filters).count(),
    )
)


# ═══════════════════════════════════════════════════════════
#  Movements
# ═══════════════════════════════════════════════════════════


def _movement_qs(filters: dict):
    queryset = StockMovement.objects.select_related("product", "location", "batch", "performed_by")

    # ⚠️  The period is **mandatory** here and nowhere else in this module.
    #
    #     This is the largest table in the system by design — a row per receipt,
    #     sale, adjustment and transfer, forever. An unfiltered export is a
    #     request for the entire history of the business in one spreadsheet, and
    #     refusing it up front is cheaper than a ceiling error after a
    #     thirty-second query has already run.
    queryset = _common.apply_period(queryset, filters, "created_at", required=True)

    if location := filters.get("location"):
        queryset = queryset.filter(location__code=location)
    if movement_type := filters.get("movement_type"):
        queryset = queryset.filter(movement_type=movement_type)
    if sku := filters.get("sku"):
        queryset = queryset.filter(product__sku=sku)

    return queryset.order_by("-created_at")


def _movement_rows(filters: dict, include_contact: bool):
    from inventory.models import MovementType

    for row in (
        _movement_qs(filters)
        .values_list(
            "created_at",
            "reference",
            "movement_type",
            "product__sku",
            "product__name_ar",
            "location__code",
            "batch__number",
            "quantity",
            "balance_after",
            "unit_cost",
            "reference_type",
            "performed_by__email",
            "note",
        )
        .iterator(chunk_size=_common.CHUNK)
    ):
        yield (
            row[0],
            row[1],
            _common.labelled(row[2], MovementType.choices),
            *row[3:],
        )


register(
    Dataset(
        key="stock-movements",
        label="حركات المخزون",
        group=Group.INVENTORY,
        permission=CanManageInventory,
        note="سجل كل ما دخل وخرج — الفترة إلزامية لأن الجدول ينمو بلا حدّ",
        filters=[
            Filter(key="start", label="من تاريخ", kind="date", required=True),
            Filter(key="end", label="إلى تاريخ", kind="date", required=True),
            Filter(key="location", label="الموقع المخزني", kind="choice", source="locations"),
            Filter(
                key="movement_type",
                label="نوع الحركة",
                kind="choice",
                source="movement_types",
            ),
            Filter(key="sku", label="رمز منتج بعينه", kind="text"),
        ],
        columns=lambda contact: [
            Column("الوقت", Kind.DATETIME),
            Column("المرجع", width=20),
            Column("نوع الحركة", width=18),
            Column("رمز المنتج", width=18),
            Column("اسم المنتج", width=32),
            Column("الموقع", width=14),
            Column("رقم الدفعة", width=20),
            Column("الكمية", Kind.INT),
            Column("الرصيد بعدها", Kind.INT),
            Column("تكلفة الوحدة", Kind.MONEY),
            Column("نوع المرجع", width=16),
            Column("المنفّذ", width=26),
            Column("ملاحظة", width=30),
        ],
        rows=_movement_rows,
        count=lambda filters: _movement_qs(filters).count(),
    )
)


# ═══════════════════════════════════════════════════════════
#  Alerts
# ═══════════════════════════════════════════════════════════


def _alert_qs(filters: dict):
    queryset = StockAlert.objects.select_related("product", "location", "batch")

    if filters.get("unresolved") == "true":
        queryset = queryset.filter(is_resolved=False)
    if alert_type := filters.get("alert_type"):
        queryset = queryset.filter(alert_type=alert_type)

    return queryset.order_by("is_resolved", "-created_at")


def _alert_rows(filters: dict, include_contact: bool):
    from inventory.models import AlertType

    for row in (
        _alert_qs(filters)
        .values_list(
            "created_at",
            "alert_type",
            "product__sku",
            "product__name_ar",
            "location__code",
            "batch__number",
            "current_value",
            "threshold_value",
            "is_resolved",
            "resolved_at",
        )
        .iterator(chunk_size=_common.CHUNK)
    ):
        yield (row[0], _common.labelled(row[1], AlertType.choices), *row[2:])


register(
    Dataset(
        key="stock-alerts",
        label="تنبيهات المخزون",
        group=Group.INVENTORY,
        permission=CanManageInventory,
        filters=[
            Filter(key="unresolved", label="غير المعالَجة فقط", kind="bool"),
            Filter(key="alert_type", label="نوع التنبيه", kind="choice", source="alert_types"),
        ],
        columns=lambda contact: [
            Column("الوقت", Kind.DATETIME),
            Column("النوع", width=20),
            Column("رمز المنتج", width=18),
            Column("اسم المنتج", width=32),
            Column("الموقع", width=14),
            Column("رقم الدفعة", width=20),
            Column("القيمة الحالية", Kind.INT),
            Column("الحدّ", Kind.INT),
            Column("عولج", Kind.BOOL),
            Column("وقت المعالجة", Kind.DATETIME),
        ],
        rows=_alert_rows,
        count=lambda filters: _alert_qs(filters).count(),
    )
)
