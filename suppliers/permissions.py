"""
Supplier permissions.

⚠️  **Purchasing is an explicit permission, not a consequence of panel access.**

    Whoever creates a purchase order commits the store's money to a third party.
    Making it available to every admin means a catalogue manager ordering a
    hundred thousand pounds of goods — with nothing stopping them but the fact
    that it did not occur to them.
"""

from rest_framework.permissions import BasePermission


class CanManagePurchasing(BasePermission):
    message = "إدارة المشتريات تحتاج صلاحية صريحة"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        return user.has_perm("suppliers.add_purchaseorder")
