"""
Contact channel normalisation — the parser every stored link passes through.

⚠️  Table-driven on purpose: each row is one input a real admin (or a hostile one) types,
    and the table is the specification. Adding a case is one line.

    No database here — `branding.channels` is pure, which is also why it can be trusted
    to run on every write path (API · Django admin · seed · shell).
"""

import pytest

from branding import channels
from branding.models import ChannelKind


def _value(kind: str, raw: str) -> str:
    return channels.normalise(kind, raw).value


def _code(kind: str, raw: str) -> str:
    with pytest.raises(channels.ChannelError) as caught:
        channels.normalise(kind, raw)
    return caught.value.code


def test_every_kind_has_a_parser_and_a_default_label():
    """A kind added to the model without a parser would 500 on save instead of validating."""
    kinds = {choice.value for choice in ChannelKind}
    assert set(channels.HANDLERS) == kinds
    assert set(channels.DEFAULT_LABELS) == kinds


# ═══════════════════════════════════════════════════════════
#  WhatsApp
# ═══════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("raw", "digits"),
    [
        ("01012345678", "201012345678"),  # Egyptian local number
        ("+201012345678", "201012345678"),
        ("+20 101 234 5678", "201012345678"),
        ("0020 101-234-5678", "201012345678"),  # 00 international prefix, dashes
        ("201012345678", "201012345678"),
        ("(010) 1234 5678", "201012345678"),
        ("٠١٠١٢٣٤٥٦٧٨", "201012345678"),  # Arabic-Indic digits from the Arabic keyboard
        ("‪+20 101 234 5678‬", "201012345678"),  # bidi marks dragged in by a paste
        ("+2001012345678", "201012345678"),  # trunk zero typed after the country code
        ("+971 50 123 4567", "971501234567"),  # another country keeps its own code
        ("https://wa.me/201012345678", "201012345678"),  # the link itself pasted
        ("wa.me/201012345678?text=hello", "201012345678"),
    ],
)
def test_whatsapp_numbers_become_international_digits(raw, digits):
    resolved = channels.normalise("WHATSAPP", raw)
    assert resolved.value == digits
    assert resolved.href == f"https://wa.me/{digits}"


def test_whatsapp_display_is_a_readable_number():
    assert channels.normalise("WHATSAPP", "01012345678").display == "+20 10 1234 5678"
    assert channels.normalise("WHATSAPP", "+971501234567").display == "+971501234567"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "abc",
        "010123",  # too short even once the country code is added
        "+0101234567890",  # a leading zero is never a country code
        "+1234567890123456",  # 16 digits: past E.164
        "01012345678; DROP TABLE",
        "javascript:alert(1)",
        "https://evil.example/201012345678",
        "0101234\n5678",  # a newline inside the number
    ],
)
def test_whatsapp_rejects(raw):
    with pytest.raises(channels.ChannelError):
        channels.normalise("WHATSAPP", raw)


def test_whatsapp_link_carries_an_urlencoded_message():
    href = channels.describe("WHATSAPP", "01012345678", "مرحبا & أهلا", "Hi & welcome")
    assert href["href"] == "https://wa.me/201012345678?text=" + (
        "%D9%85%D8%B1%D8%AD%D8%A8%D8%A7%20%26%20%D8%A3%D9%87%D9%84%D8%A7"
    )
    assert href["href_en"] == "https://wa.me/201012345678?text=Hi%20%26%20welcome"


def test_whatsapp_one_message_serves_both_languages():
    described = channels.describe("WHATSAPP", "01012345678", "", "Hello")
    assert described["href"] == described["href_en"] == "https://wa.me/201012345678?text=Hello"


def test_whatsapp_without_a_message_has_a_bare_link():
    assert channels.describe("WHATSAPP", "01012345678")["href"] == "https://wa.me/201012345678"


def test_a_message_cannot_break_out_of_the_query_string():
    href = channels.describe("WHATSAPP", "01012345678", "a&phone=1#frag?x=y\n")["href"]
    assert href.count("?") == 1
    assert "&" not in href and "#" not in href


