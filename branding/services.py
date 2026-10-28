"""
The public interface of `branding`.

⚠️  Other domains call these functions and never touch `models.py`.

⚠️  The identity is read on **almost every** page request — so it is
    aggressively cached, and the cache is invalidated on any edit. Without that,
    every page view costs two extra queries on a table that does not change once
    a month.
"""

import logging

from django.core.cache import cache

from branding import channels
from branding.models import BrandProfile, ContactChannel, DefaultMode, ThemeMode

logger = logging.getLogger(__name__)

CACHE_KEY = "branding:active"
CACHE_TIMEOUT = 60 * 60 * 12


def invalidate_cache() -> None:
    cache.delete(CACHE_KEY)


def get_active_profile() -> BrandProfile | None:
    return BrandProfile.get_active()


def theme_payload() -> dict:
    """
    The public payload the frontend consumes.

    ⚠️  **Ready-made tokens, not raw fields.**

        Sending the fields as they are leaves the frontend to build the variable
        names itself — so a token name ends up duplicated in two places, and
        adding a colour needs two edits. The backend sends the finished map.
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


def public_channels(profile: BrandProfile) -> list[dict]:
    """
    The **active** contact channels, in display order, as the storefront paints them.

    ⚠️  Only what gets painted: the kind · the resolved label · the display text · the
        link(s) · the order · whether it earns the floating button. No id, no
        `is_active`, no raw message fields — the prefilled text reaches the public only
        inside the WhatsApp link, where it is visible to the customer anyway.

    ⚠️  A row that fails to parse is **skipped, not raised**. This runs on every cache
        miss for every visitor; one corrupt row (a hand-edited database, a rule that
        tightened after the row was written) must cost a log line, not the whole site.
    """
    rows = ContactChannel.objects.filter(profile=profile, is_active=True).order_by(
        "display_order", "created_at"
    )

    entries = []
    for channel in rows:
        try:
            described = channel.describe()
        except channels.ChannelError:
            logger.warning("Skipping unreadable contact channel %s", channel.pk)
            continue

        entries.append(
            {
                "kind": channel.kind,
                "label": channel.label,
                "value": described["display"],
                "href": described["href"],
                "href_en": described["href_en"],
                "order": channel.display_order,
                "floating": channel.kind == "WHATSAPP" and channel.show_floating_button,
            }
        )
    return entries


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
            "hero_light": _asset(profile.hero_image_light),
            "hero_dark": _asset(profile.hero_image_dark),
        },
        "hero": {
            "title": {"ar": profile.hero_title_ar, "en": profile.hero_title_en},
            "subtitle": {"ar": profile.hero_subtitle_ar, "en": profile.hero_subtitle_en},
            "cta_label": {"ar": profile.hero_cta_label_ar, "en": profile.hero_cta_label_en},
            # ⚠️  Sent as stored: empty means "the catalogue", and the *route* for it is the
            #     frontend's to know — the backend has no business owning `/products`.
            "cta_url": profile.hero_cta_url,
        },
        "default_mode": profile.default_mode,
        "tokens": {
            # ⚠️  Constant across both modes — spacing and breakpoints are not
            #     configurable at all, because changing them breaks the layout
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
        # ⚠️  Additional to `contact` / `social` above, which keep rendering as they always did
        "contact_channels": public_channels(profile),
    }


#: The model field  →  the CSS token name
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
    ⚠️  A default identity for when no profile is active.

        A frontend with no colours paints a white page with black text — which
        looks like a fault rather than "the identity has not been configured
        yet". The default makes the system usable from the first minute.
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
            "hero_light": "",
            "hero_dark": "",
        },
        "hero": {
            "title": {"ar": "", "en": ""},
            "subtitle": {"ar": "", "en": ""},
            "cta_label": {"ar": "", "en": ""},
            "cta_url": "",
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
        "contact_channels": [],
    }


# ═══════════════════════════════════════════════════════════
#  What an email needs to look like it came from the store
# ═══════════════════════════════════════════════════════════


def mail_identity() -> dict:
    """
    The identity as `mailing` consumes it — a plain dict, not a model.

    ⚠️  **`mailing` cannot import this module, and does not.**

        `branding` and `mailing` are siblings (`pyproject.toml` → import-linter), and
        siblings never import each other. `mailing.layout` therefore asks for a *callable*
        by dotted path (`settings.MAIL_BRAND_PROVIDER`) and this is what that path
        points at. The contract is the shape below; neither side knows the other's types.

    ⚠️  **Only `logo_light`, never `logo_dark`.**

        An email body is white in practically every client. The dark logo is usually
        white itself, so falling back to it would put an invisible mark on the header —
        and a missing logo (the store name as text) beats an invisible one.

    ⚠️  Returns `{}` when no profile is active — the layout then falls back to a
        plain, name-less header instead of failing the delivery.
    """
    profile = get_active_profile()
    if profile is None:
        return {}

    light = next((p for p in profile.palettes.all() if p.mode == ThemeMode.LIGHT), None)
    logo = profile.logo_light

    return {
        "name": {"ar": profile.name_ar, "en": profile.name_en},
        "color": light.primary if light else "",
        # `name` is the path inside the storage (readable by mailing through the default
        # storage to embed the file); `url` is the fallback when it cannot be read.
        "logo": {"name": logo.name, "url": logo.url} if logo else {},
        "contact": {
            "email": profile.contact_email,
            "phone": profile.contact_phone,
            "address": {"ar": profile.address_ar, "en": profile.address_en},
        },
    }
