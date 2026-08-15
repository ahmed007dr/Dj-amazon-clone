"""
صلاحيات العمولات.

⚠️  **رؤية عمولات الفريق ليست صلاحية أدمن تلقائية.**

    مبلغ عمولة كل مندوب معلومة حسّاسة بين الزملاء أنفسهم: من يراها
    يعرف ترتيب أداء الفريق ورواتبه الفعلية. والاعتماد قرار مالي
    بحجم صرف نقدي.
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
