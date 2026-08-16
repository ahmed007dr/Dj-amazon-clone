"""
صلاحيات الولاء.

⚠️  **ضبط البرنامج صلاحية صريحة لا تتبع دخول اللوحة.**

    من يعدّل `point_value` يغيّر التزام المتجر كله بضربة واحدة:
    ضرب القيمة في عشرة يجعل كل نقطة قائمة تساوي عشرة أضعاف،
    والالتزام يصير رقمًا لم يوافق عليه أحد.

⚠️  والتسوية اليدوية أخطر: نقاط تُخلَق أو تُمحى بلا طلب يقابلها.
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