# ═══════════════════════════════════════════════════════════
#  Telegram
# ═══════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "raw",
    [
        "@mystore",
        "mystore",
        "t.me/mystore",
        "https://t.me/mystore",
        "https://www.t.me/mystore/",
        "https://telegram.me/mystore",
        "https://t.me/mystore?start=abc",
    ],
)
def test_telegram_accepts_every_common_shape(raw):
    resolved = channels.normalise("TELEGRAM", raw)
    assert resolved.value == "@mystore"
    assert resolved.display == "@mystore"
    assert resolved.href == "https://t.me/mystore"


def test_telegram_invite_links_are_kept():
    resolved = channels.normalise("TELEGRAM", "t.me/+AbCdEf123456")
    assert resolved.href == "https://t.me/+AbCdEf123456"
    assert resolved.value == "https://t.me/+AbCdEf123456"
    assert channels.normalise("TELEGRAM", "https://t.me/joinchat/AbCdEf123456").href.endswith(
        "joinchat/AbCdEf123456"
    )


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "ab",  # shorter than Telegram's five characters
        "1abcdef",  # must start with a letter
        "my store",
        "http://t.me/mystore",
        "https://evil.example/mystore",
        "https://t.me.evil.example/mystore",
        "javascript:alert(1)",
        "//t.me/mystore",
        "t.me/mystore/123",
        "@my-store",
    ],
)
def test_telegram_rejects(raw):
    with pytest.raises(channels.ChannelError):
        channels.normalise("TELEGRAM", raw)


# ═══════════════════════════════════════════════════════════
#  Phone and email
# ═══════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("raw", "value", "href"),
    [
        ("0221234567", "0221234567", "tel:0221234567"),
        ("02 2123-4567", "0221234567", "tel:0221234567"),
        ("+20 2 2123 4567", "+20221234567", "tel:+20221234567"),
        ("0020 2 2123 4567", "+20221234567", "tel:+20221234567"),
        ("19123", "19123", "tel:19123"),  # a five-digit hotline
        ("٠٢٢١٢٣٤٥٦٧", "0221234567", "tel:0221234567"),
    ],
)
def test_phone_keeps_digits_and_a_leading_plus(raw, value, href):
    resolved = channels.normalise("PHONE", raw)
    assert (resolved.value, resolved.href) == (value, href)


@pytest.mark.parametrize(
    "raw",
    ["", "12", "12+34", "call me", "tel:0221234567", "+" + "1" * 16, "0221234567;ext=1", "02\n21"],
)
def test_phone_rejects(raw):
    with pytest.raises(channels.ChannelError):
        channels.normalise("PHONE", raw)


def test_email_is_lowercased_and_linked():
    resolved = channels.normalise("EMAIL", "  Support@Example.COM ")
    assert resolved.value == "support@example.com"
    assert resolved.href == "mailto:support@example.com"
    assert channels.normalise("EMAIL", "mailto:a@b.co").value == "a@b.co"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "nope",
        "a@b",
        "x?cc=someone@example.com",  # valid to Django, a header-injecting mailto here
        "a&b@example.com",
        "a b@example.com",
        "a@example.com,b@example.com",
        "a@example.com\nBcc: x@y.z",
        '"quoted"@example.com',
    ],
)
def test_email_rejects(raw):
    with pytest.raises(channels.ChannelError):
        channels.normalise("EMAIL", raw)


