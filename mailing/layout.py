"""
The branded HTML layout — one wrapper applied to **every** outbound message.

⚠️  **Applied at delivery, not at enqueueing — and to the message, not to the template.**

    Every path that sends mail ends in `services._attempt`: the transactional
    templates, a reply written by an employee, the test message. Wrapping each
    template would have branded the thirteen that exist today and none of the
    ones added tomorrow; wrapping the delivery brands all of them with no upkeep.

    And the stored `OutboundMessage.body` stays plain text. The HTML is derived from
    it every time, so editing this file restyles the mail that is still queued, and
    the text/plain alternative is exactly what the log shows.

⚠️  **`mailing` cannot import `branding` — so it asks for a callable by name.**

    The two are siblings in the import-linter contract ("branding | mailing") and
    siblings never import each other. The identity is therefore read through
    `settings.MAIL_BRAND_PROVIDER`, a dotted path to a function returning a plain
    dict (the shape is documented on `branding.services.mail_identity`, and pinned
    by a test on each side). `import_string` is a runtime lookup, not an import
    statement, so the contract stays honest: neither side knows the other's types.
    Setting it to an empty string turns branding off (plain header, no logo).

⚠️  **Every dynamic string goes through `esc()`.**

    The body is written by an admin (a manual reply) or interpolated from customer
    data (names, addresses) — both are untrusted as far as HTML is concerned. The
    layout is built from f-strings, so the rule is mechanical: nothing reaches the
    markup without passing `esc()`, and colours are validated against a hex pattern
    because they land in a `style` attribute.

⚠️  **The logo is embedded (CID), not linked.**

    A linked image is blocked by default in most clients until the reader clicks
    "display images" — so a first-time customer sees an empty box above their
    password-reset link. An embedded one renders immediately. It is re-encoded to
    at most 440×112 px (twice the size it is displayed at), because the upload limit
    is 2 MB and sending that with every email would be absurd.

    If the file cannot be read, the absolute URL (from `MEDIA_ORIGIN`) is used,
    and failing that the store's name as text.

⚠️  **Raster only, by construction.** Gmail and Outlook do not render SVG, and the
    branding upload validator only accepts JPEG / PNG / WebP (`ALLOWED_IMAGE_TYPES`,
    asserted in the tests). A WebP logo is converted to PNG here for the same reason.

⚠️  **A failure here never blocks delivery.** `apply()` swallows its own errors and
    leaves the message as plain text — an unbranded password reset beats a lost one.
"""

from __future__ import annotations

import base64
import html
import io
import logging
import re
from dataclasses import dataclass
from email.mime.image import MIMEImage
from email.utils import make_msgid
from urllib.parse import urlparse

from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.utils import timezone
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)

#: The setting naming the identity provider, and the value used when it is absent
BRAND_PROVIDER_SETTING = "MAIL_BRAND_PROVIDER"
DEFAULT_BRAND_PROVIDER = "branding.services.mail_identity"

DEFAULT_COLOR = "#2e7d32"
_HEX_COLOR = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")

#: The box the logo is displayed in (CSS px) and the size it is embedded at (2x)
LOGO_BOX = (220, 56)
LOGO_EMBED = (LOGO_BOX[0] * 2, LOGO_BOX[1] * 2)
MAX_LOGO_BYTES = 5 * 1024 * 1024
LOGO_CACHE_TTL = 60 * 60 * 12

LABELS = {
    "ar": {"email": "البريد الإلكتروني", "phone": "الهاتف", "website": "الموقع"},
    "en": {"email": "Email", "phone": "Phone", "website": "Website"},
}

FONT_STACK = {
    "ar": "Tahoma,'Segoe UI',Arial,sans-serif",
    "en": "'Segoe UI',Helvetica,Arial,sans-serif",
}


def esc(value) -> str:
    """HTML-escape for both text and attribute positions."""
    return html.escape(str(value or ""), quote=True)


def _direction(language: str) -> str:
    return "rtl" if language == "ar" else "ltr"


