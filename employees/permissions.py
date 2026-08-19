"""
Staff portal permissions.

⚠️  **An employee is never granted admin permissions — not even "temporarily".**

    A sales rep sees their own customers and creates orders for them. They do
    not see the full customer list, do not edit prices, and do not suspend
    accounts. And "temporarily" is the word that precedes the longest-lived holes.

⚠️  And the permissions are **fine-grained, not one bundle**.

    "Employee" is not a permission: a sales rep creates orders and does not see
    profits; a warehouse employee sees the stock and creates no orders. A single
    bundle means every employee holds what the broadest of them holds.
"""

from rest_framework.permissions import BasePermission

from accounts.models import AccountType

#: The fine-grained permissions — assigned to roles from the panel, never to people
VIEW_DASHBOARD = "employees.view_employeeprofile"
VIEW_CUSTOMERS = "employees.view_customerassignment"
CREATE_ORDER = "orders.add_order"
MANAGE_TEAM = "employees.change_customerassignment"


class IsEmployee(BasePermission):
    """
    ⚠️  Admins pass too — but for a specific reason.

        The sales manager is an admin by account, and needs to open the staff
        portal to see what their team sees before deciding. Blocking them
        outright forced them to create a dummy employee account for themselves.
    """

    message = "بوابة الموظفين للموظفين والمديرين"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return user.account_type in (AccountType.EMPLOYEE, AccountType.ADMIN)


class HasEmployeeProfile(IsEmployee):
    """
    ⚠️  The profile **and being currently employed** — both conditions together.

        An employee who has left while their account is still active with a
        valid token in their hand is the most obvious hole in any sales system.
        `is_active` on the profile closes it on the first request rather than
        when the token expires.
    """

    message = "لا ملف موظف نشط لهذا الحساب"

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False

        profile = getattr(request.user, "employee_profile", None)
        return profile is not None and profile.is_active


class CanManageEmployees(BasePermission):
    """Managing employees, roles and assignment — for admins with an explicit permission."""

    message = "إدارة الموظفين تحتاج صلاحية صريحة"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        return user.has_perm(MANAGE_TEAM)
