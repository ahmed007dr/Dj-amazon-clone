"""
مديرو النظام والأدوار الإدارية.

⚠️  **«أدمن» ليست صلاحية واحدة.**
    رؤية الأرباح صلاحية منفصلة عن إدارة المنتجات، وتعديل بوابات
    الدفع منفصل عن إدارة الطلبات.

هذا النطاق لا يعتمد على `customers` ولا `employees` — إدارة النظام
مستقلة عن بيانات البيع. (ADR-11)
"""

from django.contrib.auth.models import Permission
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.identifiers import business_number
from core.models.base import BaseModel
from core.models.translatable import BilingualNameMixin


def admin_number() -> str:
    return business_number("ADM", random_length=6)


class AdminProfile(BaseModel):
    user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="admin_profile",
        verbose_name=_("المستخدم"),
    )
    admin_number = models.CharField(
        _("الرقم الإداري"),
        max_length=24,
        unique=True,
        default=admin_number,
        editable=False,
    )
    department = models.CharField(_("القسم"), max_length=100, blank=True)
    job_title = models.CharField(_("المسمى الوظيفي"), max_length=100, blank=True)

    is_owner = models.BooleanField(
        _("المالك"),
        default=False,
        help_text=_("الحساب الجذر — لا يُوقَف ولا تُسحب صلاحياته"),
    )

    class Meta:
        verbose_name = _("مدير نظام")
        verbose_name_plural = _("مديرو النظام")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_owner"],
                condition=models.Q(is_owner=True, deleted_at__isnull=True),
                name="unique_system_owner",
            ),
        ]

    def __str__(self):
        return f"{self.admin_number} · {self.user.email}"


class AdminRole(BilingualNameMixin, BaseModel):
    """
    دور إداري = حزمة صلاحيات.

    الأدوار المتوقعة: مدير عام · مدير مالي · مدير مخزون ·
    مدير كتالوج · خدمة عملاء · مدقّق (قراءة فقط).
    """

    code = models.SlugField(_("الرمز"), max_length=50, unique=True)
    description_ar = models.TextField(_("الوصف بالعربية"), blank=True)
    description_en = models.TextField(_("الوصف بالإنجليزية"), blank=True)

    permissions = models.ManyToManyField(
        Permission,
        blank=True,
        related_name="admin_roles",
        verbose_name=_("الصلاحيات"),
    )

    is_system = models.BooleanField(
        _("دور نظام"),
        default=False,
        help_text=_("لا يُحذف ولا يُعاد تسميته"),
    )
    is_active = models.BooleanField(_("مفعّل"), default=True, db_index=True)

    class Meta:
        verbose_name = _("دور إداري")
        verbose_name_plural = _("الأدوار الإدارية")
        ordering = ["code"]

    def __str__(self):
        return self.name_ar


class AdminRoleAssignment(BaseModel):
    """
    إسناد دور لمدير — بسجل زمني.

    الإسناد المنتهي يبقى محفوظًا: التدقيق يحتاج معرفة مَن كان
    يملك أي صلاحية وقت وقوع حدث ما.
    """

    admin = models.ForeignKey(
        AdminProfile,
        on_delete=models.CASCADE,
        related_name="role_assignments",
        verbose_name=_("المدير"),
    )
    role = models.ForeignKey(
        AdminRole,
        on_delete=models.PROTECT,
        related_name="assignments",
        verbose_name=_("الدور"),
    )
    assigned_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("أسنده"),
    )
    from_date = models.DateField(_("من تاريخ"), auto_now_add=True)
    to_date = models.DateField(_("حتى تاريخ"), null=True, blank=True)

    class Meta:
        verbose_name = _("إسناد دور")
        verbose_name_plural = _("إسنادات الأدوار")
        ordering = ["-from_date"]
        indexes = [models.Index(fields=["admin", "role"])]

    def __str__(self):
        return f"{self.admin.admin_number} · {self.role.code}"

    @property
    def is_current(self) -> bool:
        from django.utils import timezone

        # ⚠️  `localdate()` لا `now().date()`: الثانية تاريخ UTC،
        #     فتنتهي صلاحية التكليف قبل موعدها بيوم في ساعات
        #     الليل الأولى بتوقيت القاهرة.
        return self.to_date is None or self.to_date >= timezone.localdate()
