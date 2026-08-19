"""
Seed the job roles and their permissions.

    python manage.py seed_employee_roles

⚠️  **No role carries every permission.**

    "Employee" is not a permission: a rep creates orders and does not see
    profits; a warehouse employee sees the stock and creates no orders. Granting
    everyone the same bundle means every employee holds what the broadest of
    them holds — and it passes silently because the screens work.

⚠️  And `is_active` is not touched on update: re-running would have reactivated
    a role management deliberately disabled.
"""

from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from employees import services
from employees.models import EmployeeRole, EmployeeRoleKind

#: (permission code, app) — standard Django permissions, not a parallel system
ROLES = [
    {
        "code": "sales-rep",
        "kind": EmployeeRoleKind.SALES_REP,
        "name_ar": "مندوب مبيعات",
        "name_en": "Sales representative",
        # ⚠️  Reads the catalogue and creates orders for their customers — and sees no
        #     profit, no expense, and no other rep's customer account.
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
        # Adds stock reading: they promise the customer an availability date, not a guess
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
        # ⚠️  Assigns customers and sees their team's performance — and still **without**
        #     any finance permission: profits are decided in `finance` (ADR-47).
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
        # ⚠️  Reads orders and does not create them: creating is selling, and service is follow-up.
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
        # ⚠️  The only one with a finance permission — and it is explicit, not inherited (ADR-47)
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
                    # ⚠️  A missing permission is reported, never swallowed.
                    #
                    #     A typo in its name would have produced a role missing something
                    #     nobody notices until an employee complains about a screen
                    #     will not open.
                    missing.append(path)
                    continue
                permissions.append(permission)

            role.permissions.set(permissions)

            # ⚠️  Synchronise to the Django group — without it the permissions are decoration.
            #
            #     `has_perm` knows nothing about `EmployeeRole.permissions`;
            #     it reads the user's own permissions and their groups alone.
            services.sync_role_permissions(role)

        self.stdout.write(
            self.style.SUCCESS(f"الأدوار: {created} جديد · {len(ROLES) - created} محدَّث")
        )

        if missing:
            self.stdout.write(
                self.style.WARNING("\n⚠️  صلاحيات غير موجودة:\n  " + "\n  ".join(missing))
            )
