"""
Supplier and purchasing datasets.

⚠️  A supplier's contact details sit behind the same gate as a customer's.

    The reasoning is not identical but it lands in the same place: a list of
    every supplier with the buyer's direct line is exactly what a competitor
    wants, and exactly what a departing employee can carry out. The analysis
    version — who we buy from, how much, how fast they deliver — needs none of it.
"""

from __future__ import annotations

from core.permissions import CanManageInventory
from reporting.export.datasets import _common
from reporting.export.registry import Column, Dataset, Filter, Group, register
from reporting.export.writer import Kind
from suppliers.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderStatus,
    Supplier,
    SupplierLedgerEntry,
    SupplierLedgerKind,
)

# ═══════════════════════════════════════════════════════════
#  Suppliers
# ═══════════════════════════════════════════════════════════


def _supplier_qs(filters: dict):
    queryset = Supplier.objects.all()
    if filters.get("active_only") == "true":
        queryset = queryset.filter(is_active=True)
    return queryset.order_by("name_ar")


def _supplier_columns(include_contact: bool) -> list[Column]:
    columns = [
        Column("الرمز", width=16),
        Column("الاسم بالعربية", width=30),
        Column("الاسم بالإنجليزية", width=30),
        Column("مدة السداد (يوم)", Kind.INT),
        Column("مدة التوريد (يوم)", Kind.INT),
        Column("الرقم الضريبي", width=20),
        Column("السجل التجاري", width=20),
        Column("مفعّل", Kind.BOOL),
    ]
    if include_contact:
        columns += [
            Column("مسؤول الاتصال", width=24, sensitive=True),
            Column("الهاتف", width=18, sensitive=True),
            Column("البريد", width=28, sensitive=True),
            Column("العنوان", width=32, sensitive=True),
        ]
    return columns


def _supplier_rows(filters: dict, include_contact: bool):
    fields = (
        "code",
        "name_ar",
        "name_en",
        "payment_terms_days",
        "lead_time_days",
        "tax_number",
        "commercial_register",
        "is_active",
    )
    if include_contact:
        fields += ("contact_person", "phone", "email", "address")

    yield from _supplier_qs(filters).values_list(*fields).iterator(chunk_size=_common.CHUNK)


register(
    Dataset(
        key="suppliers",
        label="الموردون",
        group=Group.PURCHASING,
        permission=CanManageInventory,
        has_contact=True,
        filters=[Filter(key="active_only", label="المفعّلون فقط", kind="bool")],
        columns=_supplier_columns,
        rows=_supplier_rows,
        count=lambda filters: _supplier_qs(filters).count(),
    )
)


# ═══════════════════════════════════════════════════════════
#  Purchase orders
# ═══════════════════════════════════════════════════════════


def _po_qs(filters: dict):
    queryset = PurchaseOrder.objects.select_related("supplier", "location", "created_by")
    queryset = _common.apply_period(queryset, filters, "created_at")

    if status := filters.get("status"):
        queryset = queryset.filter(status=status)
    if supplier := filters.get("supplier"):
        queryset = queryset.filter(supplier__code=supplier)

    return queryset.order_by("-created_at")


def _po_rows(filters: dict, include_contact: bool):
    for row in (
        _po_qs(filters)
        .values_list(
            "number",
            "created_at",
            "supplier__code",
            "supplier__name_ar",
            "location__code",
            "status",
            "subtotal",
            "expected_on",
            "sent_at",
            "received_at",
            "created_by__email",
        )
        .iterator(chunk_size=_common.CHUNK)
    ):
        yield (*row[:5], _common.labelled(row[5], PurchaseOrderStatus.choices), *row[6:])


register(
    Dataset(
        key="purchase-orders",
        label="أوامر الشراء",
        group=Group.PURCHASING,
        permission=CanManageInventory,
        filters=[
            Filter(key="start", label="من تاريخ", kind="date"),
            Filter(key="end", label="إلى تاريخ", kind="date"),
            Filter(key="status", label="الحالة", kind="choice", source="po_statuses"),
            Filter(key="supplier", label="المورّد", kind="choice", source="suppliers"),
        ],
        columns=lambda contact: [
            Column("رقم الأمر", width=20),
            Column("التاريخ", Kind.DATETIME),
            Column("رمز المورّد", width=16),
            Column("المورّد", width=30),
            Column("الموقع", width=14),
            Column("الحالة", width=18),
            Column("الإجمالي", Kind.MONEY),
            Column("التسليم المتوقع", Kind.DATE),
            Column("أُرسل في", Kind.DATETIME),
            Column("استُلم في", Kind.DATETIME),
            Column("أنشأه", width=26),
        ],
        rows=_po_rows,
        count=lambda filters: _po_qs(filters).count(),
    )
)


