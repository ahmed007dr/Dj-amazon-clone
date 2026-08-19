"""
Loyalty permissions.

⚠️  **Configuring the programme is an explicit permission, not a consequence of panel access.**

    Whoever edits `point_value` changes the whole store's liability in one
    stroke: multiplying the value by ten makes every outstanding point worth ten
    times as much, and the liability becomes a figure nobody approved.

⚠️  And the manual adjustment is more dangerous still: points created or erased
    with no order against them.
"""

from rest_framework.permissions import BasePermission


class CanManageLoyalty(BasePermission):
    message = "ضبط الولاء يحتاج صلاحية صريحة"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        return user.has_perm("loyalty.change_loyaltyprogram")


class CanAdjustPoints(BasePermission):
    message = "تسوية النقاط تحتاج صلاحية صريحة"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        return user.has_perm("loyalty.add_pointsentry")