# ═══════════════════════════════════════════════════════════
#  Social networks
# ═══════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("kind", "raw", "href", "display"),
    [
        ("INSTAGRAM", "@mystore", "https://www.instagram.com/mystore", "@mystore"),
        ("INSTAGRAM", "mystore", "https://www.instagram.com/mystore", "@mystore"),
        (
            "INSTAGRAM",
            "https://www.instagram.com/mystore/",
            "https://www.instagram.com/mystore/",
            "@mystore",
        ),
        ("INSTAGRAM", "instagram.com/mystore", "https://instagram.com/mystore", "@mystore"),
        ("FACEBOOK", "my.store", "https://www.facebook.com/my.store", "@my.store"),
        (
            "FACEBOOK",
            "https://m.facebook.com/my.store",
            "https://m.facebook.com/my.store",
            "@my.store",
        ),
        ("FACEBOOK", "https://fb.me/mystore", "https://fb.me/mystore", "@mystore"),
        ("TIKTOK", "@mystore", "https://www.tiktok.com/@mystore", "@mystore"),
        (
            "TIKTOK",
            "https://www.tiktok.com/@mystore?lang=ar",
            "https://www.tiktok.com/@mystore?lang=ar",
            "@mystore",
        ),
        ("YOUTUBE", "@mychannel", "https://www.youtube.com/@mychannel", "@mychannel"),
        (
            "YOUTUBE",
            "https://www.youtube.com/channel/UCabcdef",
            "https://www.youtube.com/channel/UCabcdef",
            "youtube.com/channel/UCabcdef",
        ),
        ("X", "@mystore", "https://x.com/mystore", "@mystore"),
        ("X", "https://twitter.com/mystore", "https://twitter.com/mystore", "@mystore"),
        ("SNAPCHAT", "@mystore", "https://www.snapchat.com/add/mystore", "@mystore"),
        (
            "LINKEDIN",
            "mystore",
            "https://www.linkedin.com/company/mystore",
            "linkedin.com/company/mystore",
        ),
        (
            "LINKEDIN",
            "https://www.linkedin.com/in/jane-doe",
            "https://www.linkedin.com/in/jane-doe",
            "linkedin.com/in/jane-doe",
        ),
    ],
)
def test_social_kinds_accept_a_handle_or_a_url(kind, raw, href, display):
    resolved = channels.normalise(kind, raw)
    assert resolved.href == href
    assert resolved.display == display
    assert resolved.value == href


@pytest.mark.parametrize(
    ("kind", "raw", "code"),
    [
        ("INSTAGRAM", "http://www.instagram.com/mystore", "https_required"),
        ("INSTAGRAM", "javascript:alert(1)", "https_required"),
        ("INSTAGRAM", "//www.instagram.com/mystore", "https_required"),
        ("INSTAGRAM", "https://evil.example/instagram.com/mystore", "wrong_host"),
        ("INSTAGRAM", "https://notinstagram.com/mystore", "wrong_host"),
        ("INSTAGRAM", "https://instagram.com.evil.example/mystore", "wrong_host"),
        ("INSTAGRAM", "https://www.instagram.com@evil.example/mystore", "invalid_url"),
        ("INSTAGRAM", "https://www.instagram.com", "invalid_url"),  # the home page is no profile
        ("INSTAGRAM", "https://www.instagram.com:8443/mystore", "invalid_url"),
        ("INSTAGRAM", "https://www.instagram.com/my store", "invalid_url"),
        ("INSTAGRAM", "https://www.instagram.com\\@evil.example/x", "invalid_url"),
        ("INSTAGRAM", "my store!", "invalid_url"),
        ("INSTAGRAM", "bad/handle", "invalid_handle"),
        ("FACEBOOK", "ftp://facebook.com/x", "https_required"),
        ("TIKTOK", "x" * 25, "invalid_handle"),
        ("X", "toolonghandle_over_15", "invalid_handle"),
        ("INSTAGRAM", "", "required"),
    ],
)
def test_social_kinds_reject(kind, raw, code):
    assert _code(kind, raw) == code


# ═══════════════════════════════════════════════════════════
#  Plain links
# ═══════════════════════════════════════════════════════════


@pytest.mark.parametrize("kind", ["WEBSITE", "MAP", "OTHER"])
def test_plain_links_accept_https(kind):
    resolved = channels.normalise(kind, "https://www.example.com/a/b?c=d")
    assert resolved.href == resolved.value == "https://www.example.com/a/b?c=d"
    assert resolved.display == "example.com/a/b"
    assert channels.normalise(kind, "HTTPS://Example.com/").value == "https://Example.com/"


