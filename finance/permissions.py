"""
Finance permissions.

⚠️  **Seeing profits is not an automatic admin permission.**

    The admin panel is opened by a catalogue manager, a customer service
    employee and a warehouse supervisor. None of them needs to know the profit
    margin, nor colleagues' salaries, nor the shop's rent. Tying it to
    `IsAdminAccount` opened it to everyone without anyone deciding so.

⚠️  And business rule 14 settled **the side**: revenue and expenses are viewed
    from the admin portal. It did not settle **who** within it — so the default
    here is the stricter one: an explicit Django permission granted by decision.
"""

from rest_framework.permissions import BasePermission

#: ⚠️  A single permission governs all reading.
#:
#:     Splitting it into "sees revenue", "sees expenses" and "sees profit"
#:     is an illusion: whoever sees the first two subtracts. The only real
#:     separation is between whoever reads the report and whoever enters an expense.
VIEW_FINANCE = "finance.view_revenueentry"
MANAGE_EXPENSES = "finance.add_expense"
APPROVE_EXPENSES = "finance.change_expense"


class _PermissionRequired(BasePermission):
    """
    ⚠️  The owner (`is_superuser`) always passes.

        Without it the first user of a new system cannot open a finance screen
        to grant the permissions — a deadlock resolved through `manage.py`.
    """

    permission = ""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        return user.has_perm(self.permission)


class CanViewFinance(_PermissionRequired):
    message = "التقارير المالية تحتاج صلاحية صريحة"
    permission = VIEW_FINANCE


class CanManageExpenses(_PermissionRequired):
    message = "إدخال المصروفات يحتاج صلاحية صريحة"
    permission = MANAGE_EXPENSES


class CanApproveExpenses(_PermissionRequired):
    """
    ⚠️  Approval is **a permission separate from entry**.

        Someone who enters an expense and approves it themselves makes approval
        a signature on a blank page. The separation is the entire value of the step.
    """

    message = "اعتماد المصروفات يحتاج صلاحية صريحة"
    permission = APPROVE_EXPENSES
