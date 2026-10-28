"""
Contact channels — the model, the public payload and the cache.

The parser itself is pinned in `test_channel_rules.py`; the admin API in
`test_channel_api.py`. This file is about what a channel *does* once it exists.
"""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient

from branding import services
from branding.models import BrandProfile, ContactChannel, ThemeMode, ThemePalette


@pytest.fixture
def profile(db):
    # ⚠️  `branding.0002` ships an active default — clear it, as `test_branding.py` does
    BrandProfile.objects.all().delete()
    profile = BrandProfile.objects.create(
        code="test", name_ar="متجر", name_en="Store", is_active=True
    )
    for mode in ThemeMode:
        ThemePalette.objects.create(profile=profile, mode=mode)
    services.invalidate_cache()
    return profile


def _channel(profile, kind="WHATSAPP", value="01012345678", **extra) -> ContactChannel:
    return ContactChannel.objects.create(profile=profile, kind=kind, value=value, **extra)


def _payload() -> dict:
    return APIClient().get(reverse("v1:branding:theme")).data


# ═══════════════════════════════════════════════════════════
#  The model
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestModel:
    def test_the_value_is_stored_in_its_canonical_form(self, profile):
        assert _channel(profile).value == "201012345678"
        assert _channel(profile, "TELEGRAM", "t.me/mystore").value == "@mystore"
        assert (
            _channel(profile, "INSTAGRAM", "mystore").value == "https://www.instagram.com/mystore"
        )

        stored = ContactChannel.objects.get(kind="WHATSAPP")
        assert stored.value == "201012345678"

    def test_a_hostile_value_cannot_be_saved_by_any_path(self, profile):
        """`create()` is what the seed and the shell use — it must not skip the rules."""
        with pytest.raises(ValidationError) as caught:
            _channel(profile, "WEBSITE", "javascript:alert(1)")
        assert "value" in caught.value.message_dict
        assert not ContactChannel.objects.exists()

    def test_full_clean_reports_codes_per_field(self, profile):
        channel = ContactChannel(profile=profile, kind="WHATSAPP", value="abc", label_en="x" * 61)
        with pytest.raises(ValidationError) as caught:
            channel.full_clean()

        errors = caught.value.error_dict
        assert errors["value"][0].code == "invalid_whatsapp"
        assert "label_en" in errors

    def test_saving_twice_changes_nothing(self, profile):
        channel = _channel(profile, "TELEGRAM", "@mystore")
        before = channel.value
        channel.save()
        channel.refresh_from_db()
        assert channel.value == before

    def test_whatsapp_only_fields_are_dropped_from_other_kinds(self, profile):
        channel = _channel(
            profile, "TELEGRAM", "@mystore", message_en="Hi", show_floating_button=True
        )
        assert channel.message_en == ""
        assert channel.show_floating_button is False

    def test_only_one_floating_button_per_profile(self, profile):
        first = _channel(profile, show_floating_button=True)
        second = _channel(profile, "WHATSAPP", "01111111111", show_floating_button=True)

        first.refresh_from_db()
        second.refresh_from_db()
        assert second.show_floating_button is True
        assert first.show_floating_button is False

    def test_the_floating_button_of_another_profile_is_untouched(self, profile):
        other = BrandProfile.objects.create(code="winter", name_ar="شتاء", name_en="Winter")
        mine = _channel(profile, show_floating_button=True)
        theirs = _channel(other, show_floating_button=True)

        mine.refresh_from_db()
        theirs.refresh_from_db()
        assert mine.show_floating_button and theirs.show_floating_button

    def test_a_state_only_save_does_not_revalidate(self, profile):
        """The toggle must still work on a row that predates a stricter rule."""
        channel = _channel(profile, "WEBSITE", "https://example.com")
        ContactChannel.objects.filter(pk=channel.pk).update(value="http://legacy.example")

        channel.refresh_from_db()
        channel.is_active = False
        channel.save(update_fields=["is_active"])

        assert ContactChannel.objects.get(pk=channel.pk).is_active is False

    def test_label_falls_back_to_the_kind_default(self, profile):
        assert _channel(profile).label == {"ar": "واتساب", "en": "WhatsApp"}
        custom = _channel(profile, "PHONE", "0221234567", label_ar="الخط الساخن")
        assert custom.label == {"ar": "الخط الساخن", "en": "Call us"}

    def test_deleting_the_profile_row_removes_its_channels(self, profile):
        _channel(profile)
        profile.hard_delete()
        assert not ContactChannel.objects.exists()


