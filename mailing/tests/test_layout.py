"""
The branded HTML layout.

⚠️  **Three properties, in the order a failure would hurt:**

    1. It is never the reason a message is lost — a broken logo, a database hiccup in the
       identity lookup, a malformed provider: the text still goes out.
    2. Nothing the sender typed reaches the markup unescaped — the body of a manual reply,
       a customer's name interpolated into a template, an admin-edited store name.
    3. It covers every path that sends mail, because it hangs off the delivery
       (`services._attempt`), not off the templates.

⚠️  The identity comes through `settings.MAIL_BRAND_PROVIDER` (a dotted path), because
    `mailing` cannot import `branding`. Most tests install a fake provider here; one test
    exercises the real default through `apps.get_model`, for the same layering reason.
"""

import io

import pytest
from django.apps import apps
from django.core import mail as django_mail
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.mail import EmailMultiAlternatives
from django.urls import reverse
from rest_framework.test import APIClient

from conftest import real_png_bytes
from core.files import ALLOWED_IMAGE_TYPES
from core.testing import grant_all_domains
from mailing import layout, services
from mailing.models import DeliveryState, OutboundMessage

PASSWORD = "Str0ng-Test-Pass!23"

#: Mutated per test; the fake provider below reads it
IDENTITY: dict = {}


def fake_identity() -> dict:
    return IDENTITY


def failing_identity() -> dict:
    raise RuntimeError("قاعدة البيانات غير متاحة")


@pytest.fixture(autouse=True)
def identity(settings):
    """A known store identity, and an empty logo cache, for every test."""
    cache.clear()
    IDENTITY.clear()
    IDENTITY.update(
        {
            "name": {"ar": "متجر الاختبار", "en": "Test Store"},
            "color": "#0b5394",
            "logo": {},
            "contact": {
                "email": "hello@store.example",
                "phone": "+20 100 123 4567",
                "address": {"ar": "القاهرة، مصر", "en": "Cairo, Egypt"},
            },
        }
    )
    settings.MAIL_BRAND_PROVIDER = "mailing.tests.test_layout.fake_identity"
    settings.MEDIA_ORIGIN = "https://api.store.example"
    settings.SITE_ORIGIN = "https://store.example"
    return IDENTITY


@pytest.fixture
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


