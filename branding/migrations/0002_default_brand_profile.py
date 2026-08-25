"""
The default visual identity — created so that no installation starts unusable.

⚠️  **Why a migration and not a seed command.**

    The admin screen at `/admin/branding` reads the profile list and stops at an
    empty state when it is empty — and the frontend has no way to create the
    first one from inside that screen. So a fresh database produced a panel that
    could not be used and could not be fixed from itself.

    The only writer of a `BrandProfile` used to be `devtools/seeds/branding.py`,
    and `devtools` is installed in development alone (`config/settings/dev.py`).
    Production therefore started with zero profiles by construction, and the
    fault appeared as "branding does not work" long after deployment.

⚠️  **The colours are the seed's own, and they are not decorative.**

    `ThemePalette.clean()` refuses a palette that fails WCAG AA contrast, and an
    inactive-but-invalid palette cannot be activated at all. Copying values that
    are already verified avoids shipping an identity the panel would reject.

⚠️  **And it never overwrites.**

    `get_or_create` on the code, and the profile is activated only when no other
    active one exists. Re-running this migration on a database that already has
    an identity — or restoring an older database — must not replace the
    operator's colours with these.
"""

from django.db import migrations

CODE = "default"

PROFILE = {
    "name_ar": "المتجر الطبي",
    "name_en": "Medical Store",
    "tagline_ar": "مستلزماتك الطبية — بثقة وسرعة",
    "tagline_en": "Your medical supplies — trusted and fast",
    "font_ar": "Cairo",
    "font_en": "Inter",
    "font_size_base": "1.000",
    "radius": "0.500",
    "shadow_level": 1,
    "default_mode": "SYSTEM",
}

LIGHT = {
    "primary": "#2e7d32",
    "on_primary": "#ffffff",
    "secondary": "#00695c",
    "accent": "#a05a00",
    "success": "#2e7d32",
    "warning": "#a04100",
    "danger": "#c62828",
    "info": "#01579b",
    "bg": "#f7f8fa",
    "surface": "#ffffff",
    "border": "#e3e6ea",
    "text": "#1b1f23",
    "text_muted": "#5c6670",
}

DARK = {
    "primary": "#66bb6a",
    "on_primary": "#0b1f10",
    "secondary": "#4db6ac",
    "accent": "#ffca28",
    "success": "#66bb6a",
    "warning": "#ffa726",
    "danger": "#ef5350",
    "info": "#42a5f5",
    "bg": "#12161a",
    "surface": "#1b2127",
    "border": "#2b333b",
    "text": "#eef2f6",
    "text_muted": "#9aa7b4",
}


def create_default_identity(apps, schema_editor):
    BrandProfile = apps.get_model("branding", "BrandProfile")
    ThemePalette = apps.get_model("branding", "ThemePalette")

    # ⚠️  Activation is conditional: an existing active identity keeps its place.
    has_active = BrandProfile.objects.filter(is_active=True).exists()

    profile, created = BrandProfile.objects.get_or_create(
        code=CODE,
        defaults={**PROFILE, "is_active": not has_active},
    )

    if not created:
        return

    # ⚠️  **Both modes, always.** The screen reads the palette for the active mode
    #     and shows the same empty state when it is missing — so a profile with
    #     one palette is as unusable as no profile at all.
    for mode, colors in (("LIGHT", LIGHT), ("DARK", DARK)):
        ThemePalette.objects.get_or_create(profile=profile, mode=mode, defaults=colors)


def remove_default_identity(apps, schema_editor):
    """
    ⚠️  Reversing removes only the untouched default.

        If the operator activated another identity, this one is no longer what
        the migration created, and deleting it on a rollback would take their
        configuration with it.
    """
    BrandProfile = apps.get_model("branding", "BrandProfile")
    BrandProfile.objects.filter(code=CODE, is_active=True).delete()


class Migration(migrations.Migration):
    dependencies = [("branding", "0001_initial")]

    operations = [
        migrations.RunPython(create_default_identity, remove_default_identity),
    ]
