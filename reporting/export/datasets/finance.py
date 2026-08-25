"""
Financial datasets.

⚠️  Everything here is behind `CanViewReports`, and that permission is
    `finance.view_revenueentry` — the same one guarding the P&L.

    Whoever can see the profit can export the rows behind it; the two are the
    same disclosure at different resolutions, and splitting them into two
    permissions would mean one of them getting granted by oversight.

⚠️  And the profit columns are **computed, not formulas**.

    A margin written as `=D2-E2` recalculates when the file is opened and breaks
    the moment a reader sorts or inserts a column. A number is what it says it
    is in six months.
"""

from __future__ import annotations

from commissions.models import CommissionRecord
from core.permissions import CanViewReports
from finance.models import Expense, ExpenseStatus, RevenueEntry, RevenueSource
from reporting.export.datasets import _common
from reporting.export.registry import Column, Dataset, Filter, Group, register
from reporting.export.writer import Kind

# ═══════════════════════════════════════════════════════════
#  Revenue and cost
# ═══════════════════════════════════════════════════════════


def _revenue_qs(filters: dict):
    queryset = RevenueEntry.objects.select_related("order")
    queryset = _common.apply_date_period(queryset, filters, "occurred_on")
    if source := filters.get("source"):
        queryset = queryset.filter(source=source)
    if channel := filters.get("channel"):
        queryset = queryset.filter(channel=channel)
    return queryset.order_by("-occurred_on")


def _revenue_rows(filters: dict, include_contact: bool):
    from orders.models import OrderChannel

    # ⚠️  The cost is read through the reverse relation rather than recomputed
    #     from batches. `COGSEntry` is what `finance` actually posted, and a
    #     second calculation here would produce a profit figure that disagrees
    #     with the P&L — the exact failure the commissions layer contract calls
    #     out, one domain over.
    for row in (
        _revenue_qs(filters)
        .values_list(
            "occurred_on",
            "order__number",
            "source",
            "channel",
            "gross",
            "discounts",
            "tax",
            "net",
            "cogs__amount",
            "cogs__quantity",
            "cogs__unknown_quantity",
        )
        .iterator(chunk_size=_common.CHUNK)
    ):
        net, cost = row[7], row[8]
        profit = (net - cost) if (net is not None and cost is not None) else None
        yield (
            row[0],
            row[1],
            _common.labelled(row[2], RevenueSource.choices),
            _common.labelled(row[3], OrderChannel.choices),
            *row[4:11],
            profit,
        )


register(
    Dataset(
        key="revenue",
        label="الإيرادات والتكلفة",
        group=Group.FINANCE,
        permission=CanViewReports,
        note="صافي الإيراد وتكلفة المبيعات والربح لكل قيد",
        filters=[
            Filter(key="start", label="من تاريخ", kind="date"),
            Filter(key="end", label="إلى تاريخ", kind="date"),
            Filter(key="source", label="المصدر", kind="choice", source="revenue_sources"),
            Filter(key="channel", label="القناة", kind="choice", source="order_channels"),
        ],
        columns=lambda contact: [
            Column("التاريخ", Kind.DATE),
            Column("رقم الطلب", width=20),
            Column("المصدر", width=16),
            Column("القناة", width=14),
            Column("الإجمالي", Kind.MONEY),
            Column("الخصومات", Kind.MONEY),
            Column("الضريبة", Kind.MONEY),
            Column("الصافي", Kind.MONEY),
            Column("تكلفة المبيعات", Kind.MONEY),
            Column("الكمية", Kind.INT),
            Column("كمية بتكلفة مجهولة", Kind.INT),
            Column("الربح", Kind.MONEY),
        ],
        rows=_revenue_rows,
        count=lambda filters: _revenue_qs(filters).count(),
    )
)


# ═══════════════════════════════════════════════════════════
#  Expenses
# ═══════════════════════════════════════════════════════════


def _expense_qs(filters: dict):
    queryset = Expense.objects.select_related("category", "entered_by", "approved_by")
    queryset = _common.apply_date_period(queryset, filters, "incurred_on")
    if status := filters.get("status"):
        queryset = queryset.filter(status=status)
    if category := filters.get("category"):
        queryset = queryset.filter(category__code=category)
    return queryset.order_by("-incurred_on")