def store_logo(name="branding/logo.png", *, size=(600, 200), fmt="PNG", mode="RGBA") -> str:
    """Put a real image into the (temporary) media storage and point the identity at it."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new(mode, size, (200, 30, 30, 255) if mode == "RGBA" else (200, 30, 30)).save(
        buffer, format=fmt
    )
    saved = default_storage.save(name, ContentFile(buffer.getvalue()))
    IDENTITY["logo"] = {"name": saved, "url": f"/media/{saved}"}
    return saved


def wrap(body="مرحبًا بك", subject="موضوع", language="ar") -> EmailMultiAlternatives:
    email = EmailMultiAlternatives(subject=subject, body=body, to=["customer@example.com"])
    layout.apply(email, language=language)
    return email


def html_of(email: EmailMultiAlternatives) -> str:
    return next(content for content, mimetype in email.alternatives if mimetype == "text/html")


# ═══════════════════════════════════════════════════════════
#  Delivery
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEveryDeliveryPathIsBranded:
    def _deliver(self, message: OutboundMessage) -> EmailMultiAlternatives:
        django_mail.outbox.clear()
        assert services.deliver(message.pk) is True
        return django_mail.outbox[0]

    def test_a_template_message(self):
        message = services.enqueue(
            "password_changed", to="customer@example.com", language="ar", context={"name": "أحمد"}
        )

        sent = self._deliver(message)

        assert [mimetype for _, mimetype in sent.alternatives] == ["text/html"]
        assert "أحمد" in html_of(sent)

    def test_a_manual_reply(self):
        """A reply written by an employee never touches a template - and is branded all the same."""
        message = services.enqueue_raw(
            to="customer@example.com", subject="Re: طلبك", body="طلبك في الطريق", language="ar"
        )

        sent = self._deliver(message)

        assert "طلبك في الطريق" in html_of(sent)

    def test_the_plain_text_body_is_preserved_verbatim(self):
        """Clients that prefer text, and spam filters that compare the two, get exactly the log."""
        message = services.enqueue_raw(
            to="customer@example.com", subject="s", body="سطر أول\n\nسطر ثانٍ\nhttps://a.example/x"
        )

        sent = self._deliver(message)

        assert sent.body == "سطر أول\n\nسطر ثانٍ\nhttps://a.example/x"
        assert sent.body == OutboundMessage.objects.get(pk=message.pk).body

    def test_threading_headers_survive(self):
        message = services.enqueue_raw(
            to="customer@example.com",
            subject="Re: x",
            body="رد",
            in_reply_to="<orig@client.example>",
            references="<a@client.example> <orig@client.example>",
        )

        sent = self._deliver(message)

        assert sent.extra_headers["In-Reply-To"] == "<orig@client.example>"
        assert sent.extra_headers["References"] == "<a@client.example> <orig@client.example>"
        assert sent.alternatives

    def test_the_message_language_selects_the_direction(self):
        message = services.enqueue_raw(
            to="customer@example.com", subject="s", body="Hello there", language="en"
        )

        sent = self._deliver(message)

        assert '<html lang="en" dir="ltr">' in html_of(sent)

    def test_the_test_message_is_branded_too(self, monkeypatch):
        account = apps.get_model("mailing", "EmailAccount").objects.create(
            code="probe",
            label_ar="تجربة",
            label_en="Probe",
            transport="CONSOLE",
            from_email="noreply@example.com",
        )
        django_mail.outbox.clear()
        monkeypatch.setattr(
            services, "CONSOLE_BACKEND", "django.core.mail.backends.locmem.EmailBackend"
        )

        ok, _ = services.send_test(account, to="admin@example.com")

        assert ok
        assert django_mail.outbox[0].alternatives

    def test_a_failure_in_the_layout_never_loses_the_message(self, monkeypatch):
        """
        ⚠️  An unbranded password reset beats a lost one: whatever `render_html` does, the
            text goes out.
        """

        def explode(**kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(layout, "render_html", explode)
        message = services.enqueue_raw(to="customer@example.com", subject="s", body="مهم جدًا")

        sent = self._deliver(message)

        assert sent.body == "مهم جدًا"
        assert sent.alternatives == []
        assert OutboundMessage.objects.get(pk=message.pk).status == DeliveryState.SENT


class TestNothingToWrap:
    @pytest.mark.parametrize("body", ["", "   ", "\n\n\t\n"])
    def test_a_blank_body_gets_no_html(self, body):
        email = EmailMultiAlternatives(subject="s", body=body, to=["a@example.com"])

        assert layout.apply(email, language="ar") is False
        assert email.alternatives == []

    def test_render_html_returns_none_for_a_blank_body(self):
        assert (
            layout.render_html(subject="s", body="  ", language="ar", brand=layout.MailBrand())
            is None
        )


# ═══════════════════════════════════════════════════════════
#  Escaping
# ═══════════════════════════════════════════════════════════


class TestInjectionIsEscaped:
    def test_markup_in_the_body(self):
        email = wrap(body="<script>alert(1)</script>\n<img src=x onerror=alert(1)>")

        document = html_of(email)

        assert "<script>" not in document
        assert "<img src=x" not in document
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in document

    def test_markup_in_the_subject(self):
        document = html_of(wrap(subject="</title><script>alert(1)</script>"))

        assert "<script>" not in document
        assert "&lt;/title&gt;" in document

    def test_markup_in_every_identity_field(self, identity):
        payload = '"><script>alert(1)</script>'
        identity["name"] = {"ar": payload, "en": payload}
        identity["contact"] = {
            "email": payload,
            "phone": payload,
            "address": {"ar": payload, "en": payload},
        }

        document = html_of(wrap())

        assert "<script>" not in document

    def test_a_hostile_colour_cannot_reach_the_style_attribute(self, identity):
        """The colour lands inside `style=""`; anything but a hex literal is replaced."""
        identity["color"] = "red;background:url(javascript:alert(1))"

        document = html_of(wrap())

        assert "javascript" not in document
        assert layout.DEFAULT_COLOR in document

    def test_a_hostile_logo_url_is_escaped(self, identity):
        identity["logo"] = {"name": "", "url": 'https://x.example/a.png" onerror="alert(1)'}

        document = html_of(wrap())

        assert 'onerror="alert(1)' not in document
        assert "&quot;" in document

    def test_only_http_urls_become_links(self):
        document = html_of(wrap(body="javascript:alert(1)\nhttps://safe.example/path?a=1&b=2"))

        assert 'href="javascript' not in document
        assert '<a href="https://safe.example/path?a=1&amp;b=2"' in document

    def test_a_link_cannot_break_out_of_its_attribute(self):
        document = html_of(wrap(body='https://x.example/a"onmouseover="alert(1)'))

        assert 'onmouseover="alert' not in document

    def test_sentence_punctuation_is_not_part_of_the_link(self):
        document = html_of(wrap(body="افتح https://x.example/reset)."))

        assert 'href="https://x.example/reset"' in document

    def test_an_arabic_word_glued_to_a_link_is_not_swallowed(self):
        document = html_of(wrap(body="https://x.example/abcوبعدها"))

        assert 'href="https://x.example/abc"' in document

    def test_paragraphs_and_line_breaks(self):
        document = html_of(wrap(body="أول\nثانٍ\n\n\nثالث"))

        assert document.count('<p dir="auto"') == 2
        assert "أول<br>ثانٍ" in document


# ═══════════════════════════════════════════════════════════
#  Direction
# ═══════════════════════════════════════════════════════════


class TestDirection:
    def test_arabic_is_right_to_left(self):
        document = html_of(wrap(language="ar"))

        assert '<html lang="ar" dir="rtl">' in document
        assert 'align="right"' in document

    def test_english_is_left_to_right(self):
        document = html_of(wrap(body="Hello", language="en"))

        assert '<html lang="en" dir="ltr">' in document
        assert 'align="left"' in document
        assert "Test Store" in document
        assert "Cairo, Egypt" in document

    def test_an_unknown_language_falls_back_to_arabic(self):
        assert 'dir="rtl"' in html_of(wrap(language="fr"))

    def test_the_phone_number_stays_left_to_right_inside_an_rtl_footer(self):
        document = html_of(wrap(language="ar"))

        assert 'href="tel:+201001234567" dir="ltr"' in document


# ═══════════════════════════════════════════════════════════
#  The logo
# ═══════════════════════════════════════════════════════════


class TestLogo:
    def test_it_is_embedded_by_content_id(self, media):
        store_logo()

        email = wrap()
        raw = email.message().as_string()
        document = html_of(email)

        assert email.mixed_subtype == "related"
        assert "multipart/related" in raw
        assert "Content-ID: <" in raw
        assert "Content-Disposition: inline" in raw

        content_id = raw.split("Content-ID: <", 1)[1].split(">", 1)[0]
        assert f'src="cid:{content_id}"' in document
        assert "https://" not in document.split("<img", 1)[1].split(">", 1)[0]

    def test_the_plain_text_part_is_still_there(self, media):
        store_logo()

        raw = wrap(body="نص صريح").message().as_string()

        assert "text/plain" in raw
        assert "text/html" in raw

    def test_it_is_shrunk_to_twice_the_displayed_size(self, media):
        """A 2 MB upload must not travel with every password reset."""
        from PIL import Image

        store_logo(size=(1800, 600))

        logo = layout.read_logo(layout.load_brand())

        embedded = Image.open(io.BytesIO(logo.data))
        assert embedded.width <= layout.LOGO_EMBED[0]
        assert embedded.height <= layout.LOGO_EMBED[1]
        # 1800x600 -> 336x112 embedded (2x) -> displayed at half of that
        assert (logo.width, logo.height) == (168, 56)

    def test_a_small_logo_is_not_upscaled(self, media):
        store_logo(size=(120, 40))

        logo = layout.read_logo(layout.load_brand())

        assert (logo.width, logo.height) == (120, 40)

    def test_webp_is_sent_as_png(self, media):
        """Outlook and older clients cannot render WebP."""
        store_logo("branding/logo.webp", fmt="WEBP")

        logo = layout.read_logo(layout.load_brand())

        assert logo.subtype == "png"
        assert logo.data.startswith(b"\x89PNG")

    def test_jpeg_stays_jpeg(self, media):
        store_logo("branding/logo.jpg", fmt="JPEG", mode="RGB")

        assert layout.read_logo(layout.load_brand()).subtype == "jpeg"

    def test_an_unreadable_file_falls_back_to_the_absolute_url(self, media, identity):
        identity["logo"] = {"name": "branding/missing.png", "url": "/media/branding/missing.png"}

        email = wrap()

        assert email.attachments == []
        assert email.mixed_subtype == "mixed"
        assert 'src="https://api.store.example/media/branding/missing.png"' in html_of(email)

    def test_a_file_that_is_not_an_image_falls_back_to_the_url(self, media, identity):
        saved = default_storage.save("branding/fake.png", ContentFile(b"not an image"))
        identity["logo"] = {"name": saved, "url": f"/media/{saved}"}

        email = wrap()

        assert email.attachments == []
        assert f"https://api.store.example/media/{saved}" in html_of(email)

    def test_a_cdn_url_is_used_as_it_is(self, media, identity):
        identity["logo"] = {"name": "branding/x.png", "url": "https://cdn.example/x.png"}

        assert 'src="https://cdn.example/x.png"' in html_of(wrap())

    def test_no_logo_shows_the_store_name_as_text(self):
        document = html_of(wrap())

        assert "<img" not in document
        assert "متجر الاختبار" in document

    def test_the_name_follows_the_language(self):
        assert "Test Store" in html_of(wrap(body="Hello", language="en"))

    def test_svg_can_never_be_a_logo(self):
        """
        ⚠️  Gmail does not render SVG, and the upload validator is what guarantees the
            logo is a raster: if SVG were ever allowed there, every embedded logo would
            silently become a blank box in the largest mail client.
        """
        assert "image/svg+xml" not in ALLOWED_IMAGE_TYPES
        assert ALLOWED_IMAGE_TYPES == {"image/jpeg", "image/png", "image/webp"}

        with pytest.raises(OSError):  # PIL.UnidentifiedImageError
            layout._normalise_logo(b"<svg xmlns='http://www.w3.org/2000/svg'></svg>")

    def test_the_read_logo_is_cached_per_file_name(self, media, monkeypatch):
        store_logo()
        brand = layout.load_brand()
        layout.read_logo(brand)

        monkeypatch.setattr(default_storage, "open", lambda *a, **k: pytest.fail("re-read"))

        assert layout.read_logo(brand) is not None


# ═══════════════════════════════════════════════════════════
#  The identity provider
# ═══════════════════════════════════════════════════════════


class TestProvider:
    def test_the_footer_carries_the_contact_details(self):
        document = html_of(wrap())

        assert 'href="mailto:hello@store.example"' in document
        assert "+20 100 123 4567" in document
        assert "القاهرة، مصر" in document
        assert 'href="https://store.example"' in document
        assert "store.example</a>" in document

    def test_the_brand_colour_is_used(self):
        document = html_of(wrap())

        assert "#0b5394" in document

    def test_an_empty_setting_turns_branding_off(self, settings):
        settings.MAIL_BRAND_PROVIDER = ""

        document = html_of(wrap())

        assert "متجر الاختبار" not in document
        assert layout.DEFAULT_COLOR in document

    def test_a_broken_provider_degrades_to_plain_html(self, settings):
        settings.MAIL_BRAND_PROVIDER = "mailing.tests.test_layout.failing_identity"

        email = wrap()

        assert email.alternatives, "a database hiccup must not cost the message its layout"
        assert "متجر الاختبار" not in html_of(email)

    def test_a_missing_provider_path_does_not_raise(self, settings):
        settings.MAIL_BRAND_PROVIDER = "no.such.module.provider"

        assert wrap().alternatives

    @pytest.mark.django_db
    def test_the_default_provider_reads_the_real_active_profile(self, settings):
        """The wiring `settings.MAIL_BRAND_PROVIDER` points at, end to end."""
        settings.MAIL_BRAND_PROVIDER = "branding.services.mail_identity"
        profile_model = apps.get_model("branding", "BrandProfile")
        profile_model.objects.all().delete()
        profile_model.objects.create(
            code="mail-real",
            name_ar="هويّة حقيقية",
            name_en="Real Identity",
            contact_email="real@store.example",
            is_active=True,
        )

        brand = layout.load_brand()

        assert brand.name_ar == "هويّة حقيقية"
        assert brand.email == "real@store.example"
        assert "هويّة حقيقية" in html_of(wrap())


# ═══════════════════════════════════════════════════════════
#  The preview endpoint
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def admin_client(db):
    user_model = apps.get_model("accounts", "User")
    admin = user_model.objects.create_user(
        email="layout-admin@test.local", password=PASSWORD, account_type="ADMIN"
    )
    admin.is_active = True
    admin.save()
    apps.get_model("administration", "AdminProfile").objects.create(user=admin)
    grant_all_domains(admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.mark.django_db
class TestPreviewEndpoint:
    url = "v1:mailing:mail-preview"

    def test_returns_the_branded_html(self, admin_client):
        response = admin_client.post(
            reverse(self.url),
            {"subject": "موضوع", "body": "أهلًا بك", "language": "ar"},
            format="json",
        )

        assert response.status_code == 200
        assert "أهلًا بك" in response.data["html"]
        assert 'dir="rtl"' in response.data["html"]
        assert "متجر الاختبار" in response.data["html"]

    def test_it_is_the_same_renderer_as_delivery(self, admin_client):
        body = "نص\n\nhttps://x.example/y"
        previewed = admin_client.post(
            reverse(self.url), {"subject": "s", "body": body}, format="json"
        ).data["html"]

        assert previewed == layout.preview(subject="s", body=body, language="ar")

    def test_english(self, admin_client):
        response = admin_client.post(
            reverse(self.url), {"body": "Hello", "language": "en"}, format="json"
        )

        assert 'dir="ltr"' in response.data["html"]

    def test_the_logo_is_inlined_as_a_data_uri(self, admin_client, media):
        """`cid:` only resolves inside a real message; the sandboxed iframe gets the bytes."""
        store_logo()

        html = admin_client.post(reverse(self.url), {"body": "نص"}, format="json").data["html"]

        assert 'src="data:image/png;base64,' in html
        assert "cid:" not in html

    def test_the_preview_escapes_what_was_typed(self, admin_client):
        html = admin_client.post(
            reverse(self.url), {"body": "<script>alert(1)</script>"}, format="json"
        ).data["html"]

        assert "<script>" not in html

    def test_a_blank_body_is_refused(self, admin_client):
        response = admin_client.post(reverse(self.url), {"body": "   "}, format="json")

        assert response.status_code == 400

    def test_an_unknown_language_is_refused(self, admin_client):
        response = admin_client.post(
            reverse(self.url), {"body": "x", "language": "fr"}, format="json"
        )

        assert response.status_code == 400

    def test_it_sends_and_stores_nothing(self, admin_client):
        django_mail.outbox.clear()

        admin_client.post(reverse(self.url), {"body": "نص"}, format="json")

        assert django_mail.outbox == []
        assert not OutboundMessage.objects.exists()

    def test_a_customer_is_refused(self):
        user_model = apps.get_model("accounts", "User")
        customer = user_model.objects.create_user(email="shopper@test.local", password=PASSWORD)
        customer.is_active = True
        customer.save()
        client = APIClient()
        client.force_authenticate(user=customer)

        response = client.post(reverse(self.url), {"body": "x"}, format="json")

        assert response.status_code == 403

    def test_an_anonymous_visitor_is_refused(self):
        response = APIClient().post(reverse(self.url), {"body": "x"}, format="json")

        assert response.status_code in (401, 403)


def test_real_png_helper_is_still_a_png():
    """Guards the fixture these tests lean on, so a failure above is not misread."""
    assert real_png_bytes().startswith(b"\x89PNG")
