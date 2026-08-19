"""
Employee services.

⚠️  **Performance is computed from the orders, never stored.**

    A sales figure stored on the employee profile drifts at the first
    cancellation or return that does not pass through the update path. And the
    rep reads their number daily and builds a commission expectation on it — so
    drift is a complaint waiting to happen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.errors import BusinessError, ErrorCode
from core.money import ZERO, quantize
from employees.models import (
    AssignmentStatus,
    CustomerAssignment,
    EmployeeProfile,
)

logger = logging.getLogger(__name__)


def _money(queryset, field: str) -> Decimal:
    total = queryset.aggregate(
        total=Coalesce(
            Sum(field),
            Value(ZERO),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )["total"]
    return quantize(total)


# ═══════════════════════════════════════════════════════════
#  Roles and permissions
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def sync_role_permissions(role) -> None:
    """
    Synchronises the role's permissions into the Django group that actually confers them.

    ⚠️  **Without this call the permissions are decoration.**

        `user.has_perm()` reads the user's own permissions and their groups, and
        knows nothing at all about the `EmployeeRole.permissions` table. Leaving
        it unsynchronised means a role that looks configured in the panel while
        every permission check fails — and then a custom checker gets written
        that bypasses Django's system.
    """
    from django.contrib.auth.models import Group

    if role.group is None:
        group, _created = Group.objects.get_or_create(name=f"employee:{role.code}")
        role.group = group
        role.save(update_fields=["group", "updated_at"])

    role.group.permissions.set(role.permissions.all())


@transaction.atomic
def apply_role_permissions(employee: EmployeeProfile) -> None:
    """
    Puts the employee into their role's group — **without saving the profile**.

    ⚠️  **The separation from `set_role` is a necessity, not tidiness.**

        The `post_save` signal calls this one; and were it to save the profile,
        it would re-fire the signal endlessly. That genuinely happened: the
        recursion was swallowed by the signal's `except Exception`, so the save
        looked successful while every operation burned a thousand stack frames
        and logged an exception nobody read.

    ⚠️  And it **removes the other roles' groups**.

        Leaving them makes the employee accumulate the permissions of every role
        they have passed through — so a rep moved to customer service remains
        able to create orders, and it shows on no screen.
    """
    from django.contrib.auth.models import Group

    sync_role_permissions(employee.role)

    employee.user.groups.remove(
        *Group.objects.filter(name__startswith="employee:").exclude(pk=employee.role.group_id)
    )
    employee.user.groups.add(employee.role.group)


@transaction.atomic
def set_role(employee: EmployeeProfile, role) -> EmployeeProfile:
    """
    Changes the employee's role — and the signal handles the groups after the save.
    """
    employee.role = role
    employee.save(update_fields=["role", "updated_at"])
    return employee


def revoke_permissions(employee: EmployeeProfile) -> None:
    """
    ⚠️  Deactivating an employee **withdraws their group immediately**.

        Relying on `is_active` alone protects this domain's endpoints only; in
        the rest of the system `has_perm` keeps saying "yes" to a departed
        employee for as long as they remain in the group.
    """
    from django.contrib.auth.models import Group

    employee.user.groups.remove(*Group.objects.filter(name__startswith="employee:"))


# ═══════════════════════════════════════════════════════════
#  Assignment
# ═══════════════════════════════════════════════════════════


def assigned_customers(employee: EmployeeProfile):
    """
    This employee's **current** customers.

    ⚠️  The sole basis for everything the rep sees.

        Every query in their portal goes through here; and forgetting the filter
        on one endpoint exposes the entire customer list to someone assigned three.
    """
    from customers.models import CustomerProfile

    return CustomerProfile.objects.filter(
        assignments__employee=employee,
        assignments__status=AssignmentStatus.ACTIVE,
    ).distinct()


def is_assigned(employee: EmployeeProfile, customer) -> bool:
    return CustomerAssignment.objects.filter(
        employee=employee, customer=customer, status=AssignmentStatus.ACTIVE
    ).exists()


@transaction.atomic
def assign_customer(customer, employee: EmployeeProfile, *, actor=None, note: str = ""):
    """
    Transfers a customer to an employee — **and ends their previous assignment**.

    ⚠️  Ending before creating, and in the same transaction.

        The unique constraint forbids two current assignments; creating before
        ending is rejected with a raw integrity error the admin cannot read. And
        the reverse — ending with no creation after it — leaves a customer with
        no owner should what follows fail.
    """
    if not employee.is_active:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الموظف ليس على رأس العمل")

    current = CustomerAssignment.objects.filter(
        customer=customer, status=AssignmentStatus.ACTIVE
    ).first()

    if current is not None:
        if current.employee_id == employee.pk:
            return current

        current.status = AssignmentStatus.ENDED
        current.ended_at = timezone.now()
        current.save(update_fields=["status", "ended_at", "updated_at"])

    return CustomerAssignment.objects.create(
        customer=customer,
        employee=employee,
        assigned_by=actor,
        note=note,
    )


@transaction.atomic
def end_assignment(customer, *, actor=None) -> int:
    """
    ⚠️  Ending **does not delete the record**.

        Commission is calculated on whoever was responsible at the time of sale;
        deleting the ended assignment leaves every old order unattributed.
    """
    return CustomerAssignment.objects.filter(
        customer=customer, status=AssignmentStatus.ACTIVE
    ).update(status=AssignmentStatus.ENDED, ended_at=timezone.now())


# ═══════════════════════════════════════════════════════════
#  Performance
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Performance:
    """
    An employee's performance over a period.

    ⚠️  **No target and no commission — phase 11.**

        Putting zero in their place made the rep read "your achievement is 0%"
        and take it for poor performance rather than a system not yet
        configured. The absence is declared explicitly rather than filled with a
        false number.
    """

    employee: EmployeeProfile
    start: date
    end: date

    orders_count: int
    gross_sales: Decimal
    returns_total: Decimal
    net_sales: Decimal

    customers_count: int
    new_customers: int

    @property
    def average_order(self) -> Decimal:
        if self.orders_count == 0:
            return ZERO
        return quantize(self.net_sales / self.orders_count)


def performance(employee: EmployeeProfile, start: date, end: date) -> Performance:
    """
    ⚠️  What is attributed to the employee is `owner_employee`, not `created_by`.

        The rep is responsible for all their customers' orders — including those
        the customers placed themselves on the website. Restricting it to what
        they typed by hand makes their success in converting a customer to
        self-service **lower** their number.
    """
    from orders.models import Order, OrderStatus

    if start > end:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="بداية الفترة بعد نهايتها")

    period = Order.objects.filter(
        owner_employee=employee.user,
        created_at__date__gte=start,
        created_at__date__lte=end,
    )

    # ⚠️  Cancelled orders are excluded from the calculation entirely: nothing was sold.
    #     A return, however, was sold and then came back — it is subtracted, not ignored.
    sold = period.exclude(status__in=[OrderStatus.CANCELLED, OrderStatus.REFUNDED])
    returned = period.filter(status=OrderStatus.REFUNDED)

    gross = _money(sold, "grand_total")
    returns_total = _money(returned, "grand_total")

    customers = assigned_customers(employee)

    return Performance(
        employee=employee,
        start=start,
        end=end,
        orders_count=sold.count(),
        gross_sales=gross,
        returns_total=returns_total,
        net_sales=quantize(gross - returns_total),
        customers_count=customers.count(),
        new_customers=CustomerAssignment.objects.filter(
            employee=employee,
            started_at__date__gte=start,
            started_at__date__lte=end,
        ).count(),
    )


def monthly_history(employee: EmployeeProfile, months: int = 6) -> list[dict]:
    """
    The previous months' performance.

    ⚠️  **One aggregated query, not one query per month.**

        A loop over twelve months means twelve queries on every dashboard open —
        and it is the first screen every rep opens each morning.
    """
    from django.db.models.functions import TruncMonth

    from orders.models import Order, OrderStatus

    # ⚠️  Subtracting by months, not by "31 days".
    #
    #     Subtracting a fixed day count drifts: six months × 31 days overshoots
    #     half a year by several days, so an incomplete seventh month creeps in
    #     and it looks as though the rep's performance collapsed in the oldest row.
    today = timezone.localdate()
    month_index = today.year * 12 + (today.month - 1) - (months - 1)
    first_month = date(month_index // 12, month_index % 12 + 1, 1)

    rows = (
        Order.objects.filter(
            owner_employee=employee.user,
            created_at__date__gte=first_month,
        )
        .exclude(status=OrderStatus.CANCELLED)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(
            orders=Count("id"),
            gross=Sum("grand_total"),
            returned=Sum("grand_total", filter=Q(status=OrderStatus.REFUNDED), default=Value(ZERO)),
        )
        .order_by("-month")
    )

    return [
        {
            "month": row["month"].date().isoformat()[:7],
            "orders": row["orders"],
            "gross": str(quantize(row["gross"] or ZERO)),
            "returns": str(quantize(row["returned"] or ZERO)),
            "net": str(quantize((row["gross"] or ZERO) - (row["returned"] or ZERO))),
        }
        for row in rows
    ]


# ═══════════════════════════════════════════════════════════
#  Selling on the customer's behalf
# ═══════════════════════════════════════════════════════════


def assert_may_act_for(employee: EmployeeProfile, customer) -> None:
    """
    ⚠️  **The guard that stops a rep selling to a customer who is not theirs.**

        Without this check any rep creates an order for any customer by passing
        an id — so the sale is attributed to the wrong person and its commission
        goes to the wrong person, and whoever it belonged to discovers it at the
        end of the month rather than before.
    """
    if not employee.is_active:
        raise BusinessError(
            ErrorCode.PERMISSION_DENIED, detail="الحساب موقوف عن العمل", status_code=403
        )

    if not is_assigned(employee, customer):
        # ⚠️  404, not 403: the difference reveals the customer's existence and activity
        #     to anyone trying ids.
        raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)
