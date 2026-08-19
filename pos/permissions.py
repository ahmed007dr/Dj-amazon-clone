"""
Point-of-sale permissions.

⚠️  **A cashier is an employee, not an admin.**

    Using `IsAdminAccount` here would have granted every cashier the full admin
    panel permissions — editing prices and products and suspending accounts. And
    it is a mistake that passes silently because the screen works.

⚠️  And the fine-grained permissions (`pos.refund` · `pos.discount`) await the
    settlement of business rule 11 (cashier permissions). The current default is
    **the stricter one**: refunds for the admin alone, and a discount cap of
    zero. Widening it is a decision taken explicitly, not inherited from a
    permissive default.
"""

from rest_framework.permissions import BasePermission

from accounts.models import AccountType


class CanOperatePOS(BasePermission):
    """
    Who operates the point of sale: the employee or the admin.

    ⚠️  A customer never reaches here under any circumstances — point of sale is
        an internal tool.
    """

    message = "نقطة البيع للموظفين والمديرين فقط"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return user.account_type in (AccountType.EMPLOYEE, AccountType.ADMIN)


class CanRefund(BasePermission):
    """
    ⚠️  Refunds are for the admin alone until business rule 11 is settled.

        The written recommendation: "no discount and no return without a
        manager's approval". And relaxing it later is easier than tightening it
        after the cashier has grown used to it.
    """

    message = "الاسترداد يحتاج اعتماد مدير"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return hasattr(user, "admin_profile")
