"""
Uploading identity assets from the panel.

⚠️  **The assets used to have no check at all** while product images were
    checked by signature — a disparity nothing justified. And the logo is more
    dangerous: it is served from the site's own origin and appears on **every**
    page for every visitor.

⚠️  And `apps.get_model`, not `import`: `branding` is forbidden from importing
    any business domain, and the test is part of the package, not an exception to it.
"""

import pytest

from core.testing import grant_all_domains
from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from branding.models import BrandProfile, ThemeMode, ThemePalette
from conftest import real_png_bytes

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


def _model(label: str, name: str):
    return apps.get_model(label, name)


@pytest.fixture
def profile(db):
    profile = BrandProfile.objects.create(
        code="assets", name_ar="متجر", name_en="Store", is_active=True
    )
    for mode in ThemeMode:
        ThemePalette.objects.create(profile=profile, mode=mode)
    return profile


@pytest.fixture
def admin_client(db):
    admin = _model("accounts", "User").objects.create_user(
        email="assets-admin@test.local", password=PASSWORD, account_type="ADMIN"
    )
    admin.is_active = True
    admin.save()
    _model("administration", "AdminProfile").objects.create(user=admin)
    grant_all_domains(admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


def detail_url(profile):
    return reverse("v1:branding:profile-detail", args=[profile.pk])


# ═══════════════════════════════════════════════════════════
#  Uploading
# ═══════════════════════════════════════════════════════════


class TestUpload:
    def test_a_real_image_is_accepted(self, admin_client, profile):
        response = admin_client.patch(
            detail_url(profile),
            {"logo_light": SimpleUploadedFile("logo.png", real_png_bytes(), "image/png")},
            format="multipart",
        )

        assert response.status_code == 200
        profile.refresh_from_db()
        assert profile.logo_light.name

    def test_a_forged_content_type_is_refused(self, admin_client, profile):
        """
        ⚠️  **The check is on the file signature, not on its header.**

            `content_type` comes from the client and is forged in one line. A
            text file carrying an image header used to pass and be served from
            the site's origin — precisely what the signature allowlist blocks.
        """
        response = admin_client.patch(
            detail_url(profile),
            {"logo_light": SimpleUploadedFile("evil.png", b"<svg onload=alert(1)>", "image/png")},
            format="multipart",
        )

        assert response.status_code == 400
        assert "logo_light" in response.data["fields"]

        profile.refresh_from_db()
        assert not profile.logo_light.name

    def test_an_oversized_file_is_refused(self, admin_client, profile):
        """The logo is downloaded on every page by every visitor — a heavy file slows the whole
        site."""
        heavy = real_png_bytes() + b"0" * (3 * 1024 * 1024)

        response = admin_client.patch(
            detail_url(profile),
            {"icon": SimpleUploadedFile("big.png", heavy, "image/png")},
            format="multipart",
        )

        assert response.status_code == 400

    def test_an_empty_file_is_refused(self, admin_client, profile):
        """A zero size passes every content check and is stored as a file that looks fine."""
        response = admin_client.patch(
            detail_url(profile),
            {"favicon": SimpleUploadedFile("empty.png", b"", "image/png")},
            format="multipart",
        )

        assert response.status_code == 400

    @pytest.mark.parametrize("field", ["logo_light", "logo_dark", "icon", "favicon", "og_image"])
    def test_every_asset_field_is_guarded(self, admin_client, profile, field):
        """
        ⚠️  The field forgotten from the check is the hole — and all five are
            uploaded from the same screen with the same button.
        """
        response = admin_client.patch(
            detail_url(profile),
            {field: SimpleUploadedFile("x.png", b"not-an-image-at-all", "image/png")},
            format="multipart",
        )

        assert response.status_code == 400, field


# ═══════════════════════════════════════════════════════════
#  Clearing and permissions
# ═══════════════════════════════════════════════════════════


class TestClearAndPermissions:
    def test_an_asset_can_be_removed(self, admin_client, profile):
        """A logo uploaded by mistake must be correctable from the same screen."""
        admin_client.patch(
            detail_url(profile),
            {"logo_light": SimpleUploadedFile("logo.png", real_png_bytes(), "image/png")},
            format="multipart",
        )

        # ⚠️  JSON with a `null` value, not a form with an empty value: DRF
        #     silently ignores the latter and returns 200 with the image still there.
        response = admin_client.patch(detail_url(profile), {"logo_light": None}, format="json")

        assert response.status_code == 200
        profile.refresh_from_db()
        assert not profile.logo_light.name

    def test_editing_other_fields_leaves_assets_alone(self, admin_client, profile):
        """
        ⚠️  The screen saves only what changed. Saving the name must not erase a
            logo uploaded on another tab.
        """
        admin_client.patch(
            detail_url(profile),
            {"icon": SimpleUploadedFile("icon.png", real_png_bytes(), "image/png")},
            format="multipart",
        )

        admin_client.patch(detail_url(profile), {"name_ar": "اسم جديد"}, format="json")

        profile.refresh_from_db()
        assert profile.name_ar == "اسم جديد"
        assert profile.icon.name

    def test_a_customer_cannot_upload(self, profile):
        customer = _model("accounts", "User").objects.create_user(
            email="c@test.local", password=PASSWORD
        )
        customer.is_active = True
        customer.save()

        client = APIClient()
        client.force_authenticate(user=customer)

        response = client.patch(
            detail_url(profile),
            {"logo_light": SimpleUploadedFile("logo.png", real_png_bytes(), "image/png")},
            format="multipart",
        )

        assert response.status_code == 403


# ═══════════════════════════════════════════════════════════
#  The remaining profile fields
# ═══════════════════════════════════════════════════════════


class TestProfileFields:
    def test_typography_and_shape_are_editable(self, admin_client, profile):
        response = admin_client.patch(
            detail_url(profile),
            {
                "font_ar": "Tajawal",
                "font_en": "Roboto",
                "font_size_base": "1.125",
                "radius": "0.250",
                "shadow_level": 2,
                "default_mode": "DARK",
            },
            format="json",
        )

        assert response.status_code == 200
        profile.refresh_from_db()
        assert profile.font_ar == "Tajawal"
        assert profile.shadow_level == 2
        assert profile.default_mode == "DARK"

    def test_out_of_range_values_are_refused(self, admin_client, profile):
        """
        ⚠️  The limits live on the server, not in the frontend alone — two
            identical checks in two places diverge at the first edit.
        """
        response = admin_client.patch(
            detail_url(profile), {"font_size_base": "9.000"}, format="json"
        )

        assert response.status_code == 400
        assert "font_size_base" in response.data["fields"]

    def test_contact_and_social_are_editable(self, admin_client, profile):
        response = admin_client.patch(
            detail_url(profile),
            {
                "contact_email": "hello@example.com",
                "whatsapp": "201000000000",
                "instagram": "https://instagram.com/store",
            },
            format="json",
        )

        assert response.status_code == 200
        profile.refresh_from_db()
        assert profile.contact_email == "hello@example.com"
        assert profile.instagram.endswith("/store")

    def test_a_malformed_email_is_refused(self, admin_client, profile):
        response = admin_client.patch(
            detail_url(profile), {"contact_email": "not-an-email"}, format="json"
        )

        assert response.status_code == 400
        assert "contact_email" in response.data["fields"]