def _expense_rows(filters: dict, include_contact: bool):
    # ⚠️  `attachment` is a file path under MEDIA_ROOT and is not exported —
    #     same rule as the verification documents. A receipt is reachable
    #     through the panel with a permission check, not through a cell.
    for row in (
        _expense_qs(filters)
        .values_list(
            "incurred_on",
            "category__name_ar",
            "amount",
            "vendor_name",
            "reference",
            "payment_mean",
            "status",
            "entered_by__email",
            "approved_by__email",
            "approved_at",
            "note",
        )
        .iterator(chunk_size=_common.CHUNK)
    ):
        yield (*row[:6], _common.labelled(row[6], ExpenseStatus.choices), *row[7:])


register(
    Dataset(
        key="expenses",
        label="المصروفات",
        group=Group.FINANCE,
        permission=CanViewReports,
        filters=[
            Filter(key="start", label="من تاريخ", kind="date"),
            Filter(key="end", label="إلى تاريخ", kind="date"),
            Filter(key="status", label="الحالة", kind="choice", source="expense_statuses"),
            Filter(key="category", label="البند", kind="choice", source="expense_categories"),
        ],
        columns=lambda contact: [
            Column("التاريخ", Kind.DATE),
            Column("البند", width=24),
            Column("المبلغ", Kind.MONEY),
            Column("المورّد/الجهة", width=28),
            Column("المرجع", width=20),
            Column("وسيلة الدفع", width=16),
            Column("الحالة", width=16),
            Column("أدخله", width=26),
            Column("اعتمده", width=26),
            Column("وقت الاعتماد", Kind.DATETIME),
            Column("ملاحظة", width=30),
        ],
        rows=_expense_rows,
        count=lambda filters: _expense_qs(filters).count(),
    )
)


# ═══════════════════════════════════════════════════════════
#  Commissions
# ═══════════════════════════════════════════════════════════


def _commission_qs(filters: dict):
    queryset = CommissionRecord.objects.select_related("employee", "employee__user", "scheme")

    if year := filters.get("year"):
        queryset = queryset.filter(year=year)
    if month := filters.get("month"):
        queryset = queryset.filter(month=month)
    if status := filters.get("status"):
        queryset = queryset.filter(status=status)

    return queryset.order_by("-year", "-month", "-amount")


def _commission_rows(filters: dict, include_contact: bool):
    from commissions.models import CommissionStatus

    for row in (
        _commission_qs(filters)
        .values_list(
            "year",
            "month",
            "employee__employee_number",
            "employee__user__first_name",
            "employee__user__last_name",
            "scheme__name_ar",
            "orders_count",
            "gross_sales",
            "returns_total",
            "net_sales",
            "cost_total",
            "gross_profit",
            "target_value",
            "achieved_value",
            "achievement_percent",
            "tier_label",
            "rate",
            "amount",
            "status",
        )
        .iterator(chunk_size=_common.CHUNK)
    ):
        # ⚠️  The employee's name is **not** behind the contact gate.
        #
        #     A commission sheet without a name is unusable, and the permission
        #     that opens this file is the one that already exposes every
        #     employee's performance by name in the reports. The gate exists for
        #     contact details — a way to reach a person outside the company —
        #     and a first name in a payroll row is not that.
        first, last = row[3] or "", row[4] or ""
        yield (
            row[0],
            row[1],
            row[2],
            f"{first} {last}".strip(),
            *row[5:18],
            _common.labelled(row[18], CommissionStatus.choices),
        )


register(
    Dataset(
        key="commissions",
        label="عمولات الموظفين",
        group=Group.FINANCE,
        permission=CanViewReports,
        filters=[
            Filter(key="year", label="السنة", kind="text"),
            Filter(key="month", label="الشهر", kind="text"),
            Filter(key="status", label="الحالة", kind="choice", source="commission_statuses"),
        ],
        columns=lambda contact: [
            Column("السنة", Kind.INT),
            Column("الشهر", Kind.INT),
            Column("رقم الموظف", width=16),
            Column("الموظف", width=28),
            Column("الخطة", width=24),
            Column("عدد الطلبات", Kind.INT),
            Column("المبيعات", Kind.MONEY),
            Column("المرتجعات", Kind.MONEY),
            Column("صافي المبيعات", Kind.MONEY),
            Column("التكلفة", Kind.MONEY),
            Column("مجمل الربح", Kind.MONEY),
            Column("المستهدف", Kind.MONEY),
            Column("المحقّق", Kind.MONEY),
            Column("نسبة التحقيق %", Kind.MONEY),
            Column("الشريحة", width=18),
            Column("المعدل %", Kind.MONEY),
            Column("العمولة", Kind.MONEY),
            Column("الحالة", width=16),
        ],
        rows=_commission_rows,
        count=lambda filters: _commission_qs(filters).count(),
    )
)
