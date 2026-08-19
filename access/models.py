"""
Product access policies.

⚠️  This domain answers a single question:

        "Can this user view/buy this thing?"

    Putting it in `catalog` would have forced `cart`, `orders` and search to
    depend on the catalogue, and inflated the catalogue with security logic that
    is not its own. (ADR-04)

    A policy is **an independent entity**, not a field on the product: products
    share policies, and editing one policy applies to thousands of products at once.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models.base import BaseModel
from core.models.translatable import BilingualNameMixin


class AccessLevel(models.TextChoices):
    """
    Access level — the coarse classification.

    The precise conditions (verification · permissions · account types) live in
    separate `AccessPolicy` fields.
    """

    PUBLIC = "PUBLIC", _("عام")
    REGISTERED = "REGISTERED", _("يتطلب تسجيل دخول")
    RESTRICTED = "RESTRICTED", _("مقيّد بأنواع حسابات")
    PROFESSIONAL = "PROFESSIONAL", _("مهنيون موثّقون فقط")


class AccessPolicy(BilingualNameMixin, BaseModel):
    """
    A reusable access policy.

    Example: "medicines for pharmacists" applied to every restricted medicine —
    changing one condition in it applies to all of them.
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

    # ── Conditions ─────────────────────────────────────────
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

    # ── Message shown on denial ────────────────────────────
    # Shown to the user instead of "not found" when revealing existence is acceptable
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
