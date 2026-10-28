"""
Free shipping above an amount the owner sets — the rule, the quote and the admin switch.

⚠️  What these guard is the part that fails **silently**: a rule left on with a
    zero amount (free on every order), a boundary that is off by a piastre, an
    express method that was meant to stay paid, and a pickup that gets marked as
    "waived by the threshold" and pollutes the report.
"""

from decimal import Decimal

import pytest
from django.apps import apps
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from core import features
from core.models.audit import AuditAction, AuditLog
from core.models.settings import SystemSetting
from core.testing import grant_all_domains
from shipping import services
from shipping.models import ShippingMethod, ShippingRate, ShippingZone

PASSWORD = "Str0ng-Test-Pass!23"
CAIRO = "القاهرة"

pytestmark = pytest.mark.django_db


def turn_on(threshold="500.00"):
    services.save_free_shipping_rule(enabled=True, threshold=Decimal(threshold))


@pytest.fixture
def world(db):
    zone = ShippingZone.objects.create(
        code="cairo", name_ar="القاهرة", name_en="Cairo", governorates=[CAIRO]
    )
    standard = ShippingMethod.objects.create(
        code="standard", name_ar="عادي", name_en="Standard", display_order=1
    )
    express = ShippingMethod.objects.create(
        code="express",
        name_ar="سريع",
        name_en="Express",
        display_order=2,
        eligible_for_free_shipping=False,
    )
    pickup = ShippingMethod.objects.create(
        code="pickup", name_ar="استلام", name_en="Pickup", display_order=3, is_pickup=True
    )
    ShippingRate.objects.create(zone=zone, method=standard, base_fee=Decimal("30.00"))
    ShippingRate.objects.create(zone=zone, method=express, base_fee=Decimal("60.00"))
    ShippingRate.objects.create(zone=zone, method=pickup, base_fee=Decimal("0.00"))
    return {"zone": zone, "standard": standard, "express": express, "pickup": pickup}


def by_code(amount, **kwargs):
    quotes = services.quote(CAIRO, amount, **kwargs)
    return {q.method_code: q for q in quotes}


# ═══════════════════════════════════════════════════════════
#  The rule
# ═══════════════════════════════════════════════════════════


class TestRule:
    def test_off_by_default(self, world):
        """A fresh database never gives anything away."""
        assert features.free_shipping_rule().active is False

        quotes = by_code(Decimal("100000.00"))
        assert quotes["standard"].fee == Decimal("30.00")
        assert quotes["standard"].free_by_threshold is False

    def test_missing_rows_mean_off(self, world):
        SystemSetting.objects.filter(
            key__in=[features.FREE_SHIPPING_ENABLED, features.FREE_SHIPPING_THRESHOLD]
        ).delete()

        assert features.free_shipping_rule() == features.FreeShippingRule()

    def test_enabled_with_no_amount_does_not_apply(self, world):
        """
        ⚠️  "On, free above 0" would be free shipping on every order — a row edited by
            hand in the Django panel must fail towards charging.
        """
        SystemSetting.objects.filter(key=features.FREE_SHIPPING_ENABLED).update(value=True)
        SystemSetting.objects.filter(key=features.FREE_SHIPPING_THRESHOLD).update(value="0.00")

        rule = features.free_shipping_rule()
        assert rule.enabled is True
        assert rule.active is False
        assert by_code(Decimal("999.00"))["standard"].fee == Decimal("30.00")
        assert services.free_shipping_status(Decimal("999.00")).enabled is False

    def test_garbage_amount_reads_as_zero(self, world):
        SystemSetting.objects.filter(key=features.FREE_SHIPPING_ENABLED).update(value=True)
        SystemSetting.objects.filter(key=features.FREE_SHIPPING_THRESHOLD).update(value="abc")

        assert features.free_shipping_rule().active is False

    def test_turning_it_off_takes_effect_immediately(self, world):
        """No cached copy outlives the switch."""
        turn_on("500.00")
        assert by_code(Decimal("500.00"))["standard"].fee == Decimal("0.00")

        services.save_free_shipping_rule(enabled=False, threshold=Decimal("500.00"))
        assert by_code(Decimal("500.00"))["standard"].fee == Decimal("30.00")

    def test_migration_created_the_rows_off(self, db):
        enabled = SystemSetting.objects.get(pk=features.FREE_SHIPPING_ENABLED)
        assert enabled.value is False
        assert SystemSetting.objects.filter(pk=features.FREE_SHIPPING_THRESHOLD).exists()


# ═══════════════════════════════════════════════════════════
#  The boundary
# ═══════════════════════════════════════════════════════════


