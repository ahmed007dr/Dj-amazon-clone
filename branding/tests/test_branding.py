"""
Visual identity tests.

⚠️  The requirement: **control of colours, logo and slogans from the admin panel
    for the frontend** — with no redeployment.

    The tests here guard the properties that make that real: the effect is
    immediate · contrast is enforced · the identity works before it is configured.
"""

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient

from branding import services
from branding.contrast import contrast_ratio, passes_aa
from branding.models import BrandProfile, DefaultMode, ThemeMode, ThemePalette
from core.testing import grant_all_domains

PASSWORD = "Str0ng-Test-Pass!23"


def _model(label: str, name: str):
    """
    ⚠️  `apps.get_model`, not `import`.

        `branding` is forbidden from importing any business domain — enforced by
        `import-linter`, and the test is part of the package, not an exception
        to it. And that is right: were `branding` to import the `User` model,
        deleting the accounts domain would break the visual identity for no reason.

        A string lookup keeps the dependency at **runtime** only, and it must sit
        inside a function rather than at module level (`AppRegistryNotReady`).
    """
    return apps.get_model(label, name)


@pytest.fixture
def profile(db):
    # ⚠️  The default identity created by `branding.0002` is cleared first.
    #
    #     `unique_active_brand_profile` permits exactly one active profile, so a
    #     migration-created active default collides with the one built here —
    #     every test in this module failed with an IntegrityError that named the
    #     constraint rather than the cause.
    #
    #     Deleting it also restores the precondition the assertions rely on: a
    #     table holding only what the test put there.
    BrandProfile.objects.all().delete()

    profile = BrandProfile.objects.create(
        code="test", name_ar="متجر", name_en="Store", is_active=True
    )
    for mode in ThemeMode:
        ThemePalette.objects.create(profile=profile, mode=mode)
    services.invalidate_cache()
    return profile


