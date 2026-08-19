"""
Commission permissions.

⚠️  **Seeing the team's commissions is not an automatic admin permission.**

    Each rep's commission amount is sensitive information among colleagues
    themselves: whoever sees it knows the team's performance ranking and their
    actual pay. And approval is a financial decision the size of a cash disbursement.
"""

from rest_framework.permissions import BasePermission


class CanManageCommissions(BasePermission):
    message = "إدارة العمولات تحتاج صلاحية صريحة"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        return user.has_perm("commissions.change_commissionrecord")
