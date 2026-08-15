"""
صلاحيات الموردين.

⚠️  **الشراء صلاحية صريحة لا تتبع دخول اللوحة.**

    من يُنشئ أمر شراء يلتزم بمال المتجر لدى طرف ثالث. جعلها
    متاحة لكل أدمن يعني أن مدير كتالوج يطلب بضاعة بمئة ألف —
    ولا شيء يمنعه إلا أنه لم يفكّر في ذلك.
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