@pytest.fixture
def admin_client(db):
    user_model = _model("accounts", "User")

    admin = user_model.objects.create_user(
        email="brand-admin@test.local", password=PASSWORD, account_type="ADMIN"
    )
    admin.is_active = True
    admin.save()
    _model("administration", "AdminProfile").objects.create(user=admin)
    grant_all_domains(admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


# ═══════════════════════════════════════════════════════════
#  Contrast calculation
# ═══════════════════════════════════════════════════════════


class TestContrast:
    def test_known_ratios(self):
        """Reference values from the WCAG specification."""
        assert round(contrast_ratio("#000000", "#ffffff"), 1) == 21.0
        assert round(contrast_ratio("#ffffff", "#ffffff"), 1) == 1.0

    def test_order_does_not_matter(self):
        assert contrast_ratio("#123456", "#fedcba") == contrast_ratio("#fedcba", "#123456")

    def test_short_hex_is_expanded(self):
        assert contrast_ratio("#fff", "#000") == contrast_ratio("#ffffff", "#000000")

    def test_green_channel_dominates(self):
        """
        ⚠️  Not the average of the channels — the eye is far more sensitive to green.

            A simple average makes pure blue and pure green equal, when in
            reality they sit at opposite ends of readability.
        """
        green = contrast_ratio("#00ff00", "#000000")
        blue = contrast_ratio("#0000ff", "#000000")
        assert green > blue * 3

    def test_light_grey_on_white_fails_aa(self):
        """The "elegant" light grey — it collapses in sunlight and for a weak eye."""
        assert not passes_aa("#aaaaaa", "#ffffff")
        assert passes_aa("#595959", "#ffffff")


# ═══════════════════════════════════════════════════════════
#  The contrast guard
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestContrastGuard:
    def test_unreadable_palette_is_rejected(self, profile):
        """
        ⚠️  An unreadable palette is normally discovered through a complaint
            from a user who cannot describe it. Checking here turns it into an
            error on the admin screen.
        """
        palette = profile.palettes.get(mode=ThemeMode.LIGHT)
        palette.text = "#dddddd"
        palette.bg = "#ffffff"

        with pytest.raises(ValidationError):
            palette.clean()

    def test_white_on_light_green_is_rejected(self):
        """
        ⚠️  The common trap: white on light green — it looks fine and yields
            2.1:1, less than half the acceptable threshold.
        """
        palette = ThemePalette(mode=ThemeMode.DARK, on_primary="#ffffff", primary="#66bb6a")

        with pytest.raises(ValidationError):
            palette.clean()

    def test_activation_refuses_a_failing_palette(self, admin_client, profile):
        candidate = BrandProfile.objects.create(code="broken", name_ar="س", name_en="X")
        ThemePalette.objects.create(
            profile=candidate, mode=ThemeMode.LIGHT, text="#eeeeee", bg="#ffffff"
        )
        ThemePalette.objects.create(profile=candidate, mode=ThemeMode.DARK)

        response = admin_client.post(reverse("v1:branding:profile-activate", args=[candidate.pk]))

        assert response.status_code == 400
        candidate.refresh_from_db()
        assert not candidate.is_active
        assert BrandProfile.objects.get(pk=profile.pk).is_active


# ═══════════════════════════════════════════════════════════
#  The public payload
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPublicTheme:
    def test_is_public(self, profile):
        response = APIClient().get(reverse("v1:branding:theme"))
        assert response.status_code == 200

    def test_returns_ready_css_tokens(self, profile):
        """
        ⚠️  Ready-made tokens, not raw fields.

            Leaving the frontend to build the variable names duplicates them
            across two repositories, so adding one colour becomes two edits.
        """
        payload = APIClient().get(reverse("v1:branding:theme")).data

        assert payload["palettes"]["LIGHT"]["--color-primary"].startswith("#")
        assert payload["tokens"]["--radius"].endswith("rem")

    def test_both_modes_are_present(self, profile):
        payload = APIClient().get(reverse("v1:branding:theme")).data
        assert set(payload["palettes"]) == {"LIGHT", "DARK"}

    def test_works_before_any_profile_is_configured(self, db):
        """
        ⚠️  A frontend with no colours paints a white page with black text — it
            looks like a fault rather than "the identity is not configured yet".

        ⚠️  The condition is **created**, not assumed.

            `branding.0002` ships a default identity, so a migrated database is
            never empty. The guarantee under test is still real — an operator can
            delete every profile — so the test now produces that state instead of
            relying on the table happening to be bare.
        """
        BrandProfile.objects.all().delete()
        assert not BrandProfile.objects.exists()

        payload = APIClient().get(reverse("v1:branding:theme")).data

        assert payload["palettes"]["LIGHT"]["--color-primary"]
        assert payload["palettes"]["DARK"]["--color-primary"]
        assert payload["default_mode"] == DefaultMode.SYSTEM

    def test_no_admin_fields_leak(self, profile):
        payload = str(APIClient().get(reverse("v1:branding:theme")).data)
        assert "is_active" not in payload
        assert str(profile.pk) not in payload


# ═══════════════════════════════════════════════════════════
#  Immediate effect — the heart of the requirement
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestLiveControl:
    def test_color_change_reaches_the_frontend_immediately(self, admin_client, profile):
        """
        ⚠️  **The heart of the requirement.**

            The admin changes the primary colour and it shows in the public
            payload on the next request — with no redeployment and no rebuild.
        """
        client = APIClient()
        palette = profile.palettes.get(mode=ThemeMode.LIGHT)

        before = client.get(reverse("v1:branding:theme")).data
        assert before["palettes"]["LIGHT"]["--color-primary"] != "#0b5394"

        response = admin_client.patch(
            reverse("v1:branding:palette-detail", args=[profile.pk, palette.pk]),
            {"primary": "#0b5394", "on_primary": "#ffffff"},
            format="json",
        )
        assert response.status_code == 200

        after = client.get(reverse("v1:branding:theme")).data
        assert after["palettes"]["LIGHT"]["--color-primary"] == "#0b5394"

    def test_cache_is_invalidated_outside_the_api_too(self, profile):
        """
        ⚠️  The identity is edited from four paths (API · the Django panel ·
            the seed · the shell). Invalidation is by signal, not by a manual
            call — otherwise any forgotten path leaves stale colours for half a day.
        """
        client = APIClient()
        client.get(reverse("v1:branding:theme"))  # fills the cache

        palette = profile.palettes.get(mode=ThemeMode.LIGHT)
        palette.primary = "#7b1fa2"
        palette.on_primary = "#ffffff"
        palette.save()

        after = client.get(reverse("v1:branding:theme")).data
        assert after["palettes"]["LIGHT"]["--color-primary"] == "#7b1fa2"

    def test_activating_a_profile_deactivates_the_previous(self, admin_client, profile):
        replacement = BrandProfile.objects.create(code="winter", name_ar="شتاء", name_en="Winter")
        for mode in ThemeMode:
            ThemePalette.objects.create(profile=replacement, mode=mode)

        admin_client.post(reverse("v1:branding:profile-activate", args=[replacement.pk]))

        profile.refresh_from_db()
        replacement.refresh_from_db()
        assert replacement.is_active
        assert not profile.is_active

    def test_active_profile_cannot_be_deleted(self, admin_client, profile):
        response = admin_client.delete(reverse("v1:branding:profile-detail", args=[profile.pk]))
        assert response.status_code == 409

    def test_new_profile_is_born_with_both_palettes(self, admin_client):
        """A profile with no palettes means an identity with no colours — activating it blanks the
        site."""
        response = admin_client.post(
            reverse("v1:branding:profiles"),
            {"code": "winter", "name_ar": "شتاء", "name_en": "Winter"},
            format="json",
        )

        assert response.status_code == 201
        created = BrandProfile.objects.get(code="winter")
        assert created.palettes.count() == 2
        assert not created.is_active

    def test_preview_does_not_touch_the_live_theme(self, admin_client, profile):
        """
        ⚠️  "Try it and undo" on the identity means every visitor during the
            attempt saw broken colours.
        """
        client = APIClient()
        before = client.get(reverse("v1:branding:theme")).data

        response = admin_client.post(
            reverse("v1:branding:preview"),
            {"primary": "#ff0000", "on_primary": "#ff0000", "mode": ThemeMode.LIGHT},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["passes_aa"] is False

        after = client.get(reverse("v1:branding:theme")).data
        assert after == before

    def test_preview_ignores_unknown_fields(self, admin_client):
        """One unknown field must not become a 500."""
        response = admin_client.post(
            reverse("v1:branding:preview"),
            {"primary": "#2e7d32", "nonsense": "x"},
            format="json",
        )
        assert response.status_code == 200

    def test_customer_cannot_edit_branding(self, profile):
        customer = _model("accounts", "User").objects.create_user(
            email="c@test.local", password=PASSWORD
        )
        customer.is_active = True
        customer.save()

        client = APIClient()
        client.force_authenticate(user=customer)

        response = client.get(reverse("v1:branding:profiles"))
        assert response.status_code == 403


@pytest.mark.django_db
def test_only_one_profile_can_be_active(profile):
    """ "What are the system's colours?" must not depend on query ordering."""
    from django.db.utils import IntegrityError

    with pytest.raises(IntegrityError):
        BrandProfile.objects.create(code="second", name_ar="ث", name_en="S", is_active=True)
