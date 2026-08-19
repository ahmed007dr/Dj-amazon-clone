"""
Visual identity — everything the customer sees, configurable from the admin panel.

⚠️  The boundary with `core.SystemSetting`:

        core/settings  →  operational settings (limits · business rules · flags)
        branding/      →  what is seen (colours · logo · fonts · slogans)

    Mixing them puts "the tax rate" and "the primary colour" on the same screen —
    two decisions not taken by the same person, nor with the same care.

⚠️  This domain **knows of no business domain**. No users, no products, no
    orders — enforced by `import-linter`.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.identifiers import random_filename
from core.models.base import BaseModel, TimeStampedModel, UUIDPrimaryKeyModel

#: A HEX colour — `#rgb` or `#rrggbb`
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
    ⚠️  `SYSTEM` is not a third mode — it is a **delegation** to the device preference.

        Merging it with light and dark in one field makes "what is the current
        mode?" a question with no single answer; separating it keeps the two
        palettes as two, and makes the choice between them the variable.
    """

    LIGHT = "LIGHT", _("فاتح دائمًا")
    DARK = "DARK", _("داكن دائمًا")
    SYSTEM = "SYSTEM", _("حسب تفضيل الجهاز")


class BrandProfile(BaseModel):
    """
    An identity profile.

    ⚠️  **Exactly one active** — the rest are drafts.

        Allowing more than one active profile makes "what are the system's
        colours?" depend on query ordering. And the inactive profiles are not a
        luxury: they are what allows a complete seasonal identity to be prepared
        and then activated with one click.
    """

    # ── Name and identity ──────────────────────────────────
    code = models.SlugField(_("الرمز"), max_length=50, unique=True)
    name_ar = models.CharField(_("اسم الموقع بالعربية"), max_length=120)
    name_en = models.CharField(_("اسم الموقع بالإنجليزية"), max_length=120)
    tagline_ar = models.CharField(_("الشعار النصي عربي"), max_length=200, blank=True)
    tagline_en = models.CharField(_("الشعار النصي إنجليزي"), max_length=200, blank=True)

    # ── Assets ─────────────────────────────────────────────
    # ⚠️  One logo for light and another for dark — a single logo with a
    #     transparent background and dark text disappears entirely in dark mode.
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

    # ── Fonts ──────────────────────────────────────────────
    # ⚠️  Separate Arabic and Latin fonts: a good Latin font may carry no Arabic
    #     glyphs at all, so the text falls back to the system font with no warning.
    font_ar = models.CharField(_("الخط العربي"), max_length=120, default="Cairo")
    font_en = models.CharField(_("الخط الإنجليزي"), max_length=120, default="Inter")
    font_size_base = models.DecimalField(
        _("حجم الخط الأساسي (rem)"),
        max_digits=4,
        decimal_places=3,
        default=Decimal("1.000"),
        # ⚠️  `Decimal`, not `float` — the decimal validator compares against its
        #     own type, and passing a float makes DRF warn and drops the limit from the schema.
        validators=[MinValueValidator(Decimal("0.75")), MaxValueValidator(Decimal("1.5"))],
    )

    # ── Shape ──────────────────────────────────────────────
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

    # ── Contact ────────────────────────────────────────────
    contact_email = models.EmailField(_("بريد التواصل"), blank=True)
    contact_phone = models.CharField(_("هاتف التواصل"), max_length=30, blank=True)
    whatsapp = models.CharField(_("واتساب"), max_length=30, blank=True)
    address_ar = models.CharField(_("العنوان بالعربية"), max_length=300, blank=True)
    address_en = models.CharField(_("العنوان بالإنجليزية"), max_length=300, blank=True)

    # ── Social ─────────────────────────────────────────────
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
    A colour palette for one mode.

    ⚠️  **Two palettes, not one.** Deriving the dark one automatically by
        inverting lightness produces muddy colours and contrast that falls below
        the readable threshold — and the admin cannot correct it because it is
        not a field.

    ⚠️  A UUIDv7 key, not BigInt.

        It looked like "a child table that never appears in a URL", and then it
        did appear, at
        `/branding/admin/profiles/{id}/palettes/{id}/`. A sequential id in a URL
        is forbidden without exception — `test_exposed_models_use_uuid_pk`
        caught it, which is exactly why that test exists.
    """

    profile = models.ForeignKey(
        BrandProfile,
        on_delete=models.CASCADE,
        related_name="palettes",
        verbose_name=_("ملف الهوية"),
    )
    mode = models.CharField(_("الوضع"), max_length=8, choices=ThemeMode.choices)

    # ── Brand colours ──────────────────────────────────────
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

    # ── Status colours ─────────────────────────────────────
    success = models.CharField(_("نجاح"), max_length=7, default="#2e7d32", validators=[HEX_COLOR])
    warning = models.CharField(_("تحذير"), max_length=7, default="#ef6c00", validators=[HEX_COLOR])
    danger = models.CharField(_("خطر"), max_length=7, default="#c62828", validators=[HEX_COLOR])
    info = models.CharField(_("معلومة"), max_length=7, default="#0277bd", validators=[HEX_COLOR])

    # ── Surfaces and text ──────────────────────────────────
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
        ⚠️  Contrast is checked on save, not on display.

            An unreadable palette is normally discovered through a complaint
            from a user who cannot describe the problem. Checking here turns it
            into an error on the admin screen.
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
