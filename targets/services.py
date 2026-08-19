"""
Measuring target achievement.

⚠️  **Achievement is measured from the orders — and is not stored before closing.**

    A stored figure updated with every order drifts at the first cancellation or
    return that does not pass through the update path. And live measurement
    always returns the truth; closing alone freezes it, because it has become a
    document.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce

from core.errors import BusinessError, ErrorCode
from core.money import ZERO, quantize
from targets.models import MonthlyTarget, TargetStatus, TargetType


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """
    ⚠️  The last day from `calendar.monthrange`, not a written number.

        "30" breaks January and "31" breaks February — and the error shows up as
        an order dropping out of its month's measurement or being counted twice.
    """
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


@dataclass(frozen=True)
class Achievement:
    """
    An achievement measurement — **with all of its inputs**.

    ⚠️  "How much did they achieve?" is answered with a number; "why?" is
        answered with these fields. Withholding them leaves every dispute with
        the rep with no reference.
    """

    target: MonthlyTarget
    start: date
    end: date

    gross_sales: Decimal
    returns_total: Decimal
    net_sales: Decimal
    gross_profit: Decimal
    orders_count: int
    customers_count: int

    achieved_value: Decimal
    achievement_percent: Decimal

    @property
    def meets_minimum(self) -> bool:
        return self.achievement_percent >= self.target.minimum_achievement_percent


def _money(queryset, field: str) -> Decimal:
    total = queryset.aggregate(
        total=Coalesce(
            Sum(field),
            Value(ZERO),
            output_field=DecimalField(max_digits=16, decimal_places=2),
        )
    )["total"]
    return quantize(total)


def measure(target: MonthlyTarget) -> Achievement:
    """
    Measures a target's achievement from its owner's orders in its month.

    ⚠️  **Returns are deducted from the achievement** (business rule 16 — a recommendation).

        Not deducting them lets a rep who sells, takes a return, and sells again
        hit their target twice on the same goods. And the deduction comes from
        the **original** employee, not whoever handled the return: they own the
        sale that was reversed.
    """
    from orders.models import Order, OrderStatus

    start, end = month_bounds(target.year, target.month)

    period = Order.objects.filter(
        owner_employee=target.employee.user,
        created_at__date__gte=start,
        created_at__date__lte=end,
    )

    # ⚠️  Cancelled orders are outside the measurement entirely: nothing was sold in them.
    #     A return, however, was sold and then came back — it is subtracted, not ignored.
    sold = period.exclude(status__in=[OrderStatus.CANCELLED, OrderStatus.REFUNDED])
    returned = period.filter(status=OrderStatus.REFUNDED)

    gross = _money(sold, "grand_total")
    returns_total = _money(returned, "grand_total")
    net = quantize(gross - returns_total)

    orders_count = sold.count()
    customers_count = sold.values("customer").distinct().count()
    profit = _gross_profit(sold, returned)

    achieved = {
        TargetType.SALES_AMOUNT: gross,
        TargetType.NET_SALES: net,
        TargetType.GROSS_PROFIT: profit,
        TargetType.ORDER_COUNT: Decimal(orders_count),
        TargetType.CUSTOMER_COUNT: Decimal(customers_count),
    }[target.target_type]

    # ⚠️  A division-by-zero guard: a target of zero is possible (a training month).
    percent = (
        quantize(achieved / target.target_value * Decimal("100"))
        if target.target_value > ZERO
        else ZERO
    )

    return Achievement(
        target=target,
        start=start,
        end=end,
        gross_sales=gross,
        returns_total=returns_total,
        net_sales=net,
        gross_profit=profit,
        orders_count=orders_count,
        customers_count=customers_count,
        achieved_value=quantize(achieved),
        achievement_percent=percent,
    )


def _gross_profit(sold, returned) -> Decimal:
    """
    Gross profit = net sales − cost of goods sold.

    ⚠️  **The cost comes from `finance`, not from a parallel calculation.**

        `COGSEntry` is computed from the batch that actually shipped (FEFO).
        Recomputing it here produces a profit figure that contradicts the profit
        statement — and nobody knows which to believe once a commission is paid
        against one of them.

    ⚠️  And an order **of unknown cost is excluded from the calculation entirely**.

        A cost entry with a zero quantity means no stock movement was found for
        the order — not that its goods were free. Including it at zero cost
        makes its profit **equal to its full selling price**, so a commission is
        paid on profit that never materialised.

        Exclusion is the safe direction: a commission short of what is due is
        corrected with an entry; one paid on a phantom is never recovered.
    """
    from finance.models import COGSEntry, RevenueEntry, RevenueSource

    sold_ids = list(sold.values_list("id", flat=True))
    if not sold_ids:
        return ZERO

    entries = RevenueEntry.objects.filter(source=RevenueSource.ORDER, order_id__in=sold_ids)

    # ⚠️  Only orders with **established** cost.
    #
    #     `quantity > 0` means stock movements were genuinely found,
    #     and `unknown_quantity = 0` means every unit of them had a known
    #     cost. Anything else is profit that cannot be proved.
    priced = COGSEntry.objects.filter(revenue_entry__in=entries, quantity__gt=0, unknown_quantity=0)
    entries = entries.filter(cogs__in=priced)

    net_revenue = _money(entries, "net")
    cost = _money(priced, "amount")

    # Returns are deducted from the profit too — by their net, not their gross
    returned_ids = list(returned.values_list("id", flat=True))
    if returned_ids:
        refunds = RevenueEntry.objects.filter(
            source=RevenueSource.REFUND, order_id__in=returned_ids
        )
        # Return entries are already negative, so they are added
        net_revenue = quantize(net_revenue + _money(refunds, "net"))

    return quantize(net_revenue - cost)


@transaction.atomic
def close_target(target: MonthlyTarget, *, by=None) -> MonthlyTarget:
    """
    ⚠️  Closing happens **once** — and repeating it is refused explicitly.

        A commission that gets paid is built on the snapshot; rewriting it
        changes an amount that has left the treasury.
    """
    if target.is_closed:
        raise BusinessError(ErrorCode.CONFLICT, detail="الهدف مقفل سلفًا", status_code=409)

    if target.status != TargetStatus.ACTIVE:
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail="لا يُقفَل إلا هدف نشط — فعّله أولًا",
            status_code=409,
        )

    result = measure(target)
    target.close(achieved=result.achieved_value, percent=result.achievement_percent, by=by)
    return target


def activate(target: MonthlyTarget) -> MonthlyTarget:
    if target.is_closed:
        raise BusinessError(
            ErrorCode.CONFLICT, detail="الهدف مقفل — لا يُعاد تفعيله", status_code=409
        )

    target.status = TargetStatus.ACTIVE
    target.save(update_fields=["status", "updated_at"])
    return target


def current_target(employee, on_date: date | None = None) -> MonthlyTarget | None:
    """
    The current month's target — **the active one alone**.

    ⚠️  A draft is not shown to the rep: a figure not yet approved is one they
        build an expectation on and it then changes.
    """
    today = on_date or date.today()
    return MonthlyTarget.objects.filter(
        employee=employee,
        year=today.year,
        month=today.month,
        status__in=[TargetStatus.ACTIVE, TargetStatus.CLOSED],
    ).first()


def bulk_create_month(year: int, month: int, rows: list[dict], *, actor=None) -> int:
    """
    Create a month's targets for a whole team.

    ⚠️  Existing ones are **skipped, not overwritten**.

        The bulk creation is run repeatedly to add a new employee; and
        overwriting the existing ones erases a manual edit to a particular rep's target.
    """
    from employees.models import EmployeeProfile

    created = 0
    for row in rows:
        employee = EmployeeProfile.objects.filter(pk=row["employee"]).first()
        if employee is None:
            continue

        _, was_created = MonthlyTarget.objects.get_or_create(
            employee=employee,
            year=year,
            month=month,
            defaults={
                "target_type": row.get("target_type", TargetType.NET_SALES),
                "target_value": row["target_value"],
                "minimum_achievement_percent": row.get("minimum_achievement_percent", ZERO),
                "note": row.get("note", ""),
            },
        )
        created += int(was_created)

    return created
