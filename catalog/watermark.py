"""
The store's mark on a product photo — logo + domain, low-opacity, one corner.

⚠️  Pulled from `branding` at the moment of upload, not baked in as a constant.

    A hardcoded domain or logo drifts the day either changes. Reading
    `branding.services.get_active_profile()` and `settings.PUBLIC_SITE_DOMAIN`
    on every upload means a photo taken after a rebrand carries the new mark
    with no code change — the price is that photos uploaded *before* the
    rebrand keep the old one; nothing re-processes what is already stored.

⚠️  A silent no-op when there is nothing to stamp, never a raised error.

    No brand profile yet, or a profile with no logo uploaded, is the normal
    state on day one. Refusing a product photo over a missing watermark asset
    would block the admin from listing their first product.
"""

from __future__ import annotations

import io

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFont, ImageOps

from branding import services as branding_services

#: The logo's width as a fraction of the photo's width.
LOGO_WIDTH_RATIO = 0.16
#: Low enough that the product underneath still reads clearly.
OPACITY = 0.55
#: Breathing room from the edges, as a fraction of the photo's shorter side.
MARGIN_RATIO = 0.03

_SAVE_FORMAT = {
    "JPEG": ("JPEG", {"quality": 90}),
    "WEBP": ("WEBP", {"quality": 90}),
    "PNG": ("PNG", {}),
}


def apply(uploaded_file) -> ContentFile | None:
    """
    Returns a new file with the mark composited into its bottom-left corner,
    named the same as `uploaded_file` — or `None` if there was nothing to
    stamp it with, or the file could not be read as an image. Either way the
    caller keeps uploading the original; this never blocks the upload.
    """
    uploaded_file.seek(0)
    try:
        source = Image.open(uploaded_file)
        source.load()
    except Exception:
        return None
    finally:
        uploaded_file.seek(0)

    fmt = (source.format or "JPEG").upper()
    if fmt not in _SAVE_FORMAT:
        return None

    # A phone photo's rotation lives in its EXIF tag, not its pixels.
    canvas = ImageOps.exif_transpose(source).convert("RGBA")

    mark = _build_mark(canvas.width)
    if mark is None:
        return None

    margin = int(min(canvas.size) * MARGIN_RATIO)
    position = (margin, canvas.height - mark.height - margin)
    canvas.alpha_composite(mark, position)

    encoded = _encode(canvas, fmt)
    encoded.name = uploaded_file.name
    return encoded


def _build_mark(photo_width: int) -> Image.Image | None:
    logo = _logo_layer(photo_width)
    text = _text_layer(photo_width)
    if logo is None and text is None:
        return None

    gap = max(4, int(photo_width * 0.01)) if logo and text else 0
    width = (logo.width if logo else 0) + gap + (text.width if text else 0)
    height = max(logo.height if logo else 0, text.height if text else 0)

    mark = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    x = 0
    if logo:
        mark.alpha_composite(logo, (0, (height - logo.height) // 2))
        x = logo.width + gap
    if text:
        mark.alpha_composite(text, (x, (height - text.height) // 2))
    return mark


def _logo_layer(photo_width: int) -> Image.Image | None:
    profile = branding_services.get_active_profile()
    field = (profile.logo_light or profile.logo_dark) if profile else None
    if not field:
        return None

    try:
        with field.open("rb") as handle:
            logo = Image.open(handle)
            logo.load()
    except Exception:
        return None

    logo = logo.convert("RGBA")
    target_width = max(24, int(photo_width * LOGO_WIDTH_RATIO))
    target_height = max(1, round(logo.height * (target_width / logo.width)))
    logo = logo.resize((target_width, target_height), Image.LANCZOS)
    return _faded(logo)


def _text_layer(photo_width: int) -> Image.Image | None:
    domain = (getattr(settings, "PUBLIC_SITE_DOMAIN", "") or "").split(":")[0].strip()
    if not domain:
        return None

    font = ImageFont.load_default(size=max(12, round(photo_width * 0.032)))

    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    left, top, right, bottom = probe.textbbox((0, 0), domain, font=font)
    pad = 2
    layer = Image.new("RGBA", (right - left + pad * 2, bottom - top + pad * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    # A dark outline so the domain reads on both light and dark photo backgrounds.
    outline_alpha = round(255 * OPACITY)
    origin = (pad - left, pad - top)
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        offset = (origin[0] + dx, origin[1] + dy)
        draw.text(offset, domain, font=font, fill=(0, 0, 0, outline_alpha))
    draw.text(origin, domain, font=font, fill=(255, 255, 255, outline_alpha))
    return layer


def _faded(layer: Image.Image) -> Image.Image:
    layer.putalpha(layer.getchannel("A").point(lambda a: round(a * OPACITY)))
    return layer


def _encode(canvas: Image.Image, fmt: str) -> ContentFile:
    save_format, options = _SAVE_FORMAT[fmt]
    buffer = io.BytesIO()
    to_save = canvas.convert("RGB") if save_format == "JPEG" else canvas
    to_save.save(buffer, format=save_format, **options)
    buffer.seek(0)
    return ContentFile(buffer.read())