def _language(language: str) -> str:
    return language if language in LABELS else "ar"


# ═══════════════════════════════════════════════════════════
#  The identity
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class MailBrand:
    """What the layout needs to know about the store — nothing more."""

    name_ar: str = ""
    name_en: str = ""
    color: str = DEFAULT_COLOR
    logo_name: str = ""
    logo_url: str = ""
    email: str = ""
    phone: str = ""
    address_ar: str = ""
    address_en: str = ""
    website: str = ""

    def name(self, language: str) -> str:
        preferred = self.name_ar if language == "ar" else self.name_en
        return preferred or self.name_ar or self.name_en

    def address(self, language: str) -> str:
        preferred = self.address_ar if language == "ar" else self.address_en
        return preferred or self.address_ar or self.address_en


def load_brand() -> MailBrand:
    """
    The active identity, through the configured provider.

    ⚠️  Any failure — a missing provider, a database hiccup, a malformed answer —
        yields an unbranded layout, never an exception.
    """
    path = getattr(settings, BRAND_PROVIDER_SETTING, DEFAULT_BRAND_PROVIDER)
    data: dict = {}

    if path:
        try:
            data = import_string(path)() or {}
        except Exception:
            logger.exception("تعذّر تحميل هوية البريد من %s — تخطّي التنسيق", path)

    name = data.get("name") or {}
    logo = data.get("logo") or {}
    contact = data.get("contact") or {}
    address = contact.get("address") or {}

    color = str(data.get("color") or "")
    if not _HEX_COLOR.fullmatch(color):
        color = DEFAULT_COLOR

    return MailBrand(
        name_ar=str(name.get("ar") or ""),
        name_en=str(name.get("en") or ""),
        color=color,
        logo_name=str(logo.get("name") or ""),
        logo_url=str(logo.get("url") or ""),
        email=str(contact.get("email") or ""),
        phone=str(contact.get("phone") or ""),
        address_ar=str(address.get("ar") or ""),
        address_en=str(address.get("en") or ""),
        website=str(getattr(settings, "SITE_ORIGIN", "") or ""),
    )


# ═══════════════════════════════════════════════════════════
#  The logo
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Logo:
    data: bytes
    subtype: str  # "png" | "jpeg"
    width: int  # display size, CSS px
    height: int


def _normalise_logo(raw: bytes) -> Logo:
    """
    Re-encode to a small raster every mail client can show.

    ⚠️  Raises on anything that is not a PNG / JPEG / WebP — the caller then falls
        back to the URL, and the alt text still names the store.
    """
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(raw)) as source:
        fmt = (source.format or "").upper()
        if fmt not in {"PNG", "JPEG", "WEBP"}:
            raise ValueError(f"صيغة شعار غير مدعومة في البريد: {fmt or 'غير معروفة'}")

        image = ImageOps.exif_transpose(source)
        image.load()

    image.thumbnail(LOGO_EMBED, Image.Resampling.LANCZOS)

    out = io.BytesIO()
    if fmt == "JPEG":
        image.convert("RGB").save(out, "JPEG", quality=88, optimize=True)
        subtype = "jpeg"
    else:
        # PNG and WebP -> PNG: Outlook and older clients cannot show WebP at all
        if image.mode not in {"RGB", "RGBA", "L", "LA", "P"}:
            image = image.convert("RGBA")
        image.save(out, "PNG", optimize=True)
        subtype = "png"

    # The display size: shrink to the box when the embedded image is larger than it
    # (that is the 2x case), and never upscale a logo that already fits.
    width, height = image.size
    if width > LOGO_BOX[0] or height > LOGO_BOX[1]:
        ratio = min(LOGO_BOX[0] / width, LOGO_BOX[1] / height)
    else:
        ratio = 1.0

    return Logo(
        data=out.getvalue(),
        subtype=subtype,
        width=max(1, round(width * ratio)),
        height=max(1, round(height * ratio)),
    )


