"""
Contact channels — turning what the admin typed into what the storefront links to.

⚠️  **Every value here ends up inside an `href` on the busiest pages of the site**,
    typed by someone who can edit it from a panel. So this module is a parser,
    not a formatter: it accepts a short list of shapes per kind, rebuilds the
    link itself on a domain it chose, and refuses everything else.

        javascript:…  data:…  //evil.example  http://…  user:pass@host  control chars

    Passing the admin's text through (even "mostly checked") makes the field a
    stored XSS or a phishing redirect; rebuilding the link makes it neither.

⚠️  Pure Python — no models, no request. `models.ContactChannel.clean()` and the API
    serializer both call `clean_channel()`, so the Django admin, the API, the seed
    and the shell enforce one rule instead of four copies that drift apart.

⚠️  The canonical form is **idempotent**: normalising what was already normalised
    returns the same thing. `save()` normalises on every write, so a row read back
    from the database and saved again never changes.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import URLValidator, validate_email

#: Matches `ContactChannel.value`'s column width.
MAX_VALUE_LENGTH = 300
MAX_LABEL_LENGTH = 60
MAX_MESSAGE_LENGTH = 300

#: ⚠️  An Egyptian store: `01012345678` means `+20 1012345678`. Overridable with
#:     `settings.BRANDING_DEFAULT_COUNTRY_CODE` for a deployment elsewhere.
DEFAULT_COUNTRY_CODE = "20"

#: The kinds whose value is a phone number
_PHONE_KINDS = frozenset({"WHATSAPP", "PHONE"})


# ═══════════════════════════════════════════════════════════
#  Errors
# ═══════════════════════════════════════════════════════════


class ChannelError(Exception):
    """One refused field: a stable `code` (the UI translates by it) and a bilingual `message`."""

    def __init__(self, code: str, ar: str, en: str):
        self.code = code
        self.message = f"{ar} — {en}"
        super().__init__(self.message)


class ChannelValidationError(Exception):
    """Every refused field of one channel, keyed by field name."""

    def __init__(self, errors: dict[str, ChannelError]):
        self.errors = errors
        super().__init__("; ".join(f"{field}: {err.message}" for field, err in errors.items()))


# Shared messages — written once so the same mistake reads the same everywhere
_REQUIRED = ChannelError("required", "هذا الحقل مطلوب", "This field is required")
_TOO_LONG = ChannelError("too_long", "القيمة أطول من المسموح", "The value is too long")
_CONTROL = ChannelError(
    "control_chars",
    "القيمة تحتوي على رموز غير مسموحة",
    "The value contains characters that are not allowed",
)
_HTTPS = ChannelError(
    "https_required",
    "الرابط يجب أن يبدأ بـ https:// (روابط http وjavascript وdata مرفوضة)",
    "The link must start with https:// (http, javascript and data links are refused)",
)
_URL = ChannelError("invalid_url", "رابط غير صالح", "Invalid link")
_WRONG_HOST = ChannelError(
    "wrong_host",
    "الرابط لا يتبع الموقع المختار — اختر النوع «رابط آخر» لروابط المواقع الأخرى",
    "The link is not on the chosen platform — use the “Other link” type for other sites",
)


# ═══════════════════════════════════════════════════════════
#  Text hygiene
# ═══════════════════════════════════════════════════════════

# Arabic-Indic (٠-٩) and Extended Arabic-Indic (۰-۹) digits → ASCII. An Egyptian admin
# types the number with the Arabic keyboard's digits more often than not.
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _clean_text(
    raw: object, *, allow_newline: bool = False, strip_format: bool = False, limit: int
) -> str:
    """
    Trim and refuse anything that is not plain printable text.

    ⚠️  Category `C*` (control · format · surrogate · private · unassigned) and the
        line/paragraph separators are refused — that is what covers NUL, tabs,
        newlines, zero-width characters and the bidi overrides (U+202E) used to
        make `evil.com/moc.elgoog` read as something else.

    ⚠️  `strip_format` drops the invisible *format* characters instead of refusing
        them, for phone numbers only: copying a number out of a contacts app
        routinely drags U+202A/U+202C along, and failing that with "invalid
        characters" on a number that looks fine is a support ticket.
    """
    text = "" if raw is None else str(raw)
    if len(text) > limit * 2:  # cheap bound before any per-character work
        raise _TOO_LONG

    text = text.replace("\r\n", "\n").strip()

    cleaned: list[str] = []
    for char in text:
        category = unicodedata.category(char)
        if char == "\n" and allow_newline:
            cleaned.append(char)
        elif category == "Cf" and strip_format:
            continue
        elif category[0] == "C" or category in ("Zl", "Zp"):
            raise _CONTROL
        else:
            cleaned.append(char)

    text = "".join(cleaned).strip()
    if len(text) > limit:
        raise _TOO_LONG
    return text


# ═══════════════════════════════════════════════════════════
#  What a normalised channel is
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Resolved:
    value: str  # canonical — what gets stored
    display: str  # what the visitor reads
    href: str  # the link, with no prefilled message


# ── Phone numbers ──────────────────────────────────────────


def _country_code() -> str:
    return str(getattr(settings, "BRANDING_DEFAULT_COUNTRY_CODE", DEFAULT_COUNTRY_CODE))


def _format_international(digits: str) -> str:
    """`201012345678` → `+20 10 1234 5678` (Egyptian mobiles); anything else → `+digits`."""
    if digits.startswith("20") and len(digits) == 12:
        return f"+20 {digits[2:4]} {digits[4:8]} {digits[8:]}"
    return f"+{digits}"


_PHONE_SHAPE = re.compile(r"\+?[0-9\s().\-]+")
_WA_LINK = re.compile(r"(?:https://)?(?:www\.)?wa\.me/\+?([0-9]{8,15})(?:[/?#].*)?", re.IGNORECASE)


def _normalise_whatsapp(raw: object) -> Resolved:
    bad = ChannelError(
        "invalid_whatsapp",
        "رقم واتساب غير صالح — مثال: 01012345678 أو +201012345678",
        "Invalid WhatsApp number — for example 01012345678 or +201012345678",
    )
    text = _clean_text(raw, strip_format=True, limit=MAX_VALUE_LENGTH).translate(_DIGITS)
    if not text:
        raise _REQUIRED

    # Pasting the wa.me link itself is common — take the number, rebuild the link
    link = _WA_LINK.fullmatch(text)
    if link:
        digits = link.group(1)
    else:
        if not _PHONE_SHAPE.fullmatch(text):
            raise bad
        digits = re.sub(r"\D", "", text)
        if text.startswith("+"):
            pass  # already international
        elif digits.startswith("00"):
            digits = digits[2:]
        elif digits.startswith("0"):
            digits = _country_code() + digits[1:]

        # `+20 0101…` — the trunk zero typed after the country code. Dialled as written
        # it reaches nobody, so it is dropped (a national number is 10 digits without it).
        code = _country_code()
        if digits.startswith(code + "0") and len(digits) == len(code) + 11:
            digits = code + digits[len(code) + 1 :]

    # E.164: at most 15 digits, no leading zero. Eight is the shortest real number.
    if not 8 <= len(digits) <= 15 or digits.startswith("0"):
        raise bad

    return Resolved(
        value=digits, display=_format_international(digits), href=f"https://wa.me/{digits}"
    )


def _normalise_phone(raw: object) -> Resolved:
    bad = ChannelError(
        "invalid_phone",
        "رقم هاتف غير صالح — أرقام فقط، ويجوز + في البداية",
        "Invalid phone number — digits only, with an optional leading +",
    )
    text = _clean_text(raw, strip_format=True, limit=MAX_VALUE_LENGTH).translate(_DIGITS)
    if not text:
        raise _REQUIRED
    if not _PHONE_SHAPE.fullmatch(text):
        raise bad

    digits = re.sub(r"\D", "", text)
    international = text.startswith("+")
    if not international and digits.startswith("00"):
        digits, international = digits[2:], True

    # Three digits is the shortest real number (emergency lines); fifteen is the E.164 ceiling.
    # ⚠️  A leading zero stays: `0221234567` is a local number and `tel:` dials it as typed.
    if not 3 <= len(digits) <= 15:
        raise bad

    value = ("+" if international else "") + digits
    display = _format_international(digits) if international else digits
    return Resolved(value=value, display=display, href=f"tel:{value}")


# ── Email ──────────────────────────────────────────────────

# ⚠️  Stricter than `validate_email`, which accepts `?` `&` `=` in the local part:
#     `x?cc=someone@host` is a *valid address* to Django and a `mailto:` link that
#     silently copies a third party to every message the customer sends.
_EMAIL_LOCAL = re.compile(r"[A-Za-z0-9._%+\-]+")


def _normalise_email(raw: object) -> Resolved:
    bad = ChannelError("invalid_email", "بريد إلكتروني غير صالح", "Invalid email address")
    text = _clean_text(raw, limit=MAX_VALUE_LENGTH).lower()
    if not text:
        raise _REQUIRED
    if text.startswith("mailto:"):
        text = text[len("mailto:") :]

    try:
        validate_email(text)
    except DjangoValidationError as error:
        raise bad from error

    local = text.rsplit("@", 1)[0]
    if not _EMAIL_LOCAL.fullmatch(local):
        raise bad

    return Resolved(value=text, display=text, href=f"mailto:{quote(text, safe='@')}")


# ── Telegram ───────────────────────────────────────────────

_TG_URL = re.compile(r"(?:https://)?(?:www\.)?(?:t|telegram)\.me/(.+)", re.IGNORECASE)
_TG_USERNAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{4,31}")
_TG_INVITE = re.compile(r"\+[A-Za-z0-9_\-]{6,64}")
_TG_JOINCHAT = re.compile(r"joinchat/([A-Za-z0-9_\-]{6,64})")


def _normalise_telegram(raw: object) -> Resolved:
    bad = ChannelError(
        "invalid_telegram",
        "معرّف تيليجرام غير صالح — مثال: @username أو t.me/username",
        "Invalid Telegram handle — for example @username or t.me/username",
    )
    text = _clean_text(raw, limit=MAX_VALUE_LENGTH)
    if not text:
        raise _REQUIRED

    if text.lower().startswith("http://"):
        raise _HTTPS

    link = _TG_URL.fullmatch(text)
    if link:
        # `t.me/name?start=x#y` — only the first path piece identifies the account
        path = re.split(r"[?#]", link.group(1))[0].rstrip("/")
    elif "://" in text or ":" in text or "/" in text or "\\" in text:
        raise bad
    else:
        path = text.removeprefix("@")

    if _TG_USERNAME.fullmatch(path):
        return Resolved(value=f"@{path}", display=f"@{path}", href=f"https://t.me/{path}")

    if _TG_INVITE.fullmatch(path):
        return Resolved(
            value=f"https://t.me/{path}", display=f"t.me/{path}", href=f"https://t.me/{path}"
        )

    joined = _TG_JOINCHAT.fullmatch(path)
    if joined:
        url = f"https://t.me/joinchat/{joined.group(1)}"
        return Resolved(value=url, display=url.removeprefix("https://"), href=url)

    raise bad


# ── Social networks ────────────────────────────────────────


@dataclass(frozen=True)
class _Social:
    hosts: tuple[str, ...]  # the domains a pasted URL may belong to
    handle: re.Pattern[str]  # what a bare handle looks like
    template: str  # where a bare handle lives
    #: How to read a handle back out of a URL, for display:
    #:   "first" — the first path piece (`instagram.com/store`)
    #:   "at"    — a first path piece starting with `@` (`tiktok.com/@store`)
    #:   "add"   — `snapchat.com/add/store`
    #:   "path"  — no handle convention: show `host/path` instead
    display: str


_SOCIAL: dict[str, _Social] = {
    "FACEBOOK": _Social(
        ("facebook.com", "fb.com", "fb.me"),
        re.compile(r"[A-Za-z0-9.\-]{1,100}"),
        "https://www.facebook.com/{h}",
        "first",
    ),
    "INSTAGRAM": _Social(
        ("instagram.com",),
        re.compile(r"[A-Za-z0-9._]{1,30}"),
        "https://www.instagram.com/{h}",
        "first",
    ),
    "TIKTOK": _Social(
        ("tiktok.com",),
        re.compile(r"[A-Za-z0-9._]{1,24}"),
        "https://www.tiktok.com/@{h}",
        "at",
    ),
    "YOUTUBE": _Social(
        ("youtube.com", "youtu.be"),
        re.compile(r"[A-Za-z0-9._\-]{3,30}"),
        "https://www.youtube.com/@{h}",
        "at",
    ),
    "X": _Social(
        ("x.com", "twitter.com"),
        re.compile(r"[A-Za-z0-9_]{1,15}"),
        "https://x.com/{h}",
        "first",
    ),
    "SNAPCHAT": _Social(
        ("snapchat.com",),
        re.compile(r"[A-Za-z0-9._\-]{3,15}"),
        "https://www.snapchat.com/add/{h}",
        "add",
    ),
    # ⚠️  A bare LinkedIn handle is taken as a *company page* (a store, not a person);
    #     a personal profile needs its full `/in/…` URL.
    "LINKEDIN": _Social(
        ("linkedin.com",),
        re.compile(r"[A-Za-z0-9_%\-]{3,100}"),
        "https://www.linkedin.com/company/{h}",
        "path",
    ),
}

#: First path pieces that are content, not an account
_NOT_A_HANDLE = frozenset(
    {"profile.php", "pages", "groups", "people", "p", "share", "watch", "reel", "reels"}
    | {"explore", "stories", "hashtag", "intent", "i", "sharer", "sharer.php"}
)

_HOST_SHAPE = re.compile(r"[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?)+")


def _host_matches(host: str, domain: str) -> bool:
    """`m.facebook.com` and `facebook.com` match `facebook.com`; `notfacebook.com` does not."""
    return host == domain or host.endswith("." + domain)


def _looks_like_url(text: str, spec: _Social) -> bool:
    """
    A URL (with or without its scheme) versus a bare handle.

    ⚠️  `instagram.com/store` is a URL and `x.company` is a handle, so a handle is never
        mistaken for a host just because it *starts* with one — the host must be followed
        by a path or end the string.
    """
    lowered = text.lower()
    if "://" in lowered or lowered.startswith("//"):
        return True
    lowered = re.sub(r"^(?:www|m|mobile)\.", "", lowered)
    return any(
        lowered == host or lowered.startswith((host + "/", host + "?")) for host in spec.hosts
    )


def _display_url(url: str) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").removeprefix("www.")
    return (host + parts.path).rstrip("/")


def _social_display(spec: _Social, url: str) -> str:
    """`@store` when the URL carries a handle we can recognise; `host/path` otherwise."""
    segments = [segment for segment in urlsplit(url).path.split("/") if segment]

    if segments:
        first = segments[0]
        if spec.display == "at" and first.startswith("@") and spec.handle.fullmatch(first[1:]):
            return first
        if (
            spec.display == "add"
            and len(segments) >= 2
            and first == "add"
            and spec.handle.fullmatch(segments[1])
        ):
            return f"@{segments[1]}"
        if (
            spec.display == "first"
            and first.lower() not in _NOT_A_HANDLE
            and spec.handle.fullmatch(first)
        ):
            return f"@{first}"

    return _display_url(url)


def _normalise_social(kind: str, raw: object) -> Resolved:
    spec = _SOCIAL[kind]
    bad_handle = ChannelError(
        "invalid_handle",
        "اسم الحساب غير صالح — اكتب @اسم_الحساب أو الرابط الكامل",
        "Invalid account name — type @handle or the full link",
    )
    text = _clean_text(raw, limit=MAX_VALUE_LENGTH)
    if not text:
        raise _REQUIRED
    if text.lower().startswith(("http://", "javascript:", "data:", "vbscript:")):
        raise _HTTPS
    if any(ch.isspace() for ch in text) or "\\" in text:
        raise _URL

    if _looks_like_url(text, spec):
        candidate = text
        if candidate.startswith("//"):
            raise _HTTPS  # protocol-relative
        if "://" not in candidate:
            candidate = "https://" + candidate
        elif not candidate.lower().startswith("https://"):
            raise _HTTPS

        try:
            parts = urlsplit(candidate)
            port = parts.port
        except ValueError as error:
            raise _URL from error

        host = (parts.hostname or "").lower()
        if "@" in parts.netloc or port is not None or not _HOST_SHAPE.fullmatch(host):
            raise _URL
        if not any(_host_matches(host, domain) for domain in spec.hosts):
            raise _WRONG_HOST
        if not [segment for segment in parts.path.split("/") if segment]:
            raise _URL  # the platform's home page is not the store's page

        url = f"https://{host}{parts.path}" + (f"?{parts.query}" if parts.query else "")
        if len(url) > MAX_VALUE_LENGTH:
            raise _TOO_LONG
        return Resolved(value=url, display=_social_display(spec, url), href=url)

    handle = text.removeprefix("@")
    if not spec.handle.fullmatch(handle):
        raise bad_handle
    url = spec.template.format(h=handle)
    return Resolved(value=url, display=_social_display(spec, url), href=url)


# ── Plain links ────────────────────────────────────────────

_https_validator = URLValidator(schemes=["https"])


def _normalise_link(raw: object) -> Resolved:
    text = _clean_text(raw, limit=MAX_VALUE_LENGTH)
    if not text:
        raise _REQUIRED
    if not text.lower().startswith("https://"):
        raise _HTTPS  # also catches `http:`, `javascript:`, `data:` and `//host`
    if any(ch.isspace() for ch in text) or "\\" in text:
        raise _URL

    try:
        parts = urlsplit(text)
        parts.port  # noqa: B018 — raises ValueError on a malformed port
        _https_validator(text)
    except (ValueError, DjangoValidationError) as error:
        raise _URL from error

    # ⚠️  `https://trusted.example@evil.example/` shows the first host and goes to the second.
    if "@" in parts.netloc or not parts.hostname:
        raise _URL

    canonical = "https://" + text[len("https://") :]  # `HTTPS://` → `https://`
    return Resolved(value=canonical, display=_display_url(canonical), href=canonical)


# ═══════════════════════════════════════════════════════════
#  The registry
# ═══════════════════════════════════════════════════════════

#: Each kind → its parser. The keys must equal `models.ChannelKind` (a test pins it).
HANDLERS = {
    "WHATSAPP": _normalise_whatsapp,
    "TELEGRAM": _normalise_telegram,
    "PHONE": _normalise_phone,
    "EMAIL": _normalise_email,
    "WEBSITE": _normalise_link,
    "MAP": _normalise_link,
    "OTHER": _normalise_link,
    **{kind: (lambda raw, _kind=kind: _normalise_social(_kind, raw)) for kind in _SOCIAL},
}

#: Shown when the admin leaves the label empty — `(arabic, english)`
DEFAULT_LABELS: dict[str, tuple[str, str]] = {
    "WHATSAPP": ("واتساب", "WhatsApp"),
    "TELEGRAM": ("تيليجرام", "Telegram"),
    "PHONE": ("اتصل بنا", "Call us"),
    "EMAIL": ("البريد الإلكتروني", "Email"),
    "FACEBOOK": ("فيسبوك", "Facebook"),
    "INSTAGRAM": ("إنستجرام", "Instagram"),
    "TIKTOK": ("تيك توك", "TikTok"),
    "YOUTUBE": ("يوتيوب", "YouTube"),
    "X": ("إكس", "X"),
    "SNAPCHAT": ("سناب شات", "Snapchat"),
    "LINKEDIN": ("لينكدإن", "LinkedIn"),
    "WEBSITE": ("الموقع الإلكتروني", "Website"),
    "MAP": ("موقعنا على الخريطة", "Find us on the map"),
    "OTHER": ("رابط", "Link"),
}


def normalise(kind: str, raw: object) -> Resolved:
    """Parse one value. Raises `ChannelError`."""
    handler = HANDLERS.get(kind)
    if handler is None:
        raise ChannelError("invalid_kind", "نوع القناة غير معروف", "Unknown channel type")
    return handler(raw)


def whatsapp_link(href: str, message: str) -> str:
    """`https://wa.me/<digits>` + the prefilled text, percent-encoded."""
    return f"{href}?text={quote(message, safe='')}" if message else href


def describe(kind: str, value: str, message_ar: str = "", message_en: str = "") -> dict:
    """
    The computed, public half of a channel: display text and the links.

    ⚠️  `href` carries the Arabic message and `href_en` the English one — a visitor
        reading the page in English should not open WhatsApp with Arabic already typed.
        Each falls back to the other so a single message still works in both.
    """
    resolved = normalise(kind, value)
    href, href_en = resolved.href, resolved.href

    if kind == "WHATSAPP":
        ar = message_ar or message_en
        en = message_en or message_ar
        href, href_en = whatsapp_link(resolved.href, ar), whatsapp_link(resolved.href, en)

    return {"value": resolved.value, "display": resolved.display, "href": href, "href_en": href_en}


def resolve_label(kind: str, label_ar: str, label_en: str) -> dict[str, str]:
    default_ar, default_en = DEFAULT_LABELS.get(kind, ("", ""))
    return {"ar": label_ar or default_ar, "en": label_en or default_en}


def clean_channel(
    *,
    kind: str,
    value: object,
    label_ar: object = "",
    label_en: object = "",
    message_ar: object = "",
    message_en: object = "",
    show_floating_button: bool = False,
) -> dict:
    """
    Validate and normalise every user-typed field of one channel.

    Returns the cleaned values to store. Raises `ChannelValidationError` carrying **all** the
    refused fields at once — the admin fixes them in one pass instead of one per save.
    """
    errors: dict[str, ChannelError] = {}
    cleaned: dict = {}

    try:
        cleaned["value"] = normalise(kind, value).value
    except ChannelError as error:
        errors["kind" if error.code == "invalid_kind" else "value"] = error

    for field, raw, limit in (
        ("label_ar", label_ar, MAX_LABEL_LENGTH),
        ("label_en", label_en, MAX_LABEL_LENGTH),
        ("message_ar", message_ar, MAX_MESSAGE_LENGTH),
        ("message_en", message_en, MAX_MESSAGE_LENGTH),
    ):
        try:
            # A prefilled message may span lines; a label may not
            cleaned[field] = _clean_text(
                raw, allow_newline=field.startswith("message"), limit=limit
            )
        except ChannelError as error:
            errors[field] = error

    if errors:
        raise ChannelValidationError(errors)

    # ⚠️  The message and the floating button only mean something for WhatsApp.
    #     Keeping them on a Telegram row would be hidden state the admin cannot see.
    if kind != "WHATSAPP":
        cleaned["message_ar"] = cleaned["message_en"] = ""
        cleaned["show_floating_button"] = False
    else:
        cleaned["show_floating_button"] = bool(show_floating_button)

    return cleaned
