"""
صلاحيات نقطة البيع.

⚠️  **الكاشير موظف لا أدمن.**

    استخدام `IsAdminAccount` هنا كان سيمنح كل كاشير صلاحيات لوحة
    الأدمن كاملةً — تعديل الأسعار والمنتجات وإيقاف الحسابات. وهو
    خطأ يمرّ صامتًا لأن الشاشة تعمل.

⚠️  والصلاحيات الدقيقة (`pos.refund` · `pos.discount`) تنتظر حسم
    قاعدة العمل ١١ (صلاحيات الكاشير). الافتراضي الحالي **الأشدّ**:
    الاسترداد للأدمن وحده، والخصم بسقف صفر. توسيعه قرار يُتخذ
    صراحةً لا يُورَث من افتراضي متساهل.
"""

from rest_framework.permissions import BasePermission

from accounts.models import AccountType


class CanOperatePOS(BasePermission):
    """
    من يشغّل نقطة البيع: الموظف أو الأدمن.

    ⚠️  العميل لا يصل هنا مهما كان — نقطة البيع أداة داخلية.
    """

    message = "نقطة البيع للموظفين والمديرين فقط"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return user.account_type in (AccountType.EMPLOYEE, AccountType.ADMIN)


class CanRefund(BasePermission):
    """
    ⚠️  الاسترداد للأدمن وحده حتى تُحسم قاعدة العمل ١١.

        التوصية المكتوبة: «لا خصم ولا ارتجاع بلا اعتماد مدير».
        وتخفيفها لاحقًا أسهل من تشديدها بعد أن يعتاده الكاشير.
    """

    message = "الاسترداد يحتاج اعتماد مدير"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return hasattr(user, "admin_profile")