def read_logo(brand: MailBrand) -> Logo | None:
    """The embeddable logo, or `None` when there is none or it cannot be read."""
    if not brand.logo_name:
        return None

    # The storage name is random per upload (`random_filename`), so a replaced logo
    # gets a new key and the old entry simply ages out.
    key = f"mailing:logo:{brand.logo_name}"
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        with default_storage.open(brand.logo_name, "rb") as handle:
            raw = handle.read(MAX_LOGO_BYTES + 1)
        if len(raw) > MAX_LOGO_BYTES:
            raise ValueError("ملف الشعار أكبر من الحد المسموح للبريد")
        logo = _normalise_logo(raw)
    except Exception as error:
        logger.warning("تعذّر تضمين الشعار %s في البريد: %s", brand.logo_name, error)
        return None

    cache.set(key, logo, LOGO_CACHE_TTL)
    return logo


def absolute_media_url(url: str) -> str:
    """
    A media URL a recipient's mail client can fetch.

    ⚠️  A relative `/media/…` means nothing outside the site. `MEDIA_ORIGIN` follows
        the CDN when there is one and the API server otherwise (config/settings/base.py).
    """
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    if url.startswith("//"):
        return f"{getattr(settings, 'PUBLIC_SCHEME', 'https')}:{url}"

    origin = getattr(settings, "MEDIA_ORIGIN", "") or getattr(settings, "SITE_ORIGIN", "")
    if not origin:
        return ""
    return f"{origin.rstrip('/')}/{url.lstrip('/')}"


def _cid_domain() -> str:
    host = (getattr(settings, "PUBLIC_SITE_DOMAIN", "") or "").split(":")[0].strip()
    return host or "localhost"


# ═══════════════════════════════════════════════════════════
#  Text -> HTML
# ═══════════════════════════════════════════════════════════

#: ASCII only, deliberately: an Arabic word glued to a link must not be swallowed by it
_URL = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")
_TRAILING_PUNCTUATION = ".,;:!?'"


def _split_trailing(url: str) -> tuple[str, str]:
    """`(url, trailing)` — punctuation closing the sentence is not part of the link."""
    trailing = ""
    while url:
        last = url[-1]
        if last in _TRAILING_PUNCTUATION:
            pass
        elif last == ")" and url.count(")") > url.count("("):
            pass
        elif last == "]" and url.count("]") > url.count("["):
            pass
        else:
            break
        trailing = last + trailing
        url = url[:-1]
    return url, trailing


def linkify(line: str, color: str) -> str:
    """
    Escape a line of text and turn bare `http(s)://` URLs into links.

    ⚠️  Escaping happens on the **segments around** the URLs and on the URL itself,
        never on markup we built — so there is no point at which user text is
        concatenated unescaped. Only http(s) is matched: `javascript:` is not a URL here.
    """
    parts: list[str] = []
    position = 0

    for match in _URL.finditer(line):
        url, trailing = _split_trailing(match.group(0))
        if not re.match(r"https?://[^/\s]", url):
            continue  # `https://.` — nothing worth linking

        parts.append(esc(line[position : match.start()]))
        parts.append(
            f'<a href="{esc(url)}" style="color:{color};word-break:break-all;">{esc(url)}</a>'
            f"{esc(trailing)}"
        )
        position = match.end()

    parts.append(esc(line[position:]))
    return "".join(parts)