# ═══════════════════════════════════════════════════════════
#  The public payload
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPublicPayload:
    def test_a_profile_without_channels_has_an_empty_list(self, profile):
        assert _payload()["contact_channels"] == []

    def test_the_fallback_identity_carries_the_key_too(self, db):
        BrandProfile.objects.all().delete()
        services.invalidate_cache()
        assert _payload()["contact_channels"] == []

    def test_the_old_contact_and_social_blocks_are_untouched(self, profile):
        profile.contact_email = "hello@example.com"
        profile.contact_phone = "0221234567"
        profile.facebook = "https://facebook.com/store"
        profile.save()
        _channel(profile)

        payload = _payload()
        assert payload["contact"]["email"] == "hello@example.com"
        assert payload["contact"]["phone"] == "0221234567"
        assert payload["social"]["facebook"] == "https://facebook.com/store"

    def test_only_active_channels_are_public(self, profile):
        _channel(profile, "WHATSAPP", "01012345678")
        _channel(profile, "TELEGRAM", "@hidden_one", is_active=False)

        kinds = [entry["kind"] for entry in _payload()["contact_channels"]]
        assert kinds == ["WHATSAPP"]

    def test_channels_come_in_display_order(self, profile):
        _channel(profile, "INSTAGRAM", "store", display_order=2)
        _channel(profile, "WHATSAPP", "01012345678", display_order=0)
        _channel(profile, "TELEGRAM", "@mystore", display_order=1)

        kinds = [entry["kind"] for entry in _payload()["contact_channels"]]
        assert kinds == ["WHATSAPP", "TELEGRAM", "INSTAGRAM"]

    def test_an_entry_carries_the_computed_link_and_label(self, profile):
        _channel(profile, message_ar="مرحبا", message_en="Hello", display_order=3)

        (entry,) = _payload()["contact_channels"]
        assert entry == {
            "kind": "WHATSAPP",
            "label": {"ar": "واتساب", "en": "WhatsApp"},
            "value": "+20 10 1234 5678",
            "href": "https://wa.me/201012345678?text=%D9%85%D8%B1%D8%AD%D8%A8%D8%A7",
            "href_en": "https://wa.me/201012345678?text=Hello",
            "order": 3,
            "floating": False,
        }

    def test_the_floating_flag_is_public_only_for_whatsapp(self, profile):
        _channel(profile, show_floating_button=True)
        _channel(profile, "TELEGRAM", "@mystore")

        by_kind = {entry["kind"]: entry for entry in _payload()["contact_channels"]}
        assert by_kind["WHATSAPP"]["floating"] is True
        assert by_kind["TELEGRAM"]["floating"] is False

    def test_no_admin_state_leaks(self, profile):
        channel = _channel(profile, message_ar="سر", label_ar="س", show_floating_button=True)

        (entry,) = _payload()["contact_channels"]
        assert set(entry) == {"kind", "label", "value", "href", "href_en", "order", "floating"}

        text = str(_payload())
        assert str(channel.pk) not in text
        assert "is_active" not in text
        assert "message_ar" not in text and "show_floating_button" not in text

    def test_a_draft_profile_channels_are_not_public(self, profile):
        draft = BrandProfile.objects.create(code="winter", name_ar="شتاء", name_en="Winter")
        _channel(draft, "TELEGRAM", "@winter_sale")
        _channel(profile)

        kinds = [entry["kind"] for entry in _payload()["contact_channels"]]
        assert kinds == ["WHATSAPP"]

    def test_activating_a_profile_switches_its_channels_in(self, profile):
        """A seasonal identity carries its own contacts and goes live with its colours."""
        draft = BrandProfile.objects.create(code="winter", name_ar="شتاء", name_en="Winter")
        for mode in ThemeMode:
            ThemePalette.objects.create(profile=draft, mode=mode)
        _channel(draft, "TELEGRAM", "@winter_sale")
        _channel(profile)

        profile.is_active = False
        profile.save()
        draft.is_active = True
        draft.save()

        kinds = [entry["kind"] for entry in _payload()["contact_channels"]]
        assert kinds == ["TELEGRAM"]

    def test_an_unreadable_row_is_skipped_not_fatal(self, profile):
        """One corrupt row must cost a log line, not the whole storefront."""
        good = _channel(profile, "TELEGRAM", "@mystore")
        bad = _channel(profile, "WEBSITE", "https://example.com")
        ContactChannel.objects.filter(pk=bad.pk).update(value="javascript:alert(1)")
        services.invalidate_cache()

        entries = _payload()["contact_channels"]
        assert [entry["kind"] for entry in entries] == ["TELEGRAM"]
        assert good.pk is not None

    def test_no_stored_javascript_url_ever_reaches_an_href(self, profile):
        row = _channel(profile, "OTHER", "https://example.com")
        ContactChannel.objects.filter(pk=row.pk).update(value="javascript:alert(document.cookie)")
        services.invalidate_cache()

        assert "javascript" not in str(_payload()).lower()


# ═══════════════════════════════════════════════════════════
#  Cache invalidation
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCacheInvalidation:
    """The payload is cached for 12 hours — every write path must clear it."""

    def test_creating_a_channel_shows_immediately(self, profile):
        assert _payload()["contact_channels"] == []  # fills the cache
        _channel(profile)
        assert len(_payload()["contact_channels"]) == 1

    def test_editing_a_channel_shows_immediately(self, profile):
        channel = _channel(profile)
        _payload()
        channel.value = "01111111111"
        channel.save()
        assert _payload()["contact_channels"][0]["href"] == "https://wa.me/201111111111"

    def test_deactivating_a_channel_shows_immediately(self, profile):
        channel = _channel(profile)
        _payload()
        channel.is_active = False
        channel.save(update_fields=["is_active"])
        assert _payload()["contact_channels"] == []

    def test_deleting_a_channel_shows_immediately(self, profile):
        channel = _channel(profile)
        _payload()
        channel.delete()
        assert _payload()["contact_channels"] == []
