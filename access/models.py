"""
سياسات الوصول للمنتجات.

⚠️  هذا النطاق يجيب على سؤال واحد:

        «هل يستطيع هذا المستخدم رؤية/شراء هذا الشيء؟»

    وضعه في `catalog` كان سيجبر `cart` و`orders` والبحث على
    الاعتماد على الكتالوج، وينفخ الكتالوج بمنطق أمني ليس ملكه. (ADR-04)

    السياسة **كيان مستقل** لا حقل على المنتج: المنتجات تتشارك
    السياسات، وتعديل سياسة واحدة يسري على آلاف المنتجات فورًا.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models.base import BaseModel
from core.models.translatable import BilingualNameMixin


class AccessLevel(models.TextChoices):
    """
    مستوى الوصول — التصنيف الخشن.

    الشروط الدقيقة (التوثيق · الصلاحيات · أنواع الحسابات) في
    حقول `AccessPolicy` المنفصلة.
    """

    PUBLIC = "PUBLIC", _("عام")
    REGISTERED = "REGISTERED", _("يتطلب تسجيل دخول")
    RESTRICTED = "RESTRICTED", _("مقيّد بأنواع حسابات")
    PROFESSIONAL = "PROFESSIONAL", _("مهنيون موثّقون فقط")


class AccessPolicy(BilingualNameMixin, BaseModel):
    """
    سياسة وصول قابلة لإعادة الاستخدام.

    مثال: «أدوية للصيادلة» تُطبَّق على كل الأدوية المقيّدة —
    تغيير شرط واحد فيها يسري عليها كلها.
    """

    code = models.SlugField(_("الرمز"), max_length=50, unique=True)
    description_ar = models.TextField(_("الوصف بالعربية"), blank=True)
    description_en = models.TextField(_("الوصف بالإنجليزية"), blank=True)

    level = models.CharField(
        _("المستوى"),
        max_length=16,
        choices=AccessLevel.choices,
        default=AccessLevel.PUBLIC,
        db_index=True,
    )

    # ── الشروط ─────────────────────────────────────────────
    allowed_account_types = models.JSONField(
        _("أنواع الحسابات المسموحة"),
        default=list,
        blank=True,
        help_text=_("قائمة فارغة = كل الأنواع (بحسب المستوى)"),
    )
    requires_verification = models.BooleanField(
        _("يتطلب توثيق الحساب"),
        default=False,
        help_text=_("طبيب مسجّل ≠ طبيب موثّق"),
    )
    required_permission = models.CharField(
        _("صلاحية مطلوبة"),
        max_length=100,
        blank=True,
        help_text=_("بصيغة app_label.codename"),
    )

    # ── الرسالة المعروضة عند المنع ─────────────────────────
    # تُعرض للمستخدم بدل «غير موجود» حين يكون كشف الوجود مقبولًا
    denial_message_ar = models.CharField(_("رسالة المنع بالعربية"), max_length=300, blank=True)
    denial_message_en = models.CharField(_("رسالة المنع بالإنجليزية"), max_length=300, blank=True)

    is_default = models.BooleanField(
        _("السياسة الافتراضية"),
        default=False,
        help_text=_("تُطبَّق على أي مورد بلا سياسة صريحة"),
    )
    is_active = models.BooleanField(_("مفعّلة"), default=True, db_index=True)

    class Meta:
        verbose_name = _("سياسة وصول")
        verbose_name_plural = _("سياسات الوصول")
        ordering = ["level", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=models.Q(is_default=True, deleted_at__isnull=True),
                name="unique_default_access_policy",
            ),
        ]

    def __str__(self):
        return f"{self.name_ar} [{self.level}]"

    @classmethod
    def get_default(cls) -> "AccessPolicy | None":
        return cls.objects.filter(is_default=True, is_active=True).first()
