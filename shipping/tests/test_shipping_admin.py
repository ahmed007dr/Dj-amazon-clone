"""
Configuring shipping from the panel.

⚠️  The fee table used to be editable from the Django panel alone — so whoever
    set the delivery price had to be handed the whole database to do it, and the
    fees were set once at launch and never touched again.

⚠️  What these guard is the part that fails **silently**: a governorate in two
    zones, a typed governorate name that matches nothing, a deleted default zone
    and a deleted method that keeps quoting. In every one of them the quote
    endpoint keeps answering and the checkout keeps completing — only the fee is
    wrong, and only the margin at the end of the month shows it.
"""

from decimal import Decimal

import pytest
from django.apps import apps
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from core.testing import grant_all_domains
from shipping import services
from shipping.models import ShippingMethod, ShippingRate, ShippingZone

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_user(
        email="shipping-admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    admin.is_active = True
    admin.save()
    apps.get_model("administration", "AdminProfile").objects.create(user=admin)
    grant_all_domains(admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture
def zone(db):
    return ShippingZone.objects.create(
        code="cairo-giza",
        name_ar="القاهرة الكبرى",
        name_en="Greater Cairo",
        governorates=["القاهرة", "الجيزة"],
    )


@pytest.fixture
def default_zone(db):
    return ShippingZone.objects.create(
        code="remote",
        name_ar="المناطق النائية",
        name_en="Remote areas",
        governorates=[],
        is_default=True,
    )


@pytest.fixture
def method(db):
    return ShippingMethod.objects.create(
        code="standard", name_ar="شحن عادي", name_en="Standard", display_order=10
    )


def zone_draft(**overrides) -> dict:
    body = {
        "code": "delta",
        "name_ar": "الدلتا",
        "name_en": "Delta",
        "governorates": ["الإسكندرية", "البحيرة"],
    }
    body.update(overrides)
    return body


# ═══════════════════════════════════════════════════════════
#  Zones
# ═══════════════════════════════════════════════════════════


class TestZones:
    def test_a_zone_is_created(self, admin_client):
        response = admin_client.post(
            reverse("v1:shipping:admin-zones"), zone_draft(), format="json"
        )

        assert response.status_code == 201
        assert ShippingZone.objects.filter(code="delta").exists()

    def test_an_unknown_governorate_is_refused(self, admin_client):
        """
        ⚠️  The match is literal, so a name outside the reference list is a zone
            that covers nothing — and its addresses quote the default fee with
            nothing reporting a problem.
        """
        response = admin_client.post(
            reverse("v1:shipping:admin-zones"),
            zone_draft(governorates=["الاسكندرية"]),  # no hamza — a different string
            format="json",
        )

        assert response.status_code == 400
        assert not ShippingZone.objects.filter(code="delta").exists()

    def test_a_governorate_already_in_another_zone_is_refused(self, admin_client, zone):
        """
        ⚠️  `for_governorate` returns the **first** active zone that matches, and
            the row order is not a promise the database makes. The same address
            then quotes two different fees on two consecutive requests.
        """
        response = admin_client.post(
            reverse("v1:shipping:admin-zones"),
            zone_draft(governorates=["القاهرة", "الإسكندرية"]),
            format="json",
        )

        assert response.status_code == 400
        assert "القاهرة" in str(response.data)

    def test_a_zone_keeps_its_own_governorates_on_edit(self, admin_client, zone):
        """The overlap check must not count the zone against itself."""
        response = admin_client.patch(
            reverse("v1:shipping:admin-zone-detail", args=[zone.id]),
            {"governorates": ["القاهرة", "الجيزة", "القليوبية"]},
            format="json",
        )

        assert response.status_code == 200
        zone.refresh_from_db()
        assert "القليوبية" in zone.governorates

    def test_the_default_zone_carries_no_governorates(self, admin_client):
        """
        ⚠️  It answers for whatever is not listed elsewhere. Naming governorates
            on it puts them in two places at once — matched by name here and by
            fallback there.
        """
        response = admin_client.post(
            reverse("v1:shipping:admin-zones"),
            zone_draft(is_default=True),
            format="json",
        )

        assert response.status_code == 400

    def test_promoting_a_default_stands_the_previous_one_down(
        self, admin_client, zone, default_zone
    ):
        """
        ⚠️  Uniqueness of the default is a database constraint — saving a second
            one without standing the first down is an IntegrityError, which the
            admin reads as a broken panel.
        """
        response = admin_client.patch(
            reverse("v1:shipping:admin-zone-detail", args=[zone.id]),
            {"is_default": True, "governorates": []},
            format="json",
        )

        assert response.status_code == 200
        default_zone.refresh_from_db()
        assert default_zone.is_default is False
        assert ShippingZone.objects.filter(is_default=True).count() == 1

    def test_the_code_cannot_be_renamed(self, admin_client, zone):
        """The seeds, the reports and the operational notes all name the zone by it."""
        admin_client.patch(
            reverse("v1:shipping:admin-zone-detail", args=[zone.id]),
            {"code": "renamed"},
            format="json",
        )

        zone.refresh_from_db()
        assert zone.code == "cairo-giza"

    def test_the_default_zone_is_not_deleted(self, admin_client, default_zone):
        """
        ⚠️  Deleting it leaves every unassigned governorate with an empty quote —
            a checkout that cannot complete, for customers nobody had in mind.
        """
        response = admin_client.delete(
            reverse("v1:shipping:admin-zone-detail", args=[default_zone.id])
        )

        assert response.status_code == 409
        assert ShippingZone.objects.filter(id=default_zone.id).exists()

    def test_deleting_a_zone_takes_its_rates_with_it(self, admin_client, zone, method):
        """
        ⚠️  `CASCADE` belongs to the SQL `DELETE`, and `BaseModel.delete` stamps
            `deleted_at` instead — so without this the rates outlive their zone.
        """
        ShippingRate.objects.create(zone=zone, method=method, base_fee=Decimal("30.00"))

        response = admin_client.delete(reverse("v1:shipping:admin-zone-detail", args=[zone.id]))

        assert response.status_code == 204
        assert not ShippingRate.objects.filter(zone_id=zone.id).exists()


# ═══════════════════════════════════════════════════════════
#  Methods
# ═══════════════════════════════════════════════════════════


class TestMethods:
    def test_the_admin_list_shows_disabled_methods(self, admin_client, method):
        """
        ⚠️  The public list serves the checkout and hides them. Hiding them here
            too means turning a method back on requires creating it again.
        """
        method.is_active = False
        method.save()

        response = admin_client.get(reverse("v1:shipping:admin-methods"))

        assert response.status_code == 200
        assert [row["code"] for row in response.data] == ["standard"]

    def test_a_backwards_estimate_is_refused(self, admin_client):
        response = admin_client.post(
            reverse("v1:shipping:admin-methods"),
            {
                "code": "express",
                "name_ar": "سريع",
                "name_en": "Express",
                "estimated_days_min": 4,
                "estimated_days_max": 2,
            },
            format="json",
        )

        assert response.status_code == 400

    def test_a_deleted_method_stops_quoting(self, admin_client, zone, method):
        """
        ⚠️  The regression this exists for: the soft-delete manager filters the
            rate rows, not the joined method. A deleted-but-active method kept
            appearing at checkout, priced by a rate whose method was gone from
            the panel.
        """
        ShippingRate.objects.create(zone=zone, method=method, base_fee=Decimal("30.00"))

        response = admin_client.delete(reverse("v1:shipping:admin-method-detail", args=[method.id]))

        assert response.status_code == 204
        assert services.quote("القاهرة", Decimal("100")) == []


# ═══════════════════════════════════════════════════════════
#  Rates
# ═══════════════════════════════════════════════════════════


class TestRates:
    def test_a_rate_is_created(self, admin_client, zone, method):
        response = admin_client.post(
            reverse("v1:shipping:admin-rates"),
            {
                "zone": str(zone.id),
                "method": str(method.id),
                "base_fee": "30.00",
                "free_above": "500.00",
                "per_kg_fee": "0.00",
            },
            format="json",
        )

        assert response.status_code == 201
        assert ShippingRate.objects.filter(zone=zone, method=method).exists()

    def test_a_duplicate_pair_is_named_rather_than_crashing(self, admin_client, zone, method):
        """
        ⚠️  The pair is unique in the database, and the constraint speaks as a
            500. Naming the existing row turns it into "edit that one".
        """
        ShippingRate.objects.create(zone=zone, method=method, base_fee=Decimal("30.00"))

        response = admin_client.post(
            reverse("v1:shipping:admin-rates"),
            {"zone": str(zone.id), "method": str(method.id), "base_fee": "40.00"},
            format="json",
        )

        assert response.status_code == 400
        assert ShippingRate.objects.filter(zone=zone, method=method).count() == 1

    def test_a_zero_free_threshold_is_refused(self, admin_client, zone, method):
        """It makes every order free — a real thing to want, never a thing to type."""
        response = admin_client.post(
            reverse("v1:shipping:admin-rates"),
            {
                "zone": str(zone.id),
                "method": str(method.id),
                "base_fee": "30.00",
                "free_above": "0.00",
            },
            format="json",
        )

        assert response.status_code == 400

    def test_an_edited_fee_reaches_the_quote(self, admin_client, zone, method):
        """The point of the whole screen: no deployment between the edit and the checkout."""
        rate = ShippingRate.objects.create(zone=zone, method=method, base_fee=Decimal("30.00"))

        admin_client.patch(
            reverse("v1:shipping:admin-rate-detail", args=[rate.id]),
            {"base_fee": "45.00"},
            format="json",
        )

        quotes = services.quote("القاهرة", Decimal("100"))
        assert [quote.fee for quote in quotes] == [Decimal("45.00")]


# ═══════════════════════════════════════════════════════════
#  Coverage
# ═══════════════════════════════════════════════════════════


class TestCoverage:
    def test_it_reports_the_unassigned_governorates(self, admin_client, zone, default_zone):
        """
        ⚠️  An unassigned governorate is not an error anywhere — the default zone
            answers for it at its own fee. So an unassigned Alexandria quotes the
            remote-area price and nothing complains, until a customer does.
        """
        response = admin_client.get(reverse("v1:shipping:admin-coverage"))

        assert response.status_code == 200
        assert response.data["has_default_zone"] is True
        assert "الإسكندرية" in response.data["unassigned"]
        assert "القاهرة" not in response.data["unassigned"]

    def test_a_missing_default_zone_is_reported(self, admin_client, zone):
        """With no default, an unassigned governorate gets an empty quote."""
        response = admin_client.get(reverse("v1:shipping:admin-coverage"))

        assert response.data["has_default_zone"] is False


# ═══════════════════════════════════════════════════════════
#  Permission
# ═══════════════════════════════════════════════════════════


def test_configuring_shipping_needs_the_shipping_permission(db):
    """
    ⚠️  Not `IsAdminUser`: these edit a price the customer pays. Anyone signed in
        as staff is not the same set as anyone allowed to move the fee.
    """
    user = User.objects.create_user(
        email="nobody@test.local", password=PASSWORD, account_type=AccountType.STUDENT
    )
    user.is_active = True
    user.save()

    client = APIClient()
    client.force_authenticate(user=user)

    assert client.get(reverse("v1:shipping:admin-zones")).status_code == 403