def body_to_html(text: str, color: str) -> str:
    """
    Plain text -> paragraphs: a blank line starts a new one, a newline is a `<br>`.

    ⚠️  `dir="auto"` per paragraph. The language of the *message* sets the page
        direction, but a manual reply to an English customer from an Arabic-default
        account is an English paragraph inside an RTL page — left to the layout it
        would be right-aligned and its punctuation misplaced.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    blocks = [block for block in re.split(r"\n\s*\n", text) if block.strip()]

    paragraphs = []
    for block in blocks:
        lines = [linkify(line.strip(), color) for line in block.split("\n")]
        paragraphs.append(
            '<p dir="auto" style="margin:0 0 16px;padding:0;">' + "<br>".join(lines) + "</p>"
        )
    return "\n".join(paragraphs)


# ═══════════════════════════════════════════════════════════
#  The layout
# ═══════════════════════════════════════════════════════════


def _header(brand: MailBrand, language: str, logo: Logo | None, logo_src: str) -> str:
    name = brand.name(language)

    if logo_src:
        # With a known size (an embedded logo) both dimensions are fixed, which is the
        # only thing Outlook honours. A linked fallback has no known size, so it is boxed.
        if logo is not None:
            size = (
                f'width="{logo.width}" height="{logo.height}" '
                f'style="display:block;margin:0 auto;border:0;width:{logo.width}px;'
                f'height:{logo.height}px;"'
            )
        else:
            size = (
                f'style="display:block;margin:0 auto;border:0;max-width:{LOGO_BOX[0]}px;'
                f'max-height:{LOGO_BOX[1]}px;height:auto;"'
            )
        return f'<img src="{esc(logo_src)}" alt="{esc(name)}" {size}>'

    if name:
        return (
            f'<div style="font-size:22px;font-weight:700;line-height:1.3;'
            f'color:{brand.color};text-align:center;">{esc(name)}</div>'
        )
    return ""


def _footer(brand: MailBrand, language: str) -> str:
    labels = LABELS[language]
    name = brand.name(language)
    lines: list[str] = []

    if name:
        lines.append(f'<strong style="color:#1b1f23;">{esc(name)}</strong>')

    address = brand.address(language)
    if address:
        lines.append(esc(address))

    if brand.email:
        lines.append(
            f"{esc(labels['email'])}: "
            f'<a href="mailto:{esc(brand.email)}" style="color:{brand.color};">'
            f"{esc(brand.email)}</a>"
        )

    if brand.phone:
        dial = re.sub(r"[^\d+]", "", brand.phone)
        # ⚠️  `dir="ltr"` on the number: inside an RTL line the "+" and the groups of
        #     digits are reordered, and a phone number read backwards is a wrong number.
        lines.append(
            f"{esc(labels['phone'])}: "
            f'<a href="tel:{esc(dial)}" dir="ltr" style="color:{brand.color};'
            f'unicode-bidi:embed;">{esc(brand.phone)}</a>'
        )

    if brand.website:
        shown = urlparse(brand.website).netloc or brand.website
        lines.append(
            f"{esc(labels['website'])}: "
            f'<a href="{esc(brand.website)}" style="color:{brand.color};">{esc(shown)}</a>'
        )

    year = timezone.now().year
    lines.append(f'<span style="color:#8a949e;">© {year} {esc(name)}</span>' if name else "")

    return "<br>".join(line for line in lines if line)


def render_html(
    *,
    subject: str,
    body: str,
    language: str,
    brand: MailBrand,
    logo: Logo | None = None,
    logo_src: str = "",
) -> str | None:
    """
    The full HTML document, or `None` when there is nothing to put in it.

    ⚠️  Table layout and inline CSS: the only thing that renders the same in Gmail,
        Outlook (a Word engine) and Apple Mail. `<style>` blocks and flexbox are not
        available to the clients that matter most.
    """
    language = _language(language)

    if not (body or "").strip():
        return None

    content = body_to_html(body, brand.color)
    if not content:
        return None

    direction = _direction(language)
    align = "right" if direction == "rtl" else "left"
    font = FONT_STACK[language]
    header = _header(brand, language, logo, logo_src)
    footer = _footer(brand, language)

    # ⚠️  No `text-align` on the body cell: an explicit one is inherited by every
    #     paragraph and overrides their `dir="auto"` — an English reply would be pushed
    #     to the right edge of an Arabic message. `dir` alone aligns each paragraph
    #     by its own first strong character.
    bar = (
        f'<tr><td style="height:6px;line-height:6px;font-size:0;background:{brand.color};'
        'border-radius:8px 8px 0 0;">&nbsp;</td></tr>'
    )
    header_row = (
        f'<tr><td align="center" style="padding:28px 32px 4px;">{header}</td></tr>'
        if header
        else ""
    )
    body_row = (
        f'<tr><td dir="{direction}" style="padding:24px 32px 12px;font-family:{font};'
        f'font-size:16px;line-height:1.8;color:#1b1f23;">{content}</td></tr>'
    )
    footer_row = (
        f'<tr><td dir="{direction}" align="{align}" style="padding:20px 32px;'
        f"background:#f7f8fa;border-top:1px solid #e3e6ea;font-family:{font};"
        f'font-size:13px;line-height:1.8;color:#5c6670;text-align:{align};">{footer}</td></tr>'
        if footer
        else ""
    )

    outer = 'role="presentation" cellpadding="0" cellspacing="0" border="0"'
    card = (
        "width:100%;max-width:600px;background:#ffffff;"
        "border:1px solid #e3e6ea;border-radius:8px;"
    )

    rows = [
        "<!doctype html>",
        f'<html lang="{language}" dir="{direction}">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<meta name="color-scheme" content="light">',
        '<meta name="supported-color-schemes" content="light">',
        f"<title>{esc(subject)}</title>",
        "</head>",
        '<body style="margin:0;padding:0;background:#f4f6f8;">',
        f'<table {outer} width="100%" style="background:#f4f6f8;">',
        '<tr><td align="center" style="padding:24px 12px;">',
        f'<table {outer} width="600" dir="{direction}" style="{card}">',
        bar,
        header_row,
        body_row,
        footer_row,
        "</table>",
        "</td></tr>",
        "</table>",
        "</body>",
        "</html>",
    ]
    return "\n".join(row for row in rows if row) + "\n"


# ═══════════════════════════════════════════════════════════
#  Entry points
# ═══════════════════════════════════════════════════════════


def apply(email, *, language: str = "ar") -> bool:
    """
    Add the branded HTML alternative (and the inline logo) to a message.

    ⚠️  The plain-text body stays as the `text/plain` part — clients that prefer text
        and spam filters that compare the two both get what they expect.

    ⚠️  Returns `False` and leaves the message untouched when there is nothing to
        wrap (an empty body) or when anything at all goes wrong.
    """
    text = email.body or ""
    if not text.strip():
        return False

    try:
        brand = load_brand()
        logo = read_logo(brand)

        content_id = make_msgid(idstring="logo", domain=_cid_domain()) if logo else ""
        logo_src = f"cid:{content_id[1:-1]}" if logo else absolute_media_url(brand.logo_url)

        document = render_html(
            subject=email.subject,
            body=text,
            language=language,
            brand=brand,
            logo=logo,
            logo_src=logo_src,
        )
        if document is None:
            return False

        image = None
        if logo:
            image = MIMEImage(logo.data, _subtype=logo.subtype)
            image.add_header("Content-ID", content_id)
            image.add_header("Content-Disposition", "inline", filename=f"logo.{logo.subtype}")
    except Exception:
        logger.exception("تعذّر بناء قالب HTML للرسالة «%s» — تُرسل نصًا", email.subject)
        return False

    email.attach_alternative(document, "text/html")
    if image is not None:
        email.attach(image)
        # ⚠️  `related`, not the default `mixed`: with `mixed` the logo is offered as a
        #     downloadable attachment in several clients instead of drawing in the page.
        email.mixed_subtype = "related"

    return True


def preview(*, subject: str, body: str, language: str = "ar") -> str | None:
    """
    The HTML an admin sees before sending — the same renderer, with a self-contained logo.

    ⚠️  A `cid:` reference only resolves inside a real message, so the preview inlines
        the (already shrunk) logo as a `data:` URI. It is shown in a sandboxed iframe,
        which has no origin to fetch anything else from.
    """
    brand = load_brand()
    logo = read_logo(brand)

    if logo:
        payload = base64.b64encode(logo.data).decode("ascii")
        logo_src = f"data:image/{logo.subtype};base64,{payload}"
    else:
        logo_src = absolute_media_url(brand.logo_url)

    return render_html(
        subject=subject, body=body, language=language, brand=brand, logo=logo, logo_src=logo_src
    )
