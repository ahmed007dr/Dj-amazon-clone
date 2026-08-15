"""
الموظفون ومندوبو المبيعات.

⚠️  **الموظف ليس أدمن — وهذا أساس النطاق كله.**

    مندوب المبيعات يرى عملاءه هو، ويُنشئ لهم طلبات، ويقرأ أداءه.
    ولا يرى قائمة العملاء كاملة، ولا يعدّل الأسعار، ولا يوقف
    حسابات. منحه صلاحيات الأدمن «مؤقتًا» هو أكثر ما يُنسى.

⚠️  و**`CustomerAssignment` يسكن هنا لا في `customers`** (ADR-12).

    حقل `assigned_employee` على العميل كان ينشئ دائرة
    `customers ↔ employees`. الإسناد يملكه الطرف الأعلى، فيبقى
    الاتجاه نازلًا: `employees → customers`.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models.base import BaseModel


class EmployeeRoleKind(models.TextChoices):
    """
    ⚠️  الأدوار **بيانات لا كود**.

        هذه قائمة الأنواع المتوقَّعة، لكن الصلاحيات تُسنَد لكل دور
        من اللوحة. تثبيتها في الكود يجعل «مندوب أول» يحتاج نشرًا.
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
    دور وظيفي — حزمة صلاحيات.

    ⚠️  الصلاحيات على **الدور** لا على الشخص.

        منحها فردًا يجعل كل موظف جديد يحتاج ضبطًا يدويًا، وأول
        سهو يترك مندوبًا بلا صلاحية أو بصلاحية زائدة. والمراجعة
        تصير مستحيلة: «من يستطيع الخصم؟» تحتاج مسح كل الحسابات.
    """

    code = models.SlugField(_("الرمز"), max_length=64, unique=True)
    kind = models.CharField(
        _("النوع"), max_length=24, choices=EmployeeRoleKind.choices, db_index=True
    )

    name_ar = models.CharField(_("الاسم بالعربية"), max_length=120)
    name_en = models.CharField(_("الاسم بالإنجليزية"), max_length=120)

    #: ⚠️  صلاحيات Django القياسية — لا نظام موازٍ.
    #:
    #:     `user.has_perm()` يعمل عليها في كل مكان: الواجهات
    #:     والقوالب ولوحة Django. اختراع سلاسل خاصة يعني كتابة
    #:     فاحص خاص لكل نقطة — وأول نقطة تُنسى هي الثغرة.
    permissions = models.ManyToManyField(
        "auth.Permission",
        blank=True,
        related_name="employee_roles",
        verbose_name=_("الصلاحيات"),
    )

    #: ⚠️  **مجموعة Django تسند الصلاحيات فعلًا.**
    #:
    #:     تخزينها في `permissions` وحدها **زينة**: `has_perm`
    #:     يقرأ صلاحيات المستخدم ومجموعاته، ولا يعرف بوجود هذا
    #:     الجدول. فكان الدور يبدو مضبوطًا وكل فحص صلاحية يفشل —
    #:     أو أسوأ: يُبنى فاحص خاص يتجاوز نظام Django كله.
    #:
    #:     المجموعة تُنشأ وتُزامَن في `services.sync_role_permissions`،
    #:     وانضمام الموظف إليها في `services.set_role`.
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
    ملف الموظف.

    ⚠️  الموظف الموقوف **لا يُحذف**.

        حذفه يفقد نسبة كل طلب أنشأه ومَن كان مسؤولًا عن عملائه —
        وهي بيانات تُحتاج في أي مراجعة أداء أو نزاع عمولة لاحق.
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

    #: ⚠️  المدير المباشر اختياري: مدير المبيعات نفسه بلا مدير
    #:     أعلى داخل النظام، و`PROTECT` يمنع حذف مدير له فريق.
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
        ⚠️  الموقوف عن العمل **يفقد كل صلاحياته فورًا**.

            الاكتفاء بتعطيل الحساب يترك فجوة: توكن صالح في يده
            حتى انتهائه. والفحص هنا يُغلقها في أول طلب.
        """
        if not self.is_active:
            return False
        return self.user.has_perm(codename)


class AssignmentStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("قائم")
    ENDED = "ENDED", _("منتهٍ")


class CustomerAssignment(BaseModel):
    """
    إسناد عميل إلى موظف — **يسكن هنا لا في `customers`** (ADR-12).

    ⚠️  **سجل تاريخي لا حقل حالي.**

        حقل `assigned_employee` على العميل يُكتب فوقه عند كل نقل،
        فيضيع من كان مسؤولًا حين وقع الطلب. والعمولة في المرحلة
        ١١ تُحسب على **من كان مسؤولًا وقتها** لا على من هو
        مسؤول اليوم — بلا هذا السجل يصير الحساب مستحيلًا رجعيًا.
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
            # ⚠️  عميل واحد لموظف واحد في اللحظة الواحدة.
            #
            #     مندوبان يتقاسمان عميلًا يعني عمولةً مزدوجة على
            #     نفس البيعة، وتضاربًا في المتابعة — يتصل به
            #     الاثنان أو لا يتصل أحد.
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
