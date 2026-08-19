"""
The default visual identity — two complete palettes.

⚠️  The colours are chosen to pass **WCAG AA**, not to look pretty in a screenshot.

    A palette that `ThemePalette.clean()` rejects cannot be activated at all; so
    a seed with failing colours means a system that does not boot.

⚠️  Medical green is the primary — taken from the Greeny template as an initial
    value, as ADR-22 states, and the admin changes it from the panel with no deployment.
"""

from branding.models import BrandProfile, DefaultMode, ThemeMode, ThemePalette

PROFILE = {
    "code": "default",
    "name_ar": "المتجر الطبي",
    "name_en": "Medical Store",
    "tagline_ar": "مستلزماتك الطبية — بثقة وسرعة",
    "tagline_en": "Your medical supplies — trusted and fast",
    "font_ar": "Cairo",
    "font_en": "Inter",
    "font_size_base": "1.000",
    "radius": "0.500",
    "shadow_level": 1,
    "default_mode": DefaultMode.SYSTEM,
    "contact_email": "support@example.com",
    "contact_phone": "0221234567",
    "whatsapp": "01001234567",
    "address_ar": "القاهرة — مدينة نصر",
    "address_en": "Cairo — Nasr City",
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
    # ⚠️  **Dark** text on the light green.
    #     White on #66bb6a gives 2.1:1 — less than half the acceptable threshold.
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


def seed():
    payload = dict(PROFILE)
    code = payload.pop("code")

    # ⚠️  It is not activated by force.
    #
    #     Had the admin activated a seasonal identity, re-running the seed would
    #     return it to the default unasked — an intervention in a live decision.
    #     Activation happens only when nothing is active (or when the active
    #     profile is this very one).
    active = BrandProfile.objects.filter(is_active=True).first()
    payload["is_active"] = active is None or active.code == code

    profile, _created = BrandProfile.objects.update_or_create(code=code, defaults=payload)

    for mode, colors in ((ThemeMode.LIGHT, LIGHT), (ThemeMode.DARK, DARK)):
        ThemePalette.objects.update_or_create(profile=profile, mode=mode, defaults=colors)

    return {"profile": profile, "counts": {"profiles": 1, "palettes": 2}}