class TestBoundary:
    def test_equal_qualifies(self, world):
        turn_on("500.00")

        standard = by_code(Decimal("500.00"))["standard"]
        assert standard.fee == Decimal("0.00")
        assert standard.is_free and standard.free_by_threshold
        assert standard.original_fee == Decimal("30.00")

    def test_one_piastre_less_does_not(self, world):
        turn_on("500.00")

        standard = by_code(Decimal("499.99"))["standard"]
        assert standard.fee == Decimal("30.00")
        assert standard.original_fee == Decimal("30.00")
        assert not standard.free_by_threshold

    def test_status_reports_what_is_missing(self, world):
        turn_on("500.00")

        short = services.free_shipping_status(Decimal("499.99"))
        assert (short.enabled, short.qualifies) == (True, False)
        assert short.threshold == Decimal("500.00")
        assert short.remaining == Decimal("0.01")

        reached = services.free_shipping_status(Decimal("500.00"))
        assert (reached.qualifies, reached.remaining) == (True, Decimal("0.00"))

    def test_status_when_off_is_inert(self, world):
        status = services.free_shipping_status(Decimal("10.00"))
        assert (status.enabled, status.qualifies) == (False, False)
        assert status.threshold == status.remaining == Decimal("0.00")


# ═══════════════════════════════════════════════════════════
#  Which methods become free
# ═══════════════════════════════════════════════════════════


class TestMethods:
    def test_ineligible_method_keeps_its_price(self, world):
        turn_on("500.00")

        quotes = by_code(Decimal("800.00"))
        assert quotes["standard"].fee == Decimal("0.00")
        assert quotes["express"].fee == Decimal("60.00")
        assert quotes["express"].free_by_threshold is False

    def test_pickup_is_unaffected(self, world):
        """Already free by nature — not marked as waived by the threshold."""
        turn_on("500.00")

        pickup = by_code(Decimal("800.00"))["pickup"]
        assert pickup.fee == Decimal("0.00")
        assert pickup.is_pickup and pickup.is_free
        assert pickup.free_by_threshold is False

    def test_a_rate_that_costs_nothing_is_not_marked_waived(self, world):
        turn_on("500.00")
        ShippingRate.objects.filter(method=world["standard"]).update(base_fee=Decimal("0.00"))

        standard = by_code(Decimal("800.00"))["standard"]
        assert standard.fee == Decimal("0.00")
        assert standard.free_by_threshold is False

    def test_the_zone_threshold_still_works_alone(self, world):
        """The per-row `free_above` is a separate, older rule — it keeps working."""
        ShippingRate.objects.filter(method=world["express"]).update(free_above=Decimal("100.00"))

        express = by_code(Decimal("150.00"))["express"]
        assert express.fee == Decimal("0.00")
        assert express.free_by_threshold is False  # the zone rule, not the store-wide one

    def test_weight_fee_is_what_gets_waived(self, world):
        turn_on("500.00")
        ShippingRate.objects.filter(method=world["standard"]).update(per_kg_fee=Decimal("10.00"))

        standard = by_code(Decimal("600.00"), weight_grams=2000)["standard"]
        assert standard.fee == Decimal("0.00")
        assert standard.original_fee == Decimal("50.00")

    def test_eligible_amount_decides_not_the_subtotal(self, world):
        """After a coupon the eligible amount is lower than the subtotal."""
        turn_on("500.00")

        standard = by_code(Decimal("550.00"), eligible_amount=Decimal("450.00"))["standard"]
        assert standard.fee == Decimal("30.00")


# ═══════════════════════════════════════════════════════════
#  The public quote endpoint
# ═══════════════════════════════════════════════════════════


class TestQuoteEndpoint:
    def test_envelope_carries_the_free_shipping_status(self, world):
        turn_on("500.00")
        client = APIClient()

        response = client.get(
            reverse("v1:shipping:quote"),
            {"governorate": CAIRO, "subtotal": "520.00", "eligible_amount": "480.00"},
        )

        assert response.status_code == 200
        assert response.data["free_shipping"] == {
            "enabled": True,
            "threshold": "500.00",
            "qualifies": False,
            "remaining": "20.00",
        }
        standard = next(q for q in response.data["quotes"] if q["method_code"] == "standard")
        assert standard["fee"] == "30.00"
        assert standard["original_fee"] == "30.00"
        assert standard["free_by_threshold"] is False

    def test_qualifying_quote_shows_the_struck_through_price(self, world):
        turn_on("500.00")

        response = APIClient().get(
            reverse("v1:shipping:quote"),
            {"governorate": CAIRO, "subtotal": "500.00", "eligible_amount": "500.00"},
        )

        standard = next(q for q in response.data["quotes"] if q["method_code"] == "standard")
        assert (standard["fee"], standard["original_fee"]) == ("0.00", "30.00")
        assert standard["free_by_threshold"] is True
        assert response.data["free_shipping"]["qualifies"] is True

    def test_disabled_says_so(self, world):
        response = APIClient().get(
            reverse("v1:shipping:quote"), {"governorate": CAIRO, "subtotal": "900.00"}
        )

        assert response.data["free_shipping"]["enabled"] is False
        assert all(q["free_by_threshold"] is False for q in response.data["quotes"])

    @pytest.mark.parametrize("bad", ["NaN", "Infinity", "-5", "abc"])
    def test_unreadable_amounts_do_not_crash(self, world, bad):
        turn_on("500.00")

        response = APIClient().get(
            reverse("v1:shipping:quote"),
            {"governorate": CAIRO, "subtotal": bad, "eligible_amount": bad},
        )
        assert response.status_code == 200
        assert response.data["free_shipping"]["qualifies"] is False


