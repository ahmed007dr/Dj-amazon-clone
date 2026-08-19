"""
Employees and sales representatives.

⚠️  **An employee is not an admin — and that is the basis of this whole domain.**

    A sales rep sees their own customers, creates orders for them, and reads
    their own performance. They do not see the full customer list, do not edit
    prices, and do not suspend accounts. Granting them admin permissions
    "temporarily" is the thing most often forgotten.

⚠️  And **`CustomerAssignment` lives here, not in `customers`** (ADR-12).

    An `assigned_employee` field on the customer created a
    `customers ↔ employees` cycle. Assignment is owned by the upper side, so the
    direction stays downward: `employees → customers`.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models.base import BaseModel


class EmployeeRoleKind(models.TextChoices):
    """
    ⚠️  Roles are **data, not code**.

        This is the list of expected types, but permissions are assigned to each
        role from the panel. Fixing them in code makes "senior rep" need a deployment.
    """

    SALES_REP = "SALES_REP", _("مندوب مبيعات")
    SENIOR_SALES = "SENIOR_SALES", _("مندوب أول")
    SALES_MANAGER = "SALES_MANAGER", _("مدير مبيعات")
    CUSTOMER_SERVICE = "CUSTOMER_SERVICE", _("خدمة عملاء")
    WAREHOUSE = "WAREHOUSE", _("موظف مخزن")
    FINANCE = "FINANCE", _("موظف مالي")
    OPERATIONS = "OPERATIONS", _("عمليات")


class EmployeeRole(BaseModel):
    """
    A job role — a bundle of permissions.

    ⚠️  Permissions sit on the **role**, not on the person.

        Granting them to an individual makes every new employee need manual
        configuration, and the first oversight leaves a rep with too few
        permissions or too many. And review becomes impossible: "who can apply a
        discount?" requires scanning every account.
    """

    code = models.SlugField(_("الرمز"), max_length=64, unique=True)
    kind = models.CharField(
        _("النوع"), max_length=24, choices=EmployeeRoleKind.choices, db_index=True
    )

    name_ar = models.CharField(_("الاسم بالعربية"), max_length=120)
    name_en = models.CharField(_("الاسم بالإنجليزية"), max_length=120)

    #: ⚠️  Standard Django permissions — not a parallel system.
    #:
    #:     `user.has_perm()` works on them everywhere: the endpoints,
    #:     the templates and the Django panel. Inventing custom strings means
    #:     writing a custom checker for every endpoint — and the first one forgotten is the hole.
    permissions = models.ManyToManyField(
        "auth.Permission",
        blank=True,
        related_name="employee_roles",
        verbose_name=_("الصلاحيات"),
    )

    #: ⚠️  **The Django group is what actually confers the permissions.**
    #:
    #:     Storing them in `permissions` alone is **decoration**: `has_perm`
    #:     reads the user's own permissions and their groups, and knows nothing
    #:     about this table. So the role looked configured while every permission
    #:     check failed — or worse: a custom checker gets built that bypasses Django entirely.
    #:
    #:     The group is created and synchronised in `services.sync_role_permissions`,
    #:     and the employee joins it in `services.set_role`.
    group = models.OneToOneField(
        "auth.Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="employee_role",
        verbose_name=_("مجموعة الصلاحيات"),
    )

    is_active = models.BooleanField(_("مفعّل"), default=True)

    class Meta:
        verbose_name = _("دور وظيفي")
        verbose_name_plural = _("الأدوار الوظيفية")
        ordering = ["name_ar"]

    def __str__(self):
        return self.name_ar


class EmployeeProfile(BaseModel):
    """
    The employee profile.

    ⚠️  A departed employee is **never deleted**.

        Deleting them loses the attribution of every order they created and who
        was responsible for their customers — data needed in any performance
        review or later commission dispute.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="employee_profile",
        verbose_name=_("المستخدم"),
    )

    employee_number = models.CharField(_("الرقم الوظيفي"), max_length=32, unique=True)

    role = models.ForeignKey(
        EmployeeRole,
        on_delete=models.PROTECT,
        related_name="employees",
        verbose_name=_("الدور"),
    )

    #: ⚠️  The line manager is optional: the sales manager themselves has no
    #:     manager above them in the system, and `PROTECT` prevents deleting a manager with a team.
    manager = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="team",
        verbose_name=_("المدير المباشر"),
    )

    phone_extension = models.CharField(_("التحويلة"), max_length=16, blank=True)
    hired_on = models.DateField(_("تاريخ التعيين"), null=True, blank=True)

    is_active = models.BooleanField(_("على رأس العمل"), default=True, db_index=True)

    class Meta:
        verbose_name = _("ملف موظف")
        verbose_name_plural = _("ملفات الموظفين")
        ordering = ["employee_number"]

    def __str__(self):
        return f"{self.employee_number} · {self.user.full_name}"

    def has_permission(self, codename: str) -> bool:
        """
        ⚠️  A departed employee **loses every permission immediately**.

            Disabling the account alone leaves a gap: a valid token in their
            hand until it expires. The check here closes it on the first request.
        """
        if not self.is_active:
            return False
        return self.user.has_perm(codename)


class AssignmentStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("قائم")
    ENDED = "ENDED", _("منتهٍ")


class CustomerAssignment(BaseModel):
    """
    Assigning a customer to an employee — **it lives here, not in `customers`** (ADR-12).

    ⚠️  **A historical record, not a current field.**

        An `assigned_employee` field on the customer is overwritten on every
        transfer, losing who was responsible when the order was placed. And the
        commission in phase 11 is calculated on **whoever was responsible then**,
        not on whoever is responsible today — without this record the
        calculation becomes retrospectively impossible.
    """

    customer = models.ForeignKey(
        "customers.CustomerProfile",
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name=_("العميل"),
    )
    employee = models.ForeignKey(
        EmployeeProfile,
        on_delete=models.PROTECT,
        related_name="assignments",
        verbose_name=_("الموظف"),
    )

    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.ACTIVE,
        db_index=True,
    )

    started_at = models.DateTimeField(_("بداية الإسناد"), default=timezone.now)
    ended_at = models.DateTimeField(_("نهاية الإسناد"), null=True, blank=True)

    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="made_assignments",
        verbose_name=_("أسنده"),
    )
    note = models.TextField(_("ملاحظة"), blank=True)

    class Meta:
        verbose_name = _("إسناد عميل")
        verbose_name_plural = _("إسنادات العملاء")
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["employee", "status"]),
        ]
        constraints = [
            # ⚠️  One customer to one employee at any one time.
            #
            #     Two reps sharing a customer means a double commission on the
            #     same sale, and conflicting follow-up — either both call them
            #     or neither does.
            models.UniqueConstraint(
                fields=["customer"],
                condition=models.Q(status="ACTIVE", deleted_at__isnull=True),
                name="one_active_assignment_per_customer",
            ),
        ]

    def __str__(self):
        return f"{self.customer_id} → {self.employee.employee_number}"

    @property
    def is_active(self) -> bool:
        return self.status == AssignmentStatus.ACTIVE
