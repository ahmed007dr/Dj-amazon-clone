"""
الهوية البصرية الافتراضية — لوحتان مكتملتان.

⚠️  الألوان مختارة لتجتاز **WCAG AA** لا لتبدو جميلة في لقطة شاشة.

    اللوحة التي ترفضها `ThemePalette.clean()` لا يمكن تفعيلها
    أصلًا؛ فبذرة بألوان فاشلة تعني نظامًا لا يقلع.

⚠️  الأخضر الطبي هو الأساسي — مأخوذ من قالب Greeny كقيمة ابتدائية
    كما نصّ ADR-22، والأدمن يغيّره من اللوحة بلا نشر.
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
    # ⚠️  نص **داكن** فوق الأخضر الفاتح.
    #     الأبيض على #66bb6a يعطي 2.1:1 — أقل من نصف الحد المقبول.
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

    # ⚠️  لا تُفعَّل قسرًا.
    #
    #     لو كان الأدمن قد فعّل هوية موسمية، فإعادة تشغيل البذرة
    #     تعيده إلى الافتراضية بلا سؤال — وهو تدخّل في قرار حيّ.
    #     التفعيل يقع فقط حين لا يكون هناك مفعَّل أصلًا (أو حين
    #     يكون هو نفسه هذا الملف).
    active = BrandProfile.objects.filter(is_active=True).first()
    payload["is_active"] = active is None or active.code == code

    profile, _created = BrandProfile.objects.update_or_create(code=code, defaults=payload)

    for mode, colors in ((ThemeMode.LIGHT, LIGHT), (ThemeMode.DARK, DARK)):
        ThemePalette.objects.update_or_create(profile=profile, mode=mode, defaults=colors)

    return {"profile": profile, "counts": {"profiles": 1, "palettes": 2}}