# ═══════════════════════════════════════════════════════════
#  The admin switch
# ═══════════════════════════════════════════════════════════


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


URL = "v1:shipping:admin-free-shipping"


def audit_entries():
    return AuditLog.objects.filter(
        action=AuditAction.SETTING_CHANGE, object_repr__contains="الشحن المجاني"
    )


class TestAdminSwitch:
    def test_anonymous_is_refused(self, db):
        assert APIClient().get(reverse(URL)).status_code in (401, 403)
        assert APIClient().put(reverse(URL), {}, format="json").status_code in (401, 403)

    def test_a_customer_is_refused(self, db):
        customer = User.objects.create_user(
            email="shopper@test.local", password=PASSWORD, account_type=AccountType.STUDENT
        )
        customer.is_active = True
        customer.save()
        client = APIClient()
        client.force_authenticate(user=customer)

        assert client.get(reverse(URL)).status_code == 403
        assert (
            client.put(
                reverse(URL), {"enabled": True, "threshold": "500"}, format="json"
            ).status_code
            == 403
        )
        assert features.free_shipping_rule().enabled is False

    def test_reads_the_stored_values(self, admin_client):
        response = admin_client.get(reverse(URL))

        assert response.status_code == 200
        assert response.data == {"enabled": False, "threshold": "0.00", "active": False}

    def test_turning_it_on_takes_effect_and_is_audited(self, admin_client, world):
        response = admin_client.put(
            reverse(URL), {"enabled": True, "threshold": "750.50"}, format="json"
        )

        assert response.status_code == 200
        assert response.data == {"enabled": True, "threshold": "750.50", "active": True}
        assert by_code(Decimal("750.50"))["standard"].fee == Decimal("0.00")

        entry = audit_entries().get()
        assert entry.changes["enabled_from"] is False
        assert entry.changes["enabled_to"] is True
        assert entry.changes["threshold_to"] == "750.50"
        assert entry.actor.email == "shipping-admin@test.local"

    def test_cannot_enable_without_a_positive_amount(self, admin_client):
        for body in (
            {"enabled": True, "threshold": "0"},
            {"enabled": True, "threshold": "-10"},
            {"enabled": True},
        ):
            response = admin_client.put(reverse(URL), body, format="json")
            assert response.status_code == 400, body

        assert features.free_shipping_rule().enabled is False
        assert not audit_entries().exists()

    def test_patch_enable_uses_the_stored_amount(self, admin_client):
        admin_client.put(reverse(URL), {"enabled": False, "threshold": "300"}, format="json")

        response = admin_client.patch(reverse(URL), {"enabled": True}, format="json")
        assert response.status_code == 200
        assert response.data["threshold"] == "300.00"
        assert response.data["active"] is True

    def test_patch_enable_with_no_stored_amount_is_refused(self, admin_client):
        response = admin_client.patch(reverse(URL), {"enabled": True}, format="json")
        assert response.status_code == 400
        assert "threshold" in response.data or "threshold" in str(response.data)

    def test_can_switch_off_and_keep_the_amount(self, admin_client):
        admin_client.put(reverse(URL), {"enabled": True, "threshold": "400"}, format="json")

        response = admin_client.patch(reverse(URL), {"enabled": False}, format="json")
        assert response.status_code == 200
        assert response.data == {"enabled": False, "threshold": "400.00", "active": False}

    def test_a_save_that_changes_nothing_is_not_audited(self, admin_client):
        body = {"enabled": True, "threshold": "400"}
        admin_client.put(reverse(URL), body, format="json")
        admin_client.put(reverse(URL), body, format="json")

        assert audit_entries().count() == 1

    def test_missing_rows_are_recreated(self, admin_client):
        SystemSetting.objects.filter(
            key__in=[features.FREE_SHIPPING_ENABLED, features.FREE_SHIPPING_THRESHOLD]
        ).delete()

        response = admin_client.put(
            reverse(URL), {"enabled": True, "threshold": "250"}, format="json"
        )
        assert response.status_code == 200
        assert features.free_shipping_rule().threshold == Decimal("250.00")

    def test_method_eligibility_is_editable(self, admin_client, world):
        express = world["express"]
        assert express.eligible_for_free_shipping is False

        response = admin_client.patch(
            reverse("v1:shipping:admin-method-detail", args=[express.id]),
            {"eligible_for_free_shipping": True},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["eligible_for_free_shipping"] is True

        listing = admin_client.get(reverse("v1:shipping:admin-methods"))
        assert all("eligible_for_free_shipping" in row for row in listing.data)

    def test_new_methods_are_eligible_by_default(self, admin_client):
        response = admin_client.post(
            reverse("v1:shipping:admin-methods"),
            {"code": "scooter", "name_ar": "دراجة", "name_en": "Scooter"},
            format="json",
        )
        assert response.status_code == 201
        assert response.data["eligible_for_free_shipping"] is True
