"""
B2B permissions.

⚠️  **A business customer sees their own account — not anyone else's.**

    A pharmacy's statement reveals its purchase volume and the margin we deal at.
    Leaking it to a competing pharmacy on the same street is direct commercial
    damage, not merely a privacy breach.
"""

from rest_framework.permissions import BasePermission

from accounts.models import AccountType

#: The account types that buy wholesale — matching the `wholesale` price list
TRADE_ACCOUNTS = {
    AccountType.PHARMACY,
    AccountType.WAREHOUSE,
    AccountType.TRADER,
    AccountType.SUPPLIER,
}


class IsTradeAccount(BasePermission):
    """
    ⚠️  Admins **do not pass through here**.

        These endpoints answer "my own account", and are meaningless to an admin
        with no business profile. Admin screens have their own endpoints, which
        take the customer id explicitly.
    """

    message = "هذه البوابة للحسابات التجارية"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return user.account_type in TRADE_ACCOUNTS


class CanManageCredit(BasePermission):
    """
    Granting credit, suspending it, and recording payment.

    ⚠️  An explicit permission, not `IsAdminAccount`.

        Raising a credit limit is a financial decision the size of a loan.
        Making it available to everyone who opens the panel means a catalogue
        manager grants a pharmacy a hundred thousand — with nothing stopping
        them but the fact that it did not occur to them.
    """

    message = "إدارة الائتمان تحتاج صلاحية صريحة"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        return user.has_perm("b2b.change_businessprofile")
