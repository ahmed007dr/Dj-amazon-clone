"""
Pricing management from the panel.

⚠️  The `pricing` domain had **no `urls.py` at all**: every price list, rule and
    discount was managed from the Django panel alone.

⚠️  And what is guarded here: no public endpoint · the default is never deleted ·
    a price change is recorded with its old value.
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
from catalog.models import Category, Product
from pricing.models import PriceList, PriceRule

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_user(
        email="price-admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    admin.is_active = True
    admin.save()
    apps.get_model("administration", "AdminProfile").objects.create(user=admin)
    grant_all_domains(admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture
def product(db):
    category = Category.objects.create(name_ar="فئة", name_en="Category")
    return Product.objects.create(sku="PRC-1", name_ar="منتج", name_en="Product", category=category)


@pytest.fixture
def price_list(db):
    return PriceList.objects.create(code="retail", name_ar="تجزئة", name_en="Retail")


# ═══════════════════════════════════════════════════════════
#  Privacy
# ═══════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "route",
    ["v1:pricing:lists", "v1:pricing:rules", "v1:pricing:overrides", "v1:promotions:coupons"],
)
def test_pricing_is_never_public(route):
    """
    ⚠️  **The pricing structure is among the most valuable things the store owns.**

        Exposing the price lists hands a competitor your whole structure; and
        exposing the coupons makes every visitor try the highest available
        discount instead of the code they were sent.
    """
    assert APIClient().get(reverse(route)).status_code in (401, 403)


def test_a_customer_is_refused(product):
    customer = User.objects.create_user(email="c@test.local", password=PASSWORD)
    customer.is_active = True
    customer.save()

    client = APIClient()
    client.force_authenticate(user=customer)

    assert client.get(reverse("v1:pricing:lists")).status_code == 403


# ═══════════════════════════════════════════════════════════
#  Price lists
# ═══════════════════════════════════════════════════════════


class TestPriceLists:
    def test_a_list_is_created(self, admin_client):
        response = admin_client.post(
            reverse("v1:pricing:lists"),
            {"code": "students", "name_ar": "طلاب", "name_en": "Students", "kind": "STUDENT"},
            format="json",
        )

        assert response.status_code == 201
        assert PriceList.objects.filter(code="students").exists()

    def test_an_end_before_start_is_refused(self, admin_client):
        """
        ⚠️  A list that never applies passes silently: each field is valid on its
            own, and the error only surfaces when a customer complains they cannot see their price.
        """
        today = timezone.localdate()

        response = admin_client.post(
            reverse("v1:pricing:lists"),
            {
                "code": "broken",
                "name_ar": "مكسورة",
                "name_en": "Broken",
                "valid_from": str(today),
                "valid_to": str(today - timedelta(days=1)),
            },
            format="json",
        )

        assert response.status_code == 400
        assert "valid_to" in response.data["fields"]

    def test_the_default_list_is_not_deleted(self, admin_client):
        """Deleting it leaves every customer with no applicable list — so no product has a price."""
        default = PriceList.objects.create(
            code="base", name_ar="أساسية", name_en="Base", is_default=True
        )

        response = admin_client.delete(reverse("v1:pricing:list-detail", args=[default.pk]))
        assert response.status_code == 409

    def test_a_list_with_rules_is_not_deleted(self, admin_client, price_list, product):
        PriceRule.objects.create(
            price_list=price_list, product=product, unit_price=Decimal("10.00")
        )

        response = admin_client.delete(reverse("v1:pricing:list-detail", args=[price_list.pk]))

        assert response.status_code == 409
        assert "1" in response.data["detail"]

    def test_rule_count_exposes_an_empty_list(self, admin_client, price_list):
        """
        ⚠️  An enabled list with no rules means its customers see the retail
            price while believing they are on the wholesale price — with nothing
            to indicate the mistake.
        """
        response = admin_client.get(reverse("v1:pricing:lists"))
        assert response.data[0]["rule_count"] == 0


# ═══════════════════════════════════════════════════════════
#  Pricing rules
# ═══════════════════════════════════════════════════════════


class TestPriceRules:
    def test_quantity_tiers_are_rows_not_fields(self, admin_client, price_list, product):
        """Any number of tiers with no migration — which is why rows were chosen."""
        for quantity, price in ((1, "20.00"), (10, "18.00"), (50, "15.00")):
            response = admin_client.post(
                reverse("v1:pricing:rules"),
                {
                    "price_list": str(price_list.pk),
                    "product": str(product.pk),
                    "min_quantity": quantity,
                    "unit_price": price,
                },
                format="json",
            )
            assert response.status_code == 201, response.data

        assert PriceRule.objects.filter(product=product).count() == 3

    def test_rules_are_listed_largest_tier_first(self, admin_client, price_list, product):
        """
        ⚠️  The same matching order as in `price_for` — so what the admin sees
            is what the engine reads, not another order that confuses them.
        """
        for quantity in (1, 50, 10):
            PriceRule.objects.create(
                price_list=price_list,
                product=product,
                min_quantity=quantity,
                unit_price=Decimal("10.00"),
            )

        response = admin_client.get(reverse("v1:pricing:rules"))
        tiers = [row["min_quantity"] for row in response.data["results"]]

        assert tiers == [50, 10, 1]

    def test_a_duplicate_tier_is_refused(self, admin_client, price_list, product):
        """Two tiers at the same quantity mean two prices for the same case."""
        body = {
            "price_list": str(price_list.pk),
            "product": str(product.pk),
            "min_quantity": 5,
            "unit_price": "12.00",
        }
        admin_client.post(reverse("v1:pricing:rules"), body, format="json")

        response = admin_client.post(reverse("v1:pricing:rules"), body, format="json")
        assert response.status_code == 400

    def test_a_price_change_records_the_old_value(self, admin_client, price_list, product):
        """
        ⚠️  "When did this item become this price?" is a question asked months
            later, answerable only from a value stored in the log.
        """
        rule = PriceRule.objects.create(
            price_list=price_list, product=product, unit_price=Decimal("20.00")
        )

        admin_client.patch(
            reverse("v1:pricing:rule-detail", args=[rule.pk]),
            {"unit_price": "17.50"},
            format="json",
        )

        entry = (
            apps.get_model("core", "AuditLog")
            .objects.filter(action="PRICE_CHANGE", object_repr__contains="PRC-1")
            .order_by("-created_at")
            .first()
        )

        assert entry is not None
        assert entry.changes["unit_price"]["old"] == "20.00"
        assert entry.changes["unit_price"]["new"] == "17.50"


# ═══════════════════════════════════════════════════════════
#  Promotional discounts
# ═══════════════════════════════════════════════════════════


class TestOverrides:
    def test_a_percentage_above_hundred_is_refused(self, admin_client, product):
        """A rate above 100% means a negative price — the store pays the customer."""
        response = admin_client.post(
            reverse("v1:pricing:overrides"),
            {
                "product": str(product.pk),
                "discount_kind": "PERCENTAGE",
                "discount_value": "150.00",
            },
            format="json",
        )

        assert response.status_code == 400
        assert "discount_value" in response.data["fields"]

    def test_running_filter_uses_the_query_not_python(self, admin_client, product):
        """
        ⚠️  Filtering after pagination gives short pages with nobody noticing.
        """
        now = timezone.now()

        admin_client.post(
            reverse("v1:pricing:overrides"),
            {
                "product": str(product.pk),
                "discount_kind": "FIXED",
                "discount_value": "5.00",
                "starts_at": (now - timedelta(days=1)).isoformat(),
            },
            format="json",
        )
        admin_client.post(
            reverse("v1:pricing:overrides"),
            {
                "product": str(product.pk),
                "discount_kind": "FIXED",
                "discount_value": "7.00",
                "starts_at": (now + timedelta(days=5)).isoformat(),
            },
            format="json",
        )

        response = admin_client.get(reverse("v1:pricing:overrides"), {"running": "true"})
        assert response.data["count"] == 1
