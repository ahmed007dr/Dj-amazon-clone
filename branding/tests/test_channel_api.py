"""
Contact channels — the admin API: CRUD, reorder, toggle, preview, permissions, audit.
"""

import uuid

import pytest
from django.apps import apps
from django.urls import reverse
from rest_framework.test import APIClient

from branding import services
from branding.models import BrandProfile, ContactChannel, ThemeMode, ThemePalette
from core.models.audit import AuditAction, AuditLog
from core.testing import grant_all_domains

PASSWORD = "Str0ng-Test-Pass!23"


def _user_model():
    # ⚠️  `apps.get_model`, not `import` — `branding` may not import a business domain
    return apps.get_model("accounts", "User")


@pytest.fixture
def profile(db):
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
    admin = _user_model().objects.create_user(
        email="channels-admin@test.local", password=PASSWORD, account_type="ADMIN"
    )
    admin.is_active = True
    admin.save()
    apps.get_model("administration", "AdminProfile").objects.create(user=admin)
    grant_all_domains(admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture
def customer_client(db):
    customer = _user_model().objects.create_user(email="shopper@test.local", password=PASSWORD)
    customer.is_active = True
    customer.save()

    client = APIClient()
    client.force_authenticate(user=customer)
    return client


def _list_url(profile) -> str:
    return reverse("v1:branding:channels", args=[profile.pk])


def _detail_url(profile, channel) -> str:
    return reverse("v1:branding:channel-detail", args=[profile.pk, channel.pk])


def _toggle_url(profile, channel) -> str:
    return reverse("v1:branding:channel-toggle", args=[profile.pk, channel.pk])


def _reorder_url(profile) -> str:
    return reverse("v1:branding:channels-reorder", args=[profile.pk])


def _make(profile, kind="WHATSAPP", value="01012345678", **extra) -> ContactChannel:
    return ContactChannel.objects.create(profile=profile, kind=kind, value=value, **extra)


def _public() -> dict:
    return APIClient().get(reverse("v1:branding:theme")).data


# ═══════════════════════════════════════════════════════════
#  Create and read
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCreate:
    def test_creates_and_returns_the_computed_fields(self, admin_client, profile):
        response = admin_client.post(
            _list_url(profile),
            {"kind": "WHATSAPP", "value": "010 1234 5678", "message_en": "Hi there"},
            format="json",
        )

        assert response.status_code == 201
        body = response.data
        assert body["value"] == "201012345678"  # the canonical form, not what was typed
        assert body["display"] == "+20 10 1234 5678"
        assert body["href"] == "https://wa.me/201012345678?text=Hi%20there"
        assert body["label"] == {"ar": "واتساب", "en": "WhatsApp"}
        assert body["is_active"] is True
        assert body["show_floating_button"] is False

    def test_new_channels_go_to_the_end(self, admin_client, profile):
        for value in ("@first_one", "@second_one", "@third_one"):
            admin_client.post(
                _list_url(profile), {"kind": "TELEGRAM", "value": value}, format="json"
            )

        listed = admin_client.get(_list_url(profile)).data
        assert [row["value"] for row in listed] == ["@first_one", "@second_one", "@third_one"]
        assert [row["display_order"] for row in listed] == [0, 1, 2]

    def test_a_new_channel_reaches_the_storefront_immediately(self, admin_client, profile):
        assert _public()["contact_channels"] == []  # fills the cache

        admin_client.post(
            _list_url(profile),
            {"kind": "INSTAGRAM", "value": "@mystore"},
            format="json",
        )

        (entry,) = _public()["contact_channels"]
        assert entry["href"] == "https://www.instagram.com/mystore"

    @pytest.mark.parametrize(
        ("payload", "field", "code"),
        [
            ({"kind": "WHATSAPP", "value": "abc"}, "value", "INVALID_WHATSAPP"),
            ({"kind": "WEBSITE", "value": "javascript:alert(1)"}, "value", "HTTPS_REQUIRED"),
            ({"kind": "OTHER", "value": "http://example.com"}, "value", "HTTPS_REQUIRED"),
            ({"kind": "OTHER", "value": "//evil.example"}, "value", "HTTPS_REQUIRED"),
            ({"kind": "OTHER", "value": "data:text/html,x"}, "value", "HTTPS_REQUIRED"),
            ({"kind": "INSTAGRAM", "value": "https://evil.example/x"}, "value", "WRONG_HOST"),
            ({"kind": "TELEGRAM", "value": "ab"}, "value", "INVALID_TELEGRAM"),
            ({"kind": "EMAIL", "value": "nope"}, "value", "INVALID_EMAIL"),
            ({"kind": "PHONE", "value": "call me"}, "value", "INVALID_PHONE"),
            ({"kind": "WEBSITE", "value": ""}, "value", "REQUIRED"),
            ({"kind": "WEBSITE", "value": "https://exa\x07mple.com"}, "value", "CONTROL_CHARS"),
            ({"kind": "WEBSITE", "value": "https://e.com/" + "a" * 400}, "value", "TOO_LONG"),
            (
                {"kind": "WHATSAPP", "value": "01012345678", "label_en": "x" * 61},
                "label_en",
                "MAX_LENGTH",
            ),
            (
                {"kind": "WHATSAPP", "value": "01012345678", "label_ar": "a\nb"},
                "label_ar",
                "CONTROL_CHARS",
            ),
        ],
    )
    def test_refuses_a_bad_value_with_a_stable_code(
        self, admin_client, profile, payload, field, code
    ):
        response = admin_client.post(_list_url(profile), payload, format="json")

        assert response.status_code == 400
        assert response.data["fields"][field][0]["code"] == code
        assert not ContactChannel.objects.exists()

    def test_the_message_is_bilingual(self, admin_client, profile):
        response = admin_client.post(
            _list_url(profile), {"kind": "WHATSAPP", "value": "abc"}, format="json"
        )
        message = response.data["fields"]["value"][0]["message"]
        assert "Invalid WhatsApp number" in message
        assert any("؀" <= ch <= "ۿ" for ch in message)

    def test_every_refused_field_is_reported_in_one_response(self, admin_client, profile):
        response = admin_client.post(
            _list_url(profile),
            {"kind": "TELEGRAM", "value": "a b", "label_ar": "x\ny"},
            format="json",
        )
        assert set(response.data["fields"]) == {"value", "label_ar"}

    def test_an_unknown_kind_is_refused(self, admin_client, profile):
        response = admin_client.post(
            _list_url(profile), {"kind": "MYSPACE", "value": "x"}, format="json"
        )
        assert response.status_code == 400
        assert "kind" in response.data["fields"]

    def test_whatsapp_only_fields_are_ignored_on_other_kinds(self, admin_client, profile):
        response = admin_client.post(
            _list_url(profile),
            {
                "kind": "TELEGRAM",
                "value": "@mystore",
                "message_en": "Hi",
                "show_floating_button": True,
            },
            format="json",
        )
        assert response.data["message_en"] == ""
        assert response.data["show_floating_button"] is False

    def test_an_unknown_profile_is_404(self, admin_client, db):
        url = reverse("v1:branding:channels", args=[uuid.uuid4()])
        assert admin_client.get(url).status_code == 404
        assert (
            admin_client.post(url, {"kind": "PHONE", "value": "19123"}, format="json").status_code
            == 404
        )


# ═══════════════════════════════════════════════════════════
#  Update and delete
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestUpdateAndDelete:
    def test_patch_renormalises_on_the_merged_state(self, admin_client, profile):
        channel = _make(profile, "TELEGRAM", "@mystore")

        response = admin_client.patch(
            _detail_url(profile, channel), {"kind": "PHONE"}, format="json"
        )

        # The old value ("@mystore") is not a phone number — the kind change must be refused
        assert response.status_code == 400
        assert response.data["fields"]["value"][0]["code"] == "INVALID_PHONE"
        channel.refresh_from_db()
        assert channel.kind == "TELEGRAM"

    def test_patch_a_label_keeps_the_value(self, admin_client, profile):
        channel = _make(profile)

        response = admin_client.patch(
            _detail_url(profile, channel), {"label_en": "Order here"}, format="json"
        )

        assert response.status_code == 200
        assert response.data["label"] == {"ar": "واتساب", "en": "Order here"}
        assert response.data["value"] == "201012345678"

    def test_an_edit_reaches_the_storefront_immediately(self, admin_client, profile):
        channel = _make(profile)
        _public()

        admin_client.patch(_detail_url(profile, channel), {"value": "01111111111"}, format="json")

        assert _public()["contact_channels"][0]["href"] == "https://wa.me/201111111111"

    def test_enabling_the_floating_button_turns_off_the_other(self, admin_client, profile):
        first = _make(profile, show_floating_button=True)
        second = _make(profile, "WHATSAPP", "01111111111")

        admin_client.patch(
            _detail_url(profile, second), {"show_floating_button": True}, format="json"
        )

        first.refresh_from_db()
        second.refresh_from_db()
        assert second.show_floating_button and not first.show_floating_button

    def test_delete_removes_the_row_and_the_public_entry(self, admin_client, profile):
        channel = _make(profile)
        _public()

        assert admin_client.delete(_detail_url(profile, channel)).status_code == 204

        assert not ContactChannel.objects.exists()
        assert _public()["contact_channels"] == []

    def test_a_channel_of_another_profile_is_not_addressable(self, admin_client, profile):
        other = BrandProfile.objects.create(code="winter", name_ar="شتاء", name_en="Winter")
        foreign = _make(other)

        url = reverse("v1:branding:channel-detail", args=[profile.pk, foreign.pk])
        assert admin_client.get(url).status_code == 404
        assert admin_client.patch(url, {"label_en": "x"}, format="json").status_code == 404
        assert admin_client.delete(url).status_code == 404
        assert ContactChannel.objects.filter(pk=foreign.pk).exists()


# ═══════════════════════════════════════════════════════════
#  Toggle
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestToggle:
    def test_an_empty_body_flips(self, admin_client, profile):
        channel = _make(profile)

        assert admin_client.post(_toggle_url(profile, channel)).data["is_active"] is False
        assert admin_client.post(_toggle_url(profile, channel)).data["is_active"] is True

    def test_an_explicit_value_sets_instead_of_flipping(self, admin_client, profile):
        channel = _make(profile)

        for _ in range(2):
            response = admin_client.post(
                _toggle_url(profile, channel), {"is_active": False}, format="json"
            )
            assert response.data["is_active"] is False

    def test_a_non_boolean_is_refused(self, admin_client, profile):
        channel = _make(profile)
        response = admin_client.post(
            _toggle_url(profile, channel), {"is_active": "yes"}, format="json"
        )
        assert response.status_code == 400

    def test_hiding_removes_it_from_the_storefront_at_once(self, admin_client, profile):
        channel = _make(profile)
        assert len(_public()["contact_channels"]) == 1

        admin_client.post(_toggle_url(profile, channel), {"is_active": False}, format="json")

        assert _public()["contact_channels"] == []


# ═══════════════════════════════════════════════════════════
#  Reorder
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestReorder:
    def test_numbers_the_whole_list(self, admin_client, profile):
        a = _make(profile, "TELEGRAM", "@aaaaa_store")
        b = _make(profile, "TELEGRAM", "@bbbbb_store")
        c = _make(profile, "TELEGRAM", "@ccccc_store")  # all three share display_order 0

        response = admin_client.post(
            _reorder_url(profile), {"ids": [str(c.pk), str(a.pk), str(b.pk)]}, format="json"
        )

        assert response.status_code == 200
        assert [row["value"] for row in response.data] == [
            "@ccccc_store",
            "@aaaaa_store",
            "@bbbbb_store",
        ]
        assert [row["display_order"] for row in response.data] == [0, 1, 2]

    def test_the_storefront_follows_the_new_order_at_once(self, admin_client, profile):
        a = _make(profile, "TELEGRAM", "@aaaaa_store", display_order=0)
        b = _make(profile, "INSTAGRAM", "store", display_order=1)
        assert [e["kind"] for e in _public()["contact_channels"]] == ["TELEGRAM", "INSTAGRAM"]

        admin_client.post(_reorder_url(profile), {"ids": [str(b.pk), str(a.pk)]}, format="json")

        # ⚠️  `bulk_update` fires no signal — the endpoint clears the cache itself
        assert [e["kind"] for e in _public()["contact_channels"]] == ["INSTAGRAM", "TELEGRAM"]

    @pytest.mark.parametrize("mistake", ["missing", "duplicate", "unknown", "foreign", "empty"])
    def test_refuses_a_list_that_is_not_exactly_this_profiles_channels(
        self, admin_client, profile, mistake
    ):
        other = BrandProfile.objects.create(code="winter", name_ar="شتاء", name_en="Winter")
        a = _make(profile, "TELEGRAM", "@aaaaa_store")
        b = _make(profile, "TELEGRAM", "@bbbbb_store")
        foreign = _make(other)

        ids = {
            "missing": [a.pk],
            "duplicate": [a.pk, a.pk, b.pk],
            "unknown": [a.pk, b.pk, uuid.uuid4()],
            "foreign": [a.pk, foreign.pk],
            "empty": [],
        }[mistake]

        response = admin_client.post(
            _reorder_url(profile), {"ids": [str(i) for i in ids]}, format="json"
        )

        assert response.status_code == 400
        foreign.refresh_from_db()
        assert foreign.display_order == 0

    def test_non_uuid_ids_are_refused(self, admin_client, profile):
        _make(profile)
        response = admin_client.post(_reorder_url(profile), {"ids": [1, 2]}, format="json")
        assert response.status_code == 400


# ═══════════════════════════════════════════════════════════
#  Preview
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPreview:
    url = "v1:branding:channel-preview"

    def test_returns_the_link_without_saving(self, admin_client, profile):
        response = admin_client.post(
            reverse(self.url),
            {"kind": "TELEGRAM", "value": "t.me/mystore"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["href"] == "https://t.me/mystore"
        assert response.data["display"] == "@mystore"
        assert not ContactChannel.objects.exists()

    def test_whatsapp_preview_includes_the_message(self, admin_client, profile):
        response = admin_client.post(
            reverse(self.url),
            {"kind": "WHATSAPP", "value": "01012345678", "message_en": "Hello"},
            format="json",
        )
        assert response.data["href_en"] == "https://wa.me/201012345678?text=Hello"

    def test_a_blank_value_is_an_empty_preview_not_an_error(self, admin_client, profile):
        response = admin_client.post(
            reverse(self.url), {"kind": "WHATSAPP", "value": "  "}, format="json"
        )
        assert response.status_code == 200
        assert response.data["href"] == ""
        assert response.data["default_label"] == {"ar": "واتساب", "en": "WhatsApp"}

    def test_a_bad_value_answers_with_the_field_error(self, admin_client, profile):
        response = admin_client.post(
            reverse(self.url), {"kind": "WEBSITE", "value": "javascript:alert(1)"}, format="json"
        )
        assert response.status_code == 400
        assert response.data["fields"]["value"][0]["code"] == "HTTPS_REQUIRED"


# ═══════════════════════════════════════════════════════════
#  Permissions and audit
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPermissions:
    def test_a_customer_is_refused_everywhere(self, customer_client, profile):
        channel = _make(profile)

        assert customer_client.get(_list_url(profile)).status_code == 403
        assert (
            customer_client.post(
                _list_url(profile), {"kind": "PHONE", "value": "19123"}, format="json"
            ).status_code
            == 403
        )
        assert (
            customer_client.patch(
                _detail_url(profile, channel), {"label_en": "x"}, format="json"
            ).status_code
            == 403
        )
        assert customer_client.delete(_detail_url(profile, channel)).status_code == 403
        assert customer_client.post(_toggle_url(profile, channel)).status_code == 403
        assert (
            customer_client.post(
                _reorder_url(profile), {"ids": [str(channel.pk)]}, format="json"
            ).status_code
            == 403
        )
        assert (
            customer_client.post(
                reverse("v1:branding:channel-preview"),
                {"kind": "PHONE", "value": "19123"},
                format="json",
            ).status_code
            == 403
        )

        channel.refresh_from_db()
        assert channel.label_en == ""

    def test_anonymous_is_refused(self, profile):
        client = APIClient()
        assert client.get(_list_url(profile)).status_code in (401, 403)
        assert client.post(
            reverse("v1:branding:channel-preview"), {}, format="json"
        ).status_code in (401, 403)

    def test_the_public_payload_stays_public(self, profile):
        assert APIClient().get(reverse("v1:branding:theme")).status_code == 200


@pytest.mark.django_db
class TestAudit:
    def _entries(self):
        return list(AuditLog.objects.order_by("id").values_list("action", "object_repr"))

    def test_every_write_leaves_a_trace(self, admin_client, profile):
        created = admin_client.post(
            _list_url(profile), {"kind": "TELEGRAM", "value": "@mystore"}, format="json"
        ).data
        channel = ContactChannel.objects.get(pk=created["id"])
        admin_client.patch(_detail_url(profile, channel), {"label_en": "Chat"}, format="json")
        admin_client.post(_toggle_url(profile, channel), {"is_active": False}, format="json")
        admin_client.post(_reorder_url(profile), {"ids": [str(channel.pk)]}, format="json")
        admin_client.delete(_detail_url(profile, channel))

        actions = [action for action, _ in self._entries()]
        assert actions == [
            AuditAction.CREATE,
            AuditAction.SETTING_CHANGE,
            AuditAction.SETTING_CHANGE,
            AuditAction.SETTING_CHANGE,
            AuditAction.DELETE,
        ]
        assert all("TELEGRAM" in repr_ or "ترتيب" in repr_ for _, repr_ in self._entries())

    def test_a_refused_write_leaves_no_trace(self, admin_client, profile):
        admin_client.post(_list_url(profile), {"kind": "WHATSAPP", "value": "abc"}, format="json")
        assert self._entries() == []
