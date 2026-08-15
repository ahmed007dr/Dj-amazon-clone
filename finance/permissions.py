"""
صلاحيات المالية.

⚠️  **رؤية الأرباح ليست صلاحية أدمن تلقائية.**

    لوحة الأدمن يفتحها مدير كتالوج وموظف خدمة عملاء ومسؤول مخزن.
    ولا واحد منهم يحتاج أن يعرف هامش الربح ولا رواتب الزملاء ولا
    إيجار المحل. جعلها تابعة لـ`IsAdminAccount` كان يفتحها للجميع
    بلا أن يقرّر أحد ذلك.

⚠️  وقاعدة العمل ١٤ حسمت **الجهة**: الإيرادات والمصروفات تُرى من
    بوابة الأدمن. وهي لم تحسم **مَن** داخلها — فالافتراضي هنا
    الأشدّ: صلاحية Django صريحة تُمنَح بقرار.
"""

from rest_framework.permissions import BasePermission

#: ⚠️  صلاحية واحدة تحكم القراءة كلها.
#:
#:     تفتيتها إلى «يرى الإيراد» و«يرى المصروفات» و«يرى الربح»
#:     وهمٌ: من يرى الاثنين الأولين يطرح. الفصل الحقيقي الوحيد
#:     هو بين من يقرأ التقرير ومن يُدخل مصروفًا.
VIEW_FINANCE = "finance.view_revenueentry"
MANAGE_EXPENSES = "finance.add_expense"
APPROVE_EXPENSES = "finance.change_expense"


class _PermissionRequired(BasePermission):
    """
    ⚠️  المالك (`is_superuser`) يمرّ دائمًا.

        بدونه لا يستطيع أول مستخدم في نظام جديد فتح شاشة مالية
        ليمنح الصلاحيات — وهي حلقة مفرغة تُحَلّ بـ`manage.py`.
    """

    permission = ""

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        return user.has_perm(self.permission)


class CanViewFinance(_PermissionRequired):
    message = "التقارير المالية تحتاج صلاحية صريحة"
    permission = VIEW_FINANCE


class CanManageExpenses(_PermissionRequired):
    message = "إدخال المصروفات يحتاج صلاحية صريحة"
    permission = MANAGE_EXPENSES


class CanApproveExpenses(_PermissionRequired):
    """
    ⚠️  الاعتماد **صلاحية منفصلة عن الإدخال**.

        من يُدخل مصروفًا ويعتمده بنفسه يجعل الاعتماد توقيعًا على
        بياض. الفصل هو كل قيمة الخطوة.
    """

    message = "اعتماد المصروفات يحتاج صلاحية صريحة"
    permission = APPROVE_EXPENSES
