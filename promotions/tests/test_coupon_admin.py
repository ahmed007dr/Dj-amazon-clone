"""
Coupon management from the panel.

⚠️  The `promotions` domain had **no `urls.py` at all**: the store accepts a
    coupon and nobody could create one except from the Django panel.

⚠️  And what is guarded: no public list · the code is normalised to upper case ·
    a used one is disabled and never deleted.
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from core.testing import grant_all_domains
from django.apps import apps
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from promotions.models import Coupon

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_user(
        email="promo-admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    admin.is_active = True
    admin.save()
    apps.get_model("administration", "AdminProfile").objects.create(user=admin)
    grant_all_domains(admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


def draft(**overrides) -> dict:
    body = {
        "code": "SUMMER10",
        "name_ar": "حملة الصيف",
        "name_en": "Summer campaign",
        "kind": "PERCENTAGE",
        "value": "10.00",
    }
    body.update(overrides)
    return body


# ═══════════════════════════════════════════════════════════
#  Creation and validation
# ═══════════════════════════════════════════════════════════


class TestCreate:
    def test_a_coupon_is_created(self, admin_client):
        response = admin_client.post(reverse("v1:promotions:coupons"), draft(), format="json")

        assert response.status_code == 201
        assert Coupon.objects.filter(code="SUMMER10").exists()

    def test_the_code_is_normalised_to_upper_case(self, admin_client):
        """
        ⚠️  Without normalisation, `summer10` and `SUMMER10` become two coupons
            — and a customer who types it in lower case is refused for no comprehensible reason.
        """
        response = admin_client.post(
            reverse("v1:promotions:coupons"), draft(code=" summer20 "), format="json"
        )

        assert response.status_code == 201
        assert response.data["code"] == "SUMMER20"

    def test_a_duplicate_code_is_caught_after_normalising(self, admin_client):
        """
        ⚠️  Validation on the **normalised** form: without it `summer10` passes
            alongside `SUMMER10` and they then collide on save with a database
            error rather than a field message.
        """
        admin_client.post(reverse("v1:promotions:coupons"), draft(), format="json")

        response = admin_client.post(
            reverse("v1:promotions:coupons"), draft(code="summer10"), format="json"
        )

        assert response.status_code == 400
        assert "code" in response.data["fields"]

    def test_a_percentage_above_hundred_is_refused(self, admin_client):
        """A rate above 100% makes the order negative — the store pays the customer."""
        response = admin_client.post(
            reverse("v1:promotions:coupons"), draft(value="120.00"), format="json"
        )
        assert response.status_code == 400

    def test_a_zero_discount_is_refused(self, admin_client):
        """
        ⚠️  Not a technical error but a coupon with no effect: the customer
            enters it, sees "applied", and nothing changes — so they report a
            fault that does not exist.
        """
        response = admin_client.post(
            reverse("v1:promotions:coupons"), draft(value="0.00"), format="json"
        )
        assert response.status_code == 400

    def test_an_end_before_start_is_refused(self, admin_client):
        now = timezone.now()

        response = admin_client.post(
            reverse("v1:promotions:coupons"),
            draft(starts_at=now.isoformat(), ends_at=(now - timedelta(days=1)).isoformat()),
            format="json",
        )

        assert response.status_code == 400
        assert "ends_at" in response.data["fields"]

    def test_usage_count_cannot_be_written(self, admin_client):
        """
        ⚠️  Writing it means an edit in the panel reopens an exhausted coupon
            with no trace in any redemption record.
        """
        response = admin_client.post(
            reverse("v1:promotions:coupons"), draft(usage_count=999), format="json"
        )

        assert response.status_code == 201
        assert Coupon.objects.get(code="SUMMER10").usage_count == 0


# ═══════════════════════════════════════════════════════════
#  Deletion and status
# ═══════════════════════════════════════════════════════════


class TestLifecycle:
    def test_a_used_coupon_is_not_deleted(self, admin_client):
        """
        ⚠️  The redemption records point at it, and deleting it makes "how much
            was this order sold for, and why?" a question with no answer.
        """
        coupon = Coupon.objects.create(
            code="USED",
            name_ar="مستخدم",
            name_en="Used",
            kind="FIXED",
            value=Decimal("5.00"),
            usage_count=3,
        )

        response = admin_client.delete(reverse("v1:promotions:coupon-detail", args=[coupon.pk]))

        assert response.status_code == 409
        assert "3" in response.data["detail"]
        assert Coupon.objects.filter(pk=coupon.pk).exists()

    def test_an_unused_coupon_is_deleted(self, admin_client):
        coupon = Coupon.objects.create(
            code="FRESH", name_ar="جديد", name_en="Fresh", kind="FIXED", value=Decimal("5.00")
        )

        response = admin_client.delete(reverse("v1:promotions:coupon-detail", args=[coupon.pk]))
        assert response.status_code == 204

    def test_status_filter_runs_in_the_query(self, admin_client):
        """
        ⚠️  Filtering in Python after pagination gives short pages with nobody noticing.
        """
        now = timezone.now()

        Coupon.objects.create(
            code="LIVE",
            name_ar="جارٍ",
            name_en="Live",
            kind="FIXED",
            value=Decimal("5.00"),
            starts_at=now - timedelta(days=1),
        )
        Coupon.objects.create(
            code="SOON",
            name_ar="قادم",
            name_en="Soon",
            kind="FIXED",
            value=Decimal("5.00"),
            starts_at=now + timedelta(days=7),
        )

        running = admin_client.get(reverse("v1:promotions:coupons"), {"status": "running"})
        scheduled = admin_client.get(reverse("v1:promotions:coupons"), {"status": "scheduled"})

        assert [row["code"] for row in running.data["results"]] == ["LIVE"]
        assert [row["code"] for row in scheduled.data["results"]] == ["SOON"]

    def test_the_running_flags_are_exposed(self, admin_client):
        """The admin needs "why does it not work?", not "enabled: yes" alone."""
        Coupon.objects.create(
            code="DONE",
            name_ar="منتهٍ",
            name_en="Done",
            kind="FIXED",
            value=Decimal("5.00"),
            usage_limit=1,
            usage_count=1,
        )

        response = admin_client.get(reverse("v1:promotions:coupons"))
        row = response.data["results"][0]

        assert row["is_exhausted"] is True
        assert row["is_running"] is False


# ═══════════════════════════════════════════════════════════
#  Privacy
# ═══════════════════════════════════════════════════════════


def test_the_coupon_list_is_never_public():
    """
    ⚠️  Exposing them makes every visitor try the highest available discount
        instead of the code they were sent in their campaign — so every targeted
        campaign collapses.
    """
    assert APIClient().get(reverse("v1:promotions:coupons")).status_code in (401, 403)


def test_a_customer_cannot_read_redemptions():
    customer = User.objects.create_user(email="c@test.local", password=PASSWORD)
    customer.is_active = True
    customer.save()

    client = APIClient()
    client.force_authenticate(user=customer)

    assert client.get(reverse("v1:promotions:redemptions")).status_code == 403
