"""
"Price before discount" — what the storefront and the history receive.

⚠️  The server decides whether the old price is shown; these tests pin that decision
    for the list, the detail, the variants and the colours, plus the audit trail and the
    query count of a list page.

    Prices that depend on a price list live in `pricing/tests/test_compare_at_display.py`
    (`catalog` may not import `pricing`).
"""

from decimal import Decimal

import pytest
from django.apps import apps
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from access.models import AccessPolicy
from accounts.models import AccountType, User
from catalog import audit
from catalog import colors as color_services
from catalog.models import Category, Product, ProductVariant
from core.models.audit import AuditAction, AuditLog
from core.testing import grant_all_domains

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


@pytest.fixture
def category(db):
    return Category.objects.create(name_ar="مستلزمات", name_en="Supplies")


@pytest.fixture
def location(db):
    return apps.get_model("inventory", "StockLocation").objects.create(
        code="main", name_ar="الرئيسي", name_en="Main", is_default=True
    )


@pytest.fixture
def public_policy(db):
    from django.core.management import call_command

    call_command("seed_access_policies", verbosity=0)
    return AccessPolicy.objects.get(code="public")


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_user(
        email="cmp-admin2@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    admin.is_active = True
    admin.save()
    apps.get_model("administration", "AdminProfile").objects.create(user=admin)
    grant_all_domains(admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


def make_product(category, public_policy, location, sku="CMP-1", price="80.00", compare=None):
    """A published, stocked product — an unstocked one is not in the public catalogue."""
    product = Product.objects.create(
        sku=sku,
        name_ar=f"منتج {sku}",
        name_en=f"Product {sku}",
        category=category,
        base_price=Decimal(price),
        compare_at_price=None if compare is None else Decimal(compare),
        access_policy=public_policy,
    )
    apps.get_model("inventory", "Stock").objects.create(
        product=product, location=location, quantity_physical=10
    )
    return product


def list_row(product):
    response = APIClient().get(reverse("v1:catalog:products"))
    assert response.status_code == 200
    return next(row for row in response.data["results"] if row["sku"] == product.sku)


def detail(product):
    response = APIClient().get(reverse("v1:catalog:product-detail", args=[product.slug]))
    assert response.status_code == 200
    return response.data


def colour_row(data, color):
    return next(row for row in data["colors"] if row["id"] == str(color.pk))


# ═══════════════════════════════════════════════════════════
#  Audit
# ═══════════════════════════════════════════════════════════


class TestAudit:
    def draft(self, category, **extra):
        return {
            "sku": "AU-1",
            "name_ar": "شاش",
            "name_en": "Gauze",
            "kind": "SUPPLY",
            "category": str(category.pk),
            "base_price": "80.00",
            **extra,
        }

    def test_the_snapshot_tracks_the_field(self, category):
        product = Product.objects.create(
            sku="AU-0",
            name_ar="أ",
            name_en="a",
            category=category,
            base_price=Decimal("10"),
            compare_at_price=Decimal("12"),
        )
        assert audit.snapshot(product)["compare_at_price"] == "12.00"

    def test_changing_it_is_a_price_change_with_old_and_new(self, admin_client, category):
        created = admin_client.post(
            reverse("v1:catalog:admin-products"), self.draft(category), format="json"
        )
        url = reverse("v1:catalog:admin-product-detail", args=[created.data["id"]])

        admin_client.patch(url, {"compare_at_price": "100.00"}, format="json")
        admin_client.patch(url, {"compare_at_price": "110.00"}, format="json")

        entries = list(
            AuditLog.objects.filter(
                object_id=created.data["id"], action=AuditAction.PRICE_CHANGE
            ).order_by("created_at", "id")
        )
        assert [entry.changes["compare_at_price"] for entry in entries] == [
            {"old": None, "new": "100.00"},
            {"old": "100.00", "new": "110.00"},
        ]

    def test_an_unchanged_value_is_not_logged(self, admin_client, category):
        created = admin_client.post(
            reverse("v1:catalog:admin-products"),
            self.draft(category, compare_at_price="100.00"),
            format="json",
        )
        url = reverse("v1:catalog:admin-product-detail", args=[created.data["id"]])
        before = AuditLog.objects.count()

        admin_client.patch(url, {"compare_at_price": "100"}, format="json")

        assert AuditLog.objects.count() == before


# ═══════════════════════════════════════════════════════════
#  The list
# ═══════════════════════════════════════════════════════════


class TestList:
    def test_it_shows_the_old_price_and_the_percentage(self, category, public_policy, location):
        product = make_product(category, public_policy, location, price="80.00", compare="100.00")

        row = list_row(product)

        assert row["price"] == "80.00"
        assert row["compare_at_price"] == "100.00"
        assert row["discount_percent"] == 20

    def test_a_product_without_one_has_null_fields(self, category, public_policy, location):
        product = make_product(category, public_policy, location, price="80.00")

        row = list_row(product)

        assert row["compare_at_price"] is None
        assert row["discount_percent"] is None
        assert row["price"] == "80.00"

    def test_a_stale_compare_at_not_above_the_price_is_hidden(
        self, category, public_policy, location
    ):
        """
        ⚠️  The server decides. A `base_price` raised by an import after the compare-at was
            typed must not leave a "was 90" beside "now 100".
        """
        product = make_product(category, public_policy, location, price="100.00")
        Product.objects.filter(pk=product.pk).update(compare_at_price=Decimal("90.00"))

        row = list_row(product)

        assert row["compare_at_price"] is None
        assert row["discount_percent"] is None

    def test_the_percentage_is_rounded_down(self, category, public_policy, location):
        product = make_product(category, public_policy, location, price="80.01", compare="100.00")

        assert list_row(product)["discount_percent"] == 19

    def test_the_query_count_does_not_grow_with_the_products(
        self, category, public_policy, location
    ):
        """⚠️  Pricing a page is a fixed number of queries — never one per card."""
        for i in range(2):
            make_product(category, public_policy, location, sku=f"N-{i}", compare="120.00")
        with CaptureQueriesContext(connection) as small:
            APIClient().get(reverse("v1:catalog:products"))

        for i in range(2, 12):
            make_product(category, public_policy, location, sku=f"N-{i}", compare="120.00")
        with CaptureQueriesContext(connection) as large:
            response = APIClient().get(reverse("v1:catalog:products"))

        assert len(response.data["results"]) == 12
        assert len(large) == len(small)


# ═══════════════════════════════════════════════════════════
#  The detail
# ═══════════════════════════════════════════════════════════


class TestDetail:
    def test_the_product_level_fields(self, category, public_policy, location):
        product = make_product(category, public_policy, location, price="80.00", compare="100.00")

        data = detail(product)

        assert data["price"] == "80.00"
        assert data["compare_at_price"] == "100.00"
        assert data["discount_percent"] == 20

    def test_a_variant_has_its_own_price_and_the_same_difference_on_the_old_price(
        self, category, public_policy, location
    ):
        product = make_product(category, public_policy, location, price="80.00", compare="100.00")
        ProductVariant.objects.create(
            product=product,
            sku="CMP-1-XL",
            name_ar="كبير",
            name_en="XL",
            price_adjustment=Decimal("20.00"),
        )

        row = detail(product)["variants"][0]

        # 80 + 20 = 100 now and 100 + 20 = 120 before: the saving is 20 / 120 = 16 %
        assert row["price"] == "100.00"
        assert row["compare_at_price"] == "120.00"
        assert row["discount_percent"] == 16

    def test_a_colour_inheriting_the_product_price_inherits_its_compare_at(
        self, category, public_policy, location
    ):
        product = make_product(category, public_policy, location, price="80.00", compare="100.00")
        blue = color_services.create_color(product, name_ar="أزرق", name_en="Blue", hex="#1E40AF")

        row = colour_row(detail(product), blue)

        assert row["price"] == "80.00"
        assert row["compare_at_price"] == "100.00"
        assert row["discount_percent"] == 20

    def test_a_colour_with_its_own_price_and_its_own_compare_at(
        self, category, public_policy, location
    ):
        product = make_product(category, public_policy, location, price="80.00", compare="100.00")
        green = color_services.create_color(
            product,
            name_ar="أخضر",
            name_en="Green",
            hex="#15803D",
            price_override=Decimal("60.00"),
            compare_at_price=Decimal("90.00"),
        )

        row = colour_row(detail(product), green)

        assert row["price"] == "60.00"
        assert row["compare_at_price"] == "90.00"
        assert row["discount_percent"] == 33

    def test_a_colour_with_its_own_price_does_not_borrow_the_products_old_price(
        self, category, public_policy, location
    ):
        """The product's old 100 described the product's 80, not this colour's 60."""
        product = make_product(category, public_policy, location, price="80.00", compare="100.00")
        red = color_services.create_color(
            product,
            name_ar="أحمر",
            name_en="Red",
            hex="#B91C1C",
            price_override=Decimal("60.00"),
        )

        row = colour_row(detail(product), red)

        assert row["price"] == "60.00"
        assert row["compare_at_price"] is None
        assert row["discount_percent"] is None

    def test_without_a_provider_the_reference_price_is_the_answer(
        self, category, public_policy, location
    ):
        """With `pricing` absent the catalogue still answers, honestly, with `base_price`."""
        from core import price_facts

        product = make_product(category, public_policy, location, price="80.00", compare="100.00")
        saved = dict(price_facts._PROVIDERS)
        price_facts._PROVIDERS.clear()
        try:
            data = detail(product)
        finally:
            price_facts._PROVIDERS.update(saved)

        assert data["price"] == "80.00"
        assert data["compare_at_price"] == "100.00"