@pytest.mark.parametrize("kind", ["WEBSITE", "MAP", "OTHER"])
@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("javascript:alert(1)", "https_required"),
        ("JaVaScRiPt:alert(1)", "https_required"),
        ("data:text/html;base64,PHNjcmlwdD4=", "https_required"),
        ("vbscript:msgbox(1)", "https_required"),
        ("//evil.example/x", "https_required"),
        ("http://example.com", "https_required"),
        ("ftp://example.com", "https_required"),
        ("example.com", "https_required"),
        ("https://trusted.example@evil.example/", "invalid_url"),
        ("https://user:pass@example.com/", "invalid_url"),
        ("https://example.com/a b", "invalid_url"),
        ("https://exa mple.com", "invalid_url"),
        ("https://example.com\\@evil.example", "invalid_url"),
        ("https://", "invalid_url"),
        ("https://exa\tmple.com", "control_chars"),
        ("https://example.com/\x00", "control_chars"),
        ("https://example.com/‮", "control_chars"),  # right-to-left override
        ("https://example.com/​", "control_chars"),  # zero-width space
        ("", "required"),
    ],
)
def test_plain_links_reject(kind, raw, code):
    assert _code(kind, raw) == code


@pytest.mark.parametrize("kind", [choice.value for choice in ChannelKind])
def test_every_kind_refuses_an_over_long_value(kind):
    assert _code(kind, "https://example.com/" + "a" * 400) in {
        "too_long",
        "invalid_whatsapp",
        "invalid_phone",
        "invalid_email",
        "invalid_telegram",
        "invalid_handle",
        "invalid_url",
    }
    assert _code(kind, "a" * 5000) == "too_long"


# ═══════════════════════════════════════════════════════════
#  Idempotence and the whole-channel cleaner
# ═══════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("kind", "raw"),
    [
        ("WHATSAPP", "01012345678"),
        ("TELEGRAM", "t.me/mystore"),
        ("TELEGRAM", "t.me/+AbCdEf123456"),
        ("PHONE", "0020 2 2123 4567"),
        ("PHONE", "0221234567"),
        ("EMAIL", "Support@Example.com"),
        ("INSTAGRAM", "@mystore"),
        ("TIKTOK", "tiktok.com/@mystore"),
        ("LINKEDIN", "mystore"),
        ("WEBSITE", "HTTPS://example.com/x"),
    ],
)
def test_normalising_twice_changes_nothing(kind, raw):
    """`save()` normalises on every write — a stored row must survive being saved again."""
    once = channels.normalise(kind, raw)
    assert channels.normalise(kind, once.value) == once


def test_clean_channel_reports_every_bad_field_at_once():
    with pytest.raises(channels.ChannelValidationError) as caught:
        channels.clean_channel(
            kind="TELEGRAM", value="no spaces", label_ar="x" * 61, message_en="ok"
        )
    assert set(caught.value.errors) == {"value", "label_ar"}
    assert caught.value.errors["label_ar"].code == "too_long"


def test_clean_channel_drops_whatsapp_only_fields_from_other_kinds():
    cleaned = channels.clean_channel(
        kind="TELEGRAM",
        value="@mystore",
        message_ar="مرحبا",
        message_en="Hello",
        show_floating_button=True,
    )
    assert cleaned["message_ar"] == cleaned["message_en"] == ""
    assert cleaned["show_floating_button"] is False


def test_a_label_may_not_span_lines_but_a_message_may():
    with pytest.raises(channels.ChannelValidationError):
        channels.clean_channel(kind="WHATSAPP", value="01012345678", label_en="a\nb")
    cleaned = channels.clean_channel(kind="WHATSAPP", value="01012345678", message_en="a\nb")
    assert cleaned["message_en"] == "a\nb"


def test_unknown_kind_is_a_kind_error():
    with pytest.raises(channels.ChannelValidationError) as caught:
        channels.clean_channel(kind="MYSPACE", value="x")
    assert set(caught.value.errors) == {"kind"}


def test_errors_are_bilingual():
    with pytest.raises(channels.ChannelError) as caught:
        channels.normalise("WHATSAPP", "abc")
    assert "—" in caught.value.message
    assert any("؀" <= ch <= "ۿ" for ch in caught.value.message)
    assert "Invalid" in caught.value.message


def test_default_labels_are_used_unless_overridden():
    assert channels.resolve_label("WHATSAPP", "", "") == {"ar": "واتساب", "en": "WhatsApp"}
    assert channels.resolve_label("WHATSAPP", "اطلب الآن", "") == {
        "ar": "اطلب الآن",
        "en": "WhatsApp",
    }