# ═══════════════════════════════════════════════════════════
#  Purchase order lines
# ═══════════════════════════════════════════════════════════


def _po_line_qs(filters: dict):
    queryset = PurchaseOrderLine.objects.select_related("order", "order__supplier", "product")
    queryset = _common.apply_period(queryset, filters, "order__created_at")

    if supplier := filters.get("supplier"):
        queryset = queryset.filter(order__supplier__code=supplier)
    if filters.get("outstanding") == "true":
        # ⚠️  What is still owed to us, which is the reason this sheet exists.
        from django.db.models import F

        queryset = queryset.filter(quantity_received__lt=F("quantity_ordered"))

    return queryset.order_by("-order__created_at", "order__number")


def _po_line_rows(filters: dict, include_contact: bool):
    for row in (
        _po_line_qs(filters)
        .values_list(
            "order__number",
            "order__created_at",
            "order__supplier__name_ar",
            "product__sku",
            "product__name_ar",
            "quantity_ordered",
            "quantity_received",
            "quantity_returned",
            "unit_cost",
            "list_cost",
        )
        .iterator(chunk_size=_common.CHUNK)
    ):
        ordered, received = row[5], row[6]
        outstanding = max(0, ordered - received)
        yield (*row, outstanding, (row[8] or 0) * received)


register(
    Dataset(
        key="purchase-order-lines",
        label="بنود أوامر الشراء",
        group=Group.PURCHASING,
        permission=CanManageInventory,
        note="سطر لكل منتج — بالمتبقي غير المستلم",
        filters=[
            Filter(key="start", label="من تاريخ", kind="date"),
            Filter(key="end", label="إلى تاريخ", kind="date"),
            Filter(key="supplier", label="المورّد", kind="choice", source="suppliers"),
            Filter(key="outstanding", label="غير المستلم فقط", kind="bool"),
        ],
        columns=lambda contact: [
            Column("رقم الأمر", width=20),
            Column("تاريخ الأمر", Kind.DATETIME),
            Column("المورّد", width=30),
            Column("رمز المنتج", width=18),
            Column("اسم المنتج", width=32),
            Column("المطلوب", Kind.INT),
            Column("المستلم", Kind.INT),
            Column("المرتجع", Kind.INT),
            Column("تكلفة الوحدة", Kind.MONEY),
            Column("التكلفة المعلنة", Kind.MONEY),
            Column("المتبقي", Kind.INT),
            Column("قيمة المستلم", Kind.MONEY),
        ],
        rows=_po_line_rows,
        count=lambda filters: _po_line_qs(filters).count(),
    )
)


# ═══════════════════════════════════════════════════════════
#  Supplier ledger
# ═══════════════════════════════════════════════════════════


def _supplier_ledger_qs(filters: dict):
    queryset = SupplierLedgerEntry.objects.select_related("supplier")
    queryset = _common.apply_period(queryset, filters, "created_at")
    if supplier := filters.get("supplier"):
        queryset = queryset.filter(supplier__code=supplier)
    return queryset.order_by("supplier__name_ar", "created_at")


def _supplier_ledger_rows(filters: dict, include_contact: bool):
    for row in (
        _supplier_ledger_qs(filters)
        .values_list(
            "supplier__code",
            "supplier__name_ar",
            "created_at",
            "kind",
            "amount",
            "reference",
            "note",
        )
        .iterator(chunk_size=_common.CHUNK)
    ):
        yield (*row[:3], _common.labelled(row[3], SupplierLedgerKind.choices), *row[4:])


register(
    Dataset(
        key="supplier-ledger",
        label="كشف حساب الموردين",
        group=Group.PURCHASING,
        permission=CanManageInventory,
        filters=[
            Filter(key="supplier", label="المورّد", kind="choice", source="suppliers"),
            Filter(key="start", label="من تاريخ", kind="date"),
            Filter(key="end", label="إلى تاريخ", kind="date"),
        ],
        columns=lambda contact: [
            Column("رمز المورّد", width=16),
            Column("المورّد", width=30),
            Column("الوقت", Kind.DATETIME),
            Column("النوع", width=18),
            Column("المبلغ", Kind.MONEY),
            Column("المرجع", width=20),
            Column("ملاحظة", width=30),
        ],
        rows=_supplier_ledger_rows,
        count=lambda filters: _supplier_ledger_qs(filters).count(),
    )
)
