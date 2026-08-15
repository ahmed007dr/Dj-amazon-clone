"""
بذر الأدوار الوظيفية وصلاحياتها.

    python manage.py seed_employee_roles

⚠️  **لا دور يحمل كل الصلاحيات.**

    «موظف» ليست صلاحية: المندوب يُنشئ طلبات ولا يرى الأرباح؛
    وموظف المخزن يرى المخزون ولا يُنشئ طلبًا. منح الجميع نفس
    الحزمة يعني أن كل موظف يملك ما يملكه أوسعهم صلاحية — وهو ما
    يمرّ صامتًا لأن الشاشات تعمل.

⚠️  ولا يُلمَس `is_active` عند التحديث: إعادة التشغيل كانت ستُعيد
    تفعيل دور عطّلته الإدارة عمدًا.
"""

from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from employees import services
from employees.models import EmployeeRole, EmployeeRoleKind

#: (رمز الصلاحية، التطبيق) — صلاحيات Django القياسية لا نظام موازٍ
ROLES = [
    {
        "code": "sales-rep",
        "kind": EmployeeRoleKind.SALES_REP,
        "name_ar": "مندوب مبيعات",
        "name_en": "Sales representative",
        # ⚠️  يقرأ الكتالوج ويُنشئ طلبات لعملائه — ولا يرى ربحًا
        #     ولا مصروفًا ولا حساب عميل غيره.
        "permissions": [
            "employees.view_employeeprofile",
            "employees.view_customerassignment",
            "catalog.view_product",
            "orders.view_order",
            "orders.add_order",
        ],
    },
    {
        "code": "senior-sales",
        "kind": EmployeeRoleKind.SENIOR_SALES,
        "name_ar": "مندوب أول",
        "name_en": "Senior sales representative",
        # يضيف قراءة المخزون: يَعِد العميل بموعد توفّر لا بتخمين
        "permissions": [
            "employees.view_employeeprofile",
            "employees.view_customerassignment",
            "catalog.view_product",
            "orders.view_order",
            "orders.add_order",
            "inventory.view_stock",
        ],
    },
    {
        "code": "sales-manager",
        "kind": EmployeeRoleKind.SALES_MANAGER,
        "name_ar": "مدير مبيعات",
        "name_en": "Sales manager",
        # ⚠️  يُسنِد العملاء ويرى أداء فريقه — ولا يزال **بلا**
        #     صلاحية مالية: الأرباح قرارها في `finance` (ADR-47).
        "permissions": [
            "employees.view_employeeprofile",
            "employees.change_employeeprofile",
            "employees.view_customerassignment",
            "employees.change_customerassignment",
            "employees.add_customerassignment",
            "catalog.view_product",
            "orders.view_order",
            "orders.add_order",
            "inventory.view_stock",
        ],
    },
    {
        "code": "customer-service",
        "kind": EmployeeRoleKind.CUSTOMER_SERVICE,
        "name_ar": "خدمة عملاء",
        "name_en": "Customer service",
        # ⚠️  يقرأ الطلبات ولا يُنشئها: الإنشاء بيع، والخدمة متابعة.
        "permissions": [
            "employees.view_employeeprofile",
            "employees.view_customerassignment",
            "orders.view_order",
            "catalog.view_product",
        ],
    },
    {
        "code": "warehouse-staff",
        "kind": EmployeeRoleKind.WAREHOUSE,
        "name_ar": "موظف مخزن",
        "name_en": "Warehouse staff",
        "permissions": [
            "employees.view_employeeprofile",
            "inventory.view_stock",
            "inventory.change_stock",
            "catalog.view_product",
            "orders.view_order",
        ],
    },
    {
        "code": "finance-staff",
        "kind": EmployeeRoleKind.FINANCE,
        "name_ar": "موظف مالي",
        "name_en": "Finance staff",
        # ⚠️  الوحيد بصلاحية مالية — وهي صريحة لا موروثة (ADR-47)
        "permissions": [
            "employees.view_employeeprofile",
            "finance.view_revenueentry",
            "finance.add_expense",
            "orders.view_order",
        ],
    },
]


class Command(BaseCommand):
    help = "بذر الأدوار الوظيفية — قابل للتشغيل مرارًا"

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        missing: list[str] = []

        for payload in ROLES:
            role, was_created = EmployeeRole.objects.update_or_create(
                code=payload["code"],
                defaults={
                    "kind": payload["kind"],
                    "name_ar": payload["name_ar"],
                    "name_en": payload["name_en"],
                },
            )
            created += int(was_created)

            permissions = []
            for path in payload["permissions"]:
                app_label, codename = path.split(".")
                permission = Permission.objects.filter(
                    content_type__app_label=app_label, codename=codename
                ).first()

                if permission is None:
                    # ⚠️  الصلاحية الغائبة تُبلَّغ ولا تُبتلع.
                    #
                    #     خطأ مطبعي في اسمها كان سيُنتج دورًا ينقصه
                    #     ما لا يلاحظه أحد حتى يشتكي موظف من شاشة
                    #     لا تفتح.
                    missing.append(path)
                    continue
                permissions.append(permission)

            role.permissions.set(permissions)

            # ⚠️  المزامنة إلى مجموعة Django — بدونها الصلاحيات زينة.
            #
            #     `has_perm` لا يعرف بوجود `EmployeeRole.permissions`؛
            #     يقرأ صلاحيات المستخدم ومجموعاته وحدهما.
            services.sync_role_permissions(role)

        self.stdout.write(
            self.style.SUCCESS(f"الأدوار: {created} جديد · {len(ROLES) - created} محدَّث")
        )

        if missing:
            self.stdout.write(
                self.style.WARNING("\n⚠️  صلاحيات غير موجودة:\n  " + "\n  ".join(missing))
            )
