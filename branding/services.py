"""
واجهة `branding` العامة.

⚠️  النطاقات الأخرى تستدعي هذه الدوال ولا تلمس `models.py`.

⚠️  الهوية تُقرأ في **كل** طلب صفحة تقريبًا — فهي مُخزَّنة بقوة،
    والكاش يُبطَل عند أي تعديل. بلا ذلك يصير كل عرض صفحة استعلامين
    إضافيين على جدول لا يتغيّر مرة في الشهر.
"""

from django.core.cache import cache

from branding.models import BrandProfile, DefaultMode, ThemeMode

CACHE_KEY = "branding:active"
CACHE_TIMEOUT = 60 * 60 * 12


def invalidate_cache() -> None:
    cache.delete(CACHE_KEY)


def get_active_profile() -> BrandProfile | None:
    return BrandProfile.get_active()


def theme_payload() -> dict:
    """
    الحمولة العامة التي يستهلكها الفرونت إند.

    ⚠️  **رموز جاهزة لا حقول خام.**

        إرسال الحقول كما هي يترك الفرونت يبني أسماء المتغيرات
        بنفسه — فيصير اسم الرمز متكرّرًا في مكانين، وأي إضافة لون
        تحتاج تعديلين. الباك إند يرسل الخريطة النهائية.
    """
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached

    profile = get_active_profile()
    payload = _serialize(profile) if profile else _fallback()

    cache.set(CACHE_KEY, payload, CACHE_TIMEOUT)
    return payload


def _asset(field) -> str:
    return field.url if field else ""


def _serialize(profile: BrandProfile) -> dict:
    palettes = {palette.mode: palette for palette in profile.palettes.all()}

    return {
        "code": profile.code,
        "name": {"ar": profile.name_ar, "en": profile.name_en},
        "tagline": {"ar": profile.tagline_ar, "en": profile.tagline_en},
        "assets": {
            "logo_light": _asset(profile.logo_light),
            "logo_dark": _asset(profile.logo_dark),
            "icon": _asset(profile.icon),
            "favicon": _asset(profile.favicon),
            "og_image": _asset(profile.og_image),
        },
        "default_mode": profile.default_mode,
        "tokens": {
            # ⚠️  ثابتة عبر الوضعين — المسافات ونقاط الكسر ليست
            #     قابلة للتحكم أصلًا لأن تغييرها يكسر التخطيط
            "--font-ar": profile.font_ar,
            "--font-en": profile.font_en,
            "--font-size-base": f"{profile.font_size_base}rem",
            "--radius": f"{profile.radius}rem",
            "--shadow-level": str(profile.shadow_level),
        },
        "palettes": {mode.value: _palette_tokens(palettes.get(mode.value)) for mode in ThemeMode},
        "contact": {
            "email": profile.contact_email,
            "phone": profile.contact_phone,
            "whatsapp": profile.whatsapp,
            "address": {"ar": profile.address_ar, "en": profile.address_en},
        },
        "social": {
            "facebook": profile.facebook,
            "instagram": profile.instagram,
            "x": profile.x_twitter,
            "linkedin": profile.linkedin,
            "youtube": profile.youtube,
            "tiktok": profile.tiktok,
        },
    }


#: الحقل في الموديل  →  اسم رمز CSS
COLOR_TOKENS = {
    "primary": "--color-primary",
    "on_primary": "--color-on-primary",
    "secondary": "--color-secondary",
    "accent": "--color-accent",
    "success": "--color-success",
    "warning": "--color-warning",
    "danger": "--color-danger",
    "info": "--color-info",
    "bg": "--color-bg",
    "surface": "--color-surface",
    "border": "--color-border",
    "text": "--color-text",
    "text_muted": "--color-text-muted",
}


def _palette_tokens(palette) -> dict:
    if palette is None:
        return {}
    return {token: getattr(palette, field) for field, token in COLOR_TOKENS.items()}


def _fallback() -> dict:
    """
    ⚠️  هوية افتراضية حين لا يوجد ملف مفعّل.

        الفرونت إند بلا ألوان يرسم صفحة بيضاء بنص أسود — يبدو
        عطلًا لا «لم تُضبط الهوية بعد». الافتراضي يجعل النظام
        صالحًا للاستخدام من أول دقيقة.
    """
    from branding.models import ThemePalette

    light = ThemePalette(mode=ThemeMode.LIGHT)
    dark = ThemePalette(
        mode=ThemeMode.DARK,
        primary="#66bb6a",
        on_primary="#0b1f10",
        secondary="#4db6ac",
        accent="#ffca28",
        success="#66bb6a",
        warning="#ffa726",
        danger="#ef5350",
        info="#42a5f5",
        bg="#12161a",
        surface="#1b2127",
        border="#2b333b",
        text="#eef2f6",
        text_muted="#9aa7b4",
    )

    return {
        "code": "default",
        "name": {"ar": "المتجر الطبي", "en": "Medical Store"},
        "tagline": {"ar": "", "en": ""},
        "assets": {
            "logo_light": "",
            "logo_dark": "",
            "icon": "",
            "favicon": "",
            "og_image": "",
        },
        "default_mode": DefaultMode.SYSTEM,
        "tokens": {
            "--font-ar": "Cairo",
            "--font-en": "Inter",
            "--font-size-base": "1.0rem",
            "--radius": "0.5rem",
            "--shadow-level": "1",
        },
        "palettes": {
            ThemeMode.LIGHT: _palette_tokens(light),
            ThemeMode.DARK: _palette_tokens(dark),
        },
        "contact": {"email": "", "phone": "", "whatsapp": "", "address": {"ar": "", "en": ""}},
        "social": {
            "facebook": "",
            "instagram": "",
            "x": "",
            "linkedin": "",
            "youtube": "",
            "tiktok": "",
        },
    }
