"""
Finance services.

⚠️  **Capture, not calculation.**

    Revenue is posted at the moment the order completes, from the order's stored
    figures (ADR-30), and cost from the stock movements that actually occurred.
    Nothing here recomputes a price or a tax — recomputing from today's values
    produces a report that contradicts the invoices already issued.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.errors import BusinessError, ErrorCode
from core.money import ZERO, quantize
from finance.models import (
    COGSEntry,
    Expense,
    ExpenseStatus,
    FiscalPeriod,
    RevenueEntry,
    RevenueSource,
)

logger = logging.getLogger(__name__)


def _money_sum(queryset, field: str) -> Decimal:
    """A financial sum that never returns `None`."""
    total = queryset.aggregate(
        total=Coalesce(
            Sum(field), Value(ZERO), output_field=DecimalField(max_digits=14, decimal_places=2)
        )
    )["total"]
    return quantize(total)


# ═══════════════════════════════════════════════════════════
#  Revenue capture
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def record_order_revenue(order) -> RevenueEntry | None:
    """
    Posts a completed order's revenue — **once, however often the event repeats**.

    ⚠️  Duplication is prevented by a database constraint, not by a check here alone.

        A pre-check loses the race between two concurrent events; the unique
        constraint settles it. The check here saves the exception in the common case.
    """
    existing = RevenueEntry.objects.filter(source=RevenueSource.ORDER, order=order).first()
    if existing is not None:
        logger.info("إيراد الطلب %s مقيَّد سلفًا — تجاهل", order.number)
        return existing

    # ⚠️  Tax is subtracted from the revenue.
    #
    #     The store collects it on the state's behalf and does not own it.
    #     Counting it as revenue inflates the profit by its full rate — an error
    #     that passes silently because the number looks larger, not smaller.
    net = quantize(order.grand_total - order.tax_total)

    entry = RevenueEntry.objects.create(
        source=RevenueSource.ORDER,
        order=order,
        gross=order.subtotal,
        discounts=order.discount_total,
        tax=order.tax_total,
        net=net,
        channel=order.channel,
        # ⚠️  The order's completion date, not today's date: re-running the
        #     capture for old orders would have piled them all into one month.
        # ⚠️  `localdate(...)`, not a bare `.date()`.
        #
        #     `completed_at` is stored in UTC, and taking its date directly
        #     posts a 1am Cairo sale on **the previous day**
        #     accounting day. The result: a daily close that does not match the
        #     cashier's drawer, with the discrepancy showing every night in the shift's last three
        #     hours.
        occurred_on=timezone.localdate(order.completed_at or timezone.now()),
    )

    record_cogs(entry)
    return entry


@transaction.atomic
def record_refund(order, amount: Decimal | None = None) -> RevenueEntry | None:
    """
    A return entry — **negative**.

    ⚠️  The original revenue entry is never deleted.

        Deleting it erases that the sale happened, so the order count, the
        average order value and everything built on them break. Corrections go
        through an offsetting entry.
    """
    if RevenueEntry.objects.filter(source=RevenueSource.REFUND, order=order).exists():
        return None

    original = RevenueEntry.objects.filter(source=RevenueSource.ORDER, order=order).first()
    if original is None:
        # A return for an order whose revenue was never posted — there is nothing to reverse
        logger.warning("مرتجع الطلب %s بلا قيد إيراد أصلي", order.number)
        return None

    refunded = original.net if amount is None else quantize(amount)

    return RevenueEntry.objects.create(
        source=RevenueSource.REFUND,
        order=order,
        gross=-original.gross,
        discounts=-original.discounts,
        tax=-original.tax,
        net=-refunded,
        channel=original.channel,
        # ⚠️  `localdate()`, not `now().date()`: an entry on the UTC date
        #     lands on the previous accounting day, so it is absent from today's report.
        occurred_on=timezone.localdate(),
    )


@transaction.atomic
def record_cogs(entry: RevenueEntry) -> COGSEntry:
    """
    The cost of goods sold for a revenue entry.

    ⚠️  **From the stock movements, not from the catalogue.**

        The movement carries the batch the goods left from and its cost at that
        time (FEFO). Any other calculation — an average · the last purchase cost
        — gives a profit matching no sale that happened, and it changes
        retroactively every time a new batch arrives.

    ⚠️  And it **updates the existing entry rather than creating a second**.

        A counter sale creates the order before its stock movements are linked
        to it, so the first calculation happens on zero movements.
        `pos_sale_completed` calls it again after the linking — and without the
        update it would blow up on the existing `OneToOne` constraint, leaving
        every counter sale at zero cost.
    """
    from inventory.models import MovementType, StockMovement

    movements = StockMovement.objects.filter(
        movement_type=MovementType.SALE,
        reference_type="order",
        reference_id=str(entry.order_id),
    )

    total = ZERO
    quantity = 0
    unknown = 0

    for movement in movements:
        quantity += movement.quantity
        if movement.unit_cost is None:
            # ⚠️  Goods with no batch: their cost is unknown, not zero.
            #     Zero makes the profit appear higher by their full price.
            unknown += movement.quantity
            continue
        total += movement.unit_cost * movement.quantity

    if unknown:
        logger.warning(
            "تكلفة مجهولة لـ %s وحدة في الطلب %s — بضاعة بلا دفعة",
            unknown,
            entry.order_id,
        )

    cogs, _ = COGSEntry.objects.update_or_create(
        revenue_entry=entry,
        defaults={
            "amount": quantize(total),
            "quantity": quantity,
            "unknown_quantity": unknown,
        },
    )
    return cogs


# ═══════════════════════════════════════════════════════════
#  Expenses
# ═══════════════════════════════════════════════════════════


def assert_period_open(on_date: date) -> None:
    """
    ⚠️  A closed period rejects writes.

        A report that was issued, acted upon, and then changed retroactively is
        the worst thing that can happen in a financial system: nobody knows
        which version was correct.
    """
    if FiscalPeriod.is_locked(on_date):
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail=f"الفترة {on_date.year}-{on_date.month:02d} مقفلة — قيّد التصحيح في فترة مفتوحة",
            status_code=409,
        )


@transaction.atomic
def approve_expense(expense: Expense, *, approved_by) -> Expense:
    """
    ⚠️  Approval is **an act separate from entry** — and in principle by a different person.

        Business rule 13 has not settled who approves; for now: any authorised
        finance user. The separation itself is what makes tightening it later a
        permission change rather than a rebuild.
    """
    if expense.status == ExpenseStatus.APPROVED:
        raise BusinessError(ErrorCode.CONFLICT, detail="المصروف معتمد سلفًا", status_code=409)

    assert_period_open(expense.incurred_on)

    expense.status = ExpenseStatus.APPROVED
    expense.approved_by = approved_by
    expense.approved_at = timezone.now()
    expense.rejection_reason = ""
    expense.save(
        update_fields=["status", "approved_by", "approved_at", "rejection_reason", "updated_at"]
    )
    return expense


@transaction.atomic
def reject_expense(expense: Expense, *, rejected_by, reason: str) -> Expense:
    """⚠️  The reason is mandatory: a rejection with no reason is re-entered unchanged."""
    if not reason.strip():
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="سبب الرفض إلزامي")

    expense.status = ExpenseStatus.REJECTED
    expense.approved_by = rejected_by
    expense.approved_at = timezone.now()
    expense.rejection_reason = reason
    expense.save(
        update_fields=["status", "approved_by", "approved_at", "rejection_reason", "updated_at"]
    )
    return expense


# ═══════════════════════════════════════════════════════════
#  The profit and loss statement
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ProfitAndLoss:
    """
    A profit statement for a period.

    ⚠️  Every field here is **a sum of rows that can be displayed**, not a derived figure.

        `net_profit` alone is computed — the rest of the fields open onto their entries.
    """

    start: date
    end: date

    revenue: Decimal
    refunds: Decimal
    discounts: Decimal
    tax_collected: Decimal
    net_sales: Decimal

    cogs: Decimal
    gross_profit: Decimal

    expenses: Decimal
    net_profit: Decimal

    #: ⚠️  The number of units sold at an unknown cost — it makes the gross profit
    #:     higher than reality. It is displayed, not swallowed.
    unknown_cost_units: int

    #: Draft expenses not yet approved — outside the calculation, but they must be seen
    pending_expenses: Decimal

    @property
    def gross_margin(self) -> Decimal:
        """Gross profit margin % — or zero with no sales (no division by zero)."""
        if self.net_sales == ZERO:
            return ZERO
        return quantize(self.gross_profit / self.net_sales * Decimal("100"))

    @property
    def is_reliable(self) -> bool:
        """⚠️  A report containing unknown cost is read with caution — and that is stated
        explicitly."""
        return self.unknown_cost_units == 0


def profit_and_loss(start: date, end: date) -> ProfitAndLoss:
    """
    ```text
    revenue − returns − discounts
      = net sales
      − cost of goods sold
      = gross profit
      − operating expenses
      = net profit
    ```

    ⚠️  Returns are **already negative entries**, so they are added, not subtracted.

        Subtracting them a second time doubled their effect — a sign error that
        surfaces only when a return occurs, that is, after the report has been
        issued repeatedly.
    """
    entries = RevenueEntry.objects.filter(occurred_on__gte=start, occurred_on__lte=end)

    sales = entries.filter(source=RevenueSource.ORDER)
    refunds = entries.filter(source=RevenueSource.REFUND)

    revenue = _money_sum(sales, "net")
    refunded = _money_sum(refunds, "net")  # already negative
    discounts = _money_sum(sales, "discounts")
    tax = _money_sum(sales, "tax")

    net_sales = quantize(revenue + refunded)

    cogs_rows = COGSEntry.objects.filter(revenue_entry__in=entries)
    cogs = _money_sum(cogs_rows.filter(revenue_entry__source=RevenueSource.ORDER), "amount")
    unknown_units = (
        cogs_rows.aggregate(total=Coalesce(Sum("unknown_quantity"), Value(0)))["total"] or 0
    )

    gross_profit = quantize(net_sales - cogs)

    period_expenses = Expense.objects.filter(incurred_on__gte=start, incurred_on__lte=end)
    expenses = _money_sum(period_expenses.filter(status=ExpenseStatus.APPROVED), "amount")
    pending = _money_sum(period_expenses.filter(status=ExpenseStatus.DRAFT), "amount")

    return ProfitAndLoss(
        start=start,
        end=end,
        revenue=revenue,
        refunds=refunded,
        discounts=discounts,
        tax_collected=tax,
        net_sales=net_sales,
        cogs=cogs,
        gross_profit=gross_profit,
        expenses=expenses,
        net_profit=quantize(gross_profit - expenses),
        unknown_cost_units=unknown_units,
        pending_expenses=pending,
    )


def expenses_by_category(start: date, end: date) -> list[dict]:
    """A breakdown of approved expenses by category — for reading "where the money went"."""
    rows = (
        Expense.objects.filter(
            incurred_on__gte=start,
            incurred_on__lte=end,
            status=ExpenseStatus.APPROVED,
        )
        .values("category__code", "category__name_ar", "category__name_en")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )

    return [
        {
            "code": row["category__code"],
            "name_ar": row["category__name_ar"],
            "name_en": row["category__name_en"],
            "total": str(quantize(row["total"])),
        }
        for row in rows
    ]


def revenue_by_channel(start: date, end: date) -> list[dict]:
    """
    Revenue by channel — online versus the counter.

    ⚠️  It includes returns in the same channel, or a channel with many returns
        would look more profitable than it is.
    """
    rows = (
        RevenueEntry.objects.filter(occurred_on__gte=start, occurred_on__lte=end)
        .values("channel")
        .annotate(total=Sum("net"))
        .order_by("-total")
    )
    return [
        {"channel": row["channel"] or "—", "total": str(quantize(row["total"]))} for row in rows
    ]


# ═══════════════════════════════════════════════════════════
#  Cash flow
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CashFlow:
    """
    Cash in and cash out.

    ⚠️  **Derived, not stored — and that is a decision.**

        `payments` knows the inflow and the expenses know the outflow. Storing
        it a third time creates a number that must match two sources, and at the
        first divergence between them nobody can settle it. Deriving is slower
        by an amount unnoticeable over a month, and it never lies.
    """

    start: date
    end: date
    cash_in: Decimal
    cash_out: Decimal

    @property
    def net(self) -> Decimal:
        return quantize(self.cash_in - self.cash_out)


def cash_flow(start: date, end: date) -> CashFlow:
    from payments.models import PaymentTransaction, TransactionStatus

    incoming = PaymentTransaction.objects.filter(
        created_at__date__gte=start,
        created_at__date__lte=end,
        status__in=[TransactionStatus.CAPTURED, TransactionStatus.AUTHORIZED],
    )

    outgoing = Expense.objects.filter(
        incurred_on__gte=start,
        incurred_on__lte=end,
        status=ExpenseStatus.APPROVED,
    )

    return CashFlow(
        start=start,
        end=end,
        cash_in=_money_sum(incoming, "amount"),
        cash_out=_money_sum(outgoing, "amount"),
    )
