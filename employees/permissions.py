"""
صلاحيات بوابة الموظفين.

⚠️  **الموظف لا يُمنَح صلاحيات الأدمن — ولو «مؤقتًا».**

    مندوب المبيعات يرى عملاءه هو ويُنشئ لهم طلبات. ولا يرى قائمة
    العملاء كاملة، ولا يعدّل الأسعار، ولا يوقف حسابات. و«مؤقتًا»
    هي الكلمة التي تسبق أطول الثغرات عمرًا.

⚠️  والصلاحيات **دقيقة لا حزمة واحدة**.

    «موظف» ليست صلاحية: مندوب المبيعات يُنشئ طلبات ولا يرى
    الأرباح؛ وموظف المخزن يرى المخزون ولا يُنشئ طلبًا. حزمة واحدة
    تعني أن كل موظف يملك ما يملكه أوسعهم صلاحية.
"""

from rest_framework.permissions import BasePermission

from accounts.models import AccountType

#: الصلاحيات الدقيقة — تُسنَد للأدوار من اللوحة لا للأشخاص
VIEW_DASHBOARD = "employees.view_employeeprofile"
VIEW_CUSTOMERS = "employees.view_customerassignment"
CREATE_ORDER = "orders.add_order"
MANAGE_TEAM = "employees.change_customerassignment"


class IsEmployee(BasePermission):
    """
    ⚠️  الأدمن يمرّ أيضًا — لكن لسبب محدَّد.

        مدير المبيعات أدمن بحساب، ويحتاج فتح بوابة الموظفين
        ليرى ما يراه فريقه قبل أن يقرّر. المنع الكامل كان يجبره
        على إنشاء حساب موظف وهمي لنفسه.
    """

    message = "بوابة الموظفين للموظفين والمديرين"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return user.account_type in (AccountType.EMPLOYEE, AccountType.ADMIN)


class HasEmployeeProfile(IsEmployee):
    """
    ⚠️  الملف **وهو على رأس العمل** — الشرطان معًا.

        موظف انتهت خدمته وحسابه ما زال نشطًا بتوكن صالح في يده
        هو أوضح ثغرة في أي نظام مبيعات. `is_active` على الملف
        يُغلقها في أول طلب لا عند انتهاء التوكن.
    """

    message = "لا ملف موظف نشط لهذا الحساب"

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False

        profile = getattr(request.user, "employee_profile", None)
        return profile is not None and profile.is_active


class CanManageEmployees(BasePermission):
    """إدارة الموظفين والأدوار والإسناد — للأدمن بصلاحية صريحة."""

    message = "إدارة الموظفين تحتاج صلاحية صريحة"

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if user.is_superuser:
            return True
        return user.has_perm(MANAGE_TEAM)
