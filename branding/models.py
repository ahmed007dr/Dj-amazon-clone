"""
الهوية البصرية — كل ما يراه العميل، قابلًا للضبط من لوحة الأدمن.

⚠️  الحدود مع `core.SystemSetting`:

        core/settings  →  إعدادات تشغيلية (حدود · قواعد عمل · أعلام)
        branding/      →  ما يُرى (ألوان · لوجو · خطوط · شعارات)

    الخلط يجعل «نسبة الضريبة» و«اللون الأساسي» في نفس الشاشة —
    وهما قراران لا يتخذهما الشخص نفسه ولا بنفس الحذر.

⚠️  هذا النطاق **لا يعرف بوجود أي نطاق عمل**. لا مستخدمين ولا
    منتجات ولا طلبات — يفرضه `import-linter`.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.identifiers import random_filename
from core.models.base import BaseModel, TimeStampedModel, UUIDPrimaryKeyModel

#: لون HEX — `#rgb` أو `#rrggbb`
HEX_COLOR = RegexValidator(
    regex=r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$",
    message=_("لون غير صالح — استخدم صيغة #rrggbb"),
)


def branding_asset_path(instance, filename: str) -> str:
    return f"branding/{random_filename(filename)}"


class ThemeMode(models.TextChoices):
    LIGHT = "LIGHT", _("فاتح")
    DARK = "DARK", _("داكن")


class DefaultMode(models.TextChoices):
    """
    ⚠️  `SYSTEM` ليس وضعًا ثالثًا — إنه **تفويض** لتفضيل الجهاز.

        دمجه مع الفاتح والداكن في حقل واحد يجعل «ما الوضع الحالي؟»
        سؤالًا بلا إجابة واحدة؛ فصله يبقي اللوحتين اثنتين ويجعل
        الاختيار بينهما هو المتغيّر.
    """

    LIGHT = "LIGHT", _("فاتح دائمًا")
    DARK = "DARK", _("داكن دائمًا")
    SYSTEM = "SYSTEM", _("حسب تفضيل الجهاز")


class BrandProfile(BaseModel):
    """
    ملف الهوية.

    ⚠️  **واحد مفعّل فقط** — والبقية مسوّدات.

        السماح بأكثر من ملف مفعّل يعني أن «ما ألوان النظام؟» تعتمد
        على ترتيب الاستعلام. والملفات غير المفعّلة ليست ترفًا: هي
        ما يسمح بتجهيز هوية موسمية كاملة ثم تفعيلها بضغطة.
    """

    # ── الاسم والهوية ──────────────────────────────────────
    code = models.SlugField(_("الرمز"), max_length=50, unique=True)
    name_ar = models.CharField(_("اسم الموقع بالعربية"), max_length=120)
    name_en = models.CharField(_("اسم الموقع بالإنجليزية"), max_length=120)
    tagline_ar = models.CharField(_("الشعار النصي عربي"), max_length=200, blank=True)
    tagline_en = models.CharField(_("الشعار النصي إنجليزي"), max_length=200, blank=True)

    # ── الأصول ─────────────────────────────────────────────
    # ⚠️  لوجو للفاتح وآخر للداكن — لوجو واحد بخلفية شفافة ونص
    #     داكن يختفي تمامًا على الوضع الداكن.
    logo_light = models.ImageField(
        _("اللوجو — الوضع الفاتح"), upload_to=branding_asset_path, blank=True
    )
    logo_dark = models.ImageField(
        _("اللوجو — الوضع الداكن"), upload_to=branding_asset_path, blank=True
    )
    icon = models.ImageField(
        _("الأيقونة المربّعة"),
        upload_to=branding_asset_path,
        blank=True,
        help_text=_("للتطبيق والمشاركة — مربّعة"),
    )
    favicon = models.ImageField(_("أيقونة المتصفح"), upload_to=branding_asset_path, blank=True)
    og_image = models.ImageField(
        _("صورة المشاركة"),
        upload_to=branding_asset_path,
        blank=True,
        help_text=_("تظهر عند مشاركة رابط الموقع — 1200×630"),
    )

    # ── الخطوط ─────────────────────────────────────────────
    # ⚠️  خط عربي وخط إنجليزي منفصلان: خط لاتيني جيد قد لا يحمل
    #     محارف عربية أصلًا، فيسقط النص إلى خط النظام بلا تحذير.
    font_ar = models.CharField(_("الخط العربي"), max_length=120, default="Cairo")
    font_en = models.CharField(_("الخط الإنجليزي"), max_length=120, default="Inter")
    font_size_base = models.DecimalField(
        _("حجم الخط الأساسي (rem)"),
        max_digits=4,
        decimal_places=3,
        default=Decimal("1.000"),
        # ⚠️  `Decimal` لا `float` — المدقّق العشري يقارن بنوعه،
        #     وتمرير عائم يجعل DRF يحذّر ويسقط الحد من المخطط.
        validators=[MinValueValidator(Decimal("0.75")), MaxValueValidator(Decimal("1.5"))],
    )

    # ── الشكل ──────────────────────────────────────────────
    radius = models.DecimalField(
        _("استدارة الحواف (rem)"),
        max_digits=4,
        decimal_places=3,
        default=Decimal("0.500"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("2"))],
    )
    shadow_level = models.PositiveSmallIntegerField(
        _("مستوى الظل"),
        default=1,
        validators=[MaxValueValidator(3)],
        help_text=_("0 = بلا ظل · 3 = ظل عميق"),
    )

    default_mode = models.CharField(
        _("الوضع الافتراضي"),
        max_length=8,
        choices=DefaultMode.choices,
        default=DefaultMode.SYSTEM,
    )

    # ── التواصل ────────────────────────────────────────────
    contact_email = models.EmailField(_("بريد التواصل"), blank=True)
    contact_phone = models.CharField(_("هاتف التواصل"), max_length=30, blank=True)
    whatsapp = models.CharField(_("واتساب"), max_length=30, blank=True)
    address_ar = models.CharField(_("العنوان بالعربية"), max_length=300, blank=True)
    address_en = models.CharField(_("العنوان بالإنجليزية"), max_length=300, blank=True)

    # ── السوشيال ───────────────────────────────────────────
    facebook = models.URLField(_("فيسبوك"), blank=True)
    instagram = models.URLField(_("إنستجرام"), blank=True)
    x_twitter = models.URLField(_("إكس"), blank=True)
    linkedin = models.URLField(_("لينكدإن"), blank=True)
    youtube = models.URLField(_("يوتيوب"), blank=True)
    tiktok = models.URLField(_("تيك توك"), blank=True)

    is_active = models.BooleanField(_("مفعّل"), default=False, db_index=True)

    class Meta:
        verbose_name = _("ملف هوية")
        verbose_name_plural = _("ملفات الهوية")
        ordering = ["-is_active", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=models.Q(is_active=True, deleted_at__isnull=True),
                name="unique_active_brand_profile",
            ),
        ]

    def __str__(self):
        return f"{self.code}{' ✓' if self.is_active else ''}"

    @classmethod
    def get_active(cls) -> "BrandProfile | None":
        return cls.objects.filter(is_active=True).prefetch_related("palettes").first()


class ThemePalette(UUIDPrimaryKeyModel, TimeStampedModel):
    """
    لوحة ألوان لوضع واحد.

    ⚠️  **لوحتان لا واحدة.** اشتقاق الداكن آليًا بعكس الإضاءة ينتج
        ألوانًا موحلة وتباينًا يسقط تحت الحد المقروء — والأدمن لا
        يملك تصحيحه لأنه ليس حقلًا.

    ⚠️  مفتاح UUIDv7 لا BigInt.

        بدا «جدولًا تابعًا لا يظهر في رابط»، ثم ظهر فعلًا في
        `/branding/admin/profiles/{id}/palettes/{id}/`. ومعرّف تسلسلي
        في رابط ممنوع بلا استثناء — أمسكه
        `test_exposed_models_use_uuid_pk`، وهو بالضبط سبب وجوده.
    """

    profile = models.ForeignKey(
        BrandProfile,
        on_delete=models.CASCADE,
        related_name="palettes",
        verbose_name=_("ملف الهوية"),
    )
    mode = models.CharField(_("الوضع"), max_length=8, choices=ThemeMode.choices)

    # ── ألوان العلامة ──────────────────────────────────────
    primary = models.CharField(
        _("الأساسي"), max_length=7, default="#2e7d32", validators=[HEX_COLOR]
    )
    on_primary = models.CharField(
        _("النص فوق الأساسي"), max_length=7, default="#ffffff", validators=[HEX_COLOR]
    )
    secondary = models.CharField(
        _("الثانوي"), max_length=7, default="#00695c", validators=[HEX_COLOR]
    )
    accent = models.CharField(_("المميّز"), max_length=7, default="#f9a825", validators=[HEX_COLOR])

    # ── ألوان الحالة ───────────────────────────────────────
    success = models.CharField(_("نجاح"), max_length=7, default="#2e7d32", validators=[HEX_COLOR])
    warning = models.CharField(_("تحذير"), max_length=7, default="#ef6c00", validators=[HEX_COLOR])
    danger = models.CharField(_("خطر"), max_length=7, default="#c62828", validators=[HEX_COLOR])
    info = models.CharField(_("معلومة"), max_length=7, default="#0277bd", validators=[HEX_COLOR])

    # ── الأسطح والنص ───────────────────────────────────────
    bg = models.CharField(_("الخلفية"), max_length=7, default="#f7f8fa", validators=[HEX_COLOR])
    surface = models.CharField(_("السطح"), max_length=7, default="#ffffff", validators=[HEX_COLOR])
    border = models.CharField(_("الحدود"), max_length=7, default="#e3e6ea", validators=[HEX_COLOR])
    text = models.CharField(_("النص"), max_length=7, default="#1b1f23", validators=[HEX_COLOR])
    text_muted = models.CharField(
        _("النص الخافت"), max_length=7, default="#5c6670", validators=[HEX_COLOR]
    )

    class Meta:
        verbose_name = _("لوحة ألوان")
        verbose_name_plural = _("لوحات الألوان")
        ordering = ["profile", "mode"]
        constraints = [
            models.UniqueConstraint(fields=["profile", "mode"], name="unique_palette_per_mode"),
        ]

    def __str__(self):
        return f"{self.profile.code} · {self.mode}"

    def clean(self):
        """
        ⚠️  التباين يُفحص عند الحفظ لا عند العرض.

            لوحة غير مقروءة تُكتشف عادةً بشكوى مستخدم لا يعرف كيف
            يصف المشكلة. الفحص هنا يجعلها خطأً في شاشة الأدمن.
        """
        from branding.contrast import AA_NORMAL_TEXT, contrast_ratio

        failures = []
        for label, foreground, background in (
            (_("النص على الخلفية"), self.text, self.bg),
            (_("النص على السطح"), self.text, self.surface),
            (_("النص فوق الأساسي"), self.on_primary, self.primary),
        ):
            ratio = contrast_ratio(foreground, background)
            if ratio < AA_NORMAL_TEXT:
                failures.append(f"{label}: {ratio:.2f}:1 (المطلوب {AA_NORMAL_TEXT}:1)")

        if failures:
            raise ValidationError(
                {"__all__": _("تباين غير كافٍ — WCAG AA: ") + " · ".join(map(str, failures))}
            )
