"""
"Price before discount" (compare-at) — the catalogue's side.

⚠️  Three things are guarded here:

      1. the arithmetic (`catalog.compare_at`) — strictly greater, rounded **down**;
      2. the rule that it must exceed the price, on **every** write path: model,
         admin product API, admin colour API;
      3. the storefront payloads — list and detail — which show it only when it is
         above the price the viewer pays, with no query per card.

    Prices that depend on a price list (a student's) live in
    `pricing/tests/test_compare_at_display.py`: `catalog` may not import `pricing`.
"""

from decimal import Decimal

import pytest
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient

from access.models import AccessPolicy
from accounts.models import AccountType, User
from catalog import compare_at
from catalog.models import Category, Product, ProductColor, ProductKind
from core.models.audit import AuditAction, AuditLog
from core.testing import grant_all_domains

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


# ═══════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════


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
        email="cmp-admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
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


def draft(category, **overrides) -> dict:
    body = {
        "sku": "CMP-NEW",
        "name_ar": "شاش طبي",
        "name_en": "Medical gauze",
        "kind": ProductKind.SUPPLY,
        "category": str(category.pk),
        "base_price": "80.00",
    }
    body.update(overrides)
    return body


def list_row(client, product):
    response = client.get(reverse("v1:catalog:products"))
    assert response.status_code == 200
    return next(row for row in response.data["results"] if row["sku"] == product.sku)


def detail(client, product):
    response = client.get(reverse("v1:catalog:product-detail", args=[product.slug]))
    assert response.status_code == 200
    return response.data


# ═══════════════════════════════════════════════════════════
#  The arithmetic
# ═══════════════════════════════════════════════════════════


class TestArithmetic:
    def test_it_is_shown_only_when_strictly_above_the_price(self):
        assert compare_at.shown_compare_at(Decimal("100"), Decimal("80")) == Decimal("100")
        assert compare_at.shown_compare_at(Decimal("80"), Decimal("80")) is None
        assert compare_at.shown_compare_at(Decimal("70"), Decimal("80")) is None
        assert compare_at.shown_compare_at(None, Decimal("80")) is None

    @pytest.mark.parametrize(
        ("old", "now", "expected"),
        [
            ("100.00", "80.00", 20),
            ("30.00", "24.00", 20),  # 0.2 is not exact in a float — cents are
            ("100.00", "80.01", 19),  # 19.99 % is 19, never a flattering 20
            ("3.00", "2.00", 33),  # 33.33 %
            ("100.00", "99.50", 0),  # 0.5 % — shown, but not worth a badge
            ("100.00", "0.00", 100),  # free
        ],
    )
    def test_the_percentage_is_rounded_down(self, old, now, expected):
        assert compare_at.discount_percent(Decimal(old), Decimal(now)) == expected

    def test_no_percentage_when_nothing_is_shown(self):
        assert compare_at.discount_percent(Decimal("80"), Decimal("80")) is None
        assert compare_at.discount_percent(None, Decimal("80")) is None

    def test_equal_and_lower_are_errors(self):
        assert compare_at.compare_at_error(Decimal("80"), Decimal("80")) is not None
        assert compare_at.compare_at_error(Decimal("79.99"), Decimal("80")) is not None
        assert compare_at.compare_at_error(Decimal("80.01"), Decimal("80")) is None
        assert compare_at.compare_at_error(None, Decimal("80")) is None

    def test_the_message_is_bilingual(self):
        message = compare_at.compare_at_error(Decimal("1"), Decimal("2"))
        assert "السعر قبل الخصم" in message
        assert "Price before discount" in message


# ═══════════════════════════════════════════════════════════
#  Model validation (the Django panel goes through `full_clean`)
# ═══════════════════════════════════════════════════════════


class TestModelClean:
    def test_a_product_compare_at_must_exceed_the_base_price(self, category):
        product = Product(
            sku="M-1", name_ar="أ", name_en="a", category=category,
            base_price=Decimal("50"), compare_at_price=Decimal("50"),
        )  # fmt: skip
        with pytest.raises(ValidationError) as error:
            product.clean()
        assert "compare_at_price" in error.value.message_dict

        product.compare_at_price = Decimal("50.01")
        product.clean()

    def test_a_colour_is_judged_against_its_own_price_else_the_products(self, category):
        product = Product.objects.create(
            sku="M-2", name_ar="ب", name_en="b", category=category, base_price=Decimal("100")
        )
        inherits = ProductColor(product=product, name_ar="أ", name_en="A", compare_at_price=100)
        with pytest.raises(ValidationError):
            inherits.clean()  # equal to the product price it inherits

        own = ProductColor(
            product=product, name_ar="ب", name_en="B",
            price_override=Decimal("60"), compare_at_price=Decimal("80"),
        )  # fmt: skip
        own.clean()  # above its own 60, though below the product's 100


# ═══════════════════════════════════════════════════════════
#  Admin product API
# ═══════════════════════════════════════════════════════════


class TestAdminProductApi:
    url = staticmethod(lambda: reverse("v1:catalog:admin-products"))

    def test_create_with_a_valid_compare_at(self, admin_client, category):
        response = admin_client.post(
            self.url(), draft(category, compare_at_price="100.00"), format="json"
        )

        assert response.status_code == 201, response.content
        assert response.data["compare_at_price"] == "100.00"
        assert Product.objects.get(sku="CMP-NEW").compare_at_price == Decimal("100.00")

    @pytest.mark.parametrize("value", ["80.00", "79.99", "0.00"])
    def test_equal_or_lower_is_rejected_with_a_field_error(self, admin_client, category, value):
        response = admin_client.post(
            self.url(), draft(category, compare_at_price=value), format="json"
        )

        assert response.status_code == 400
        fields = response.json()["fields"]
        assert "compare_at_price" in fields
        message = fields["compare_at_price"][0]["message"]
        assert "Price before discount" in message and "السعر قبل الخصم" in message
        assert not Product.objects.filter(sku="CMP-NEW").exists()

    def test_it_is_optional_and_can_be_cleared(self, admin_client, category):
        created = admin_client.post(self.url(), draft(category), format="json")
        assert created.status_code == 201
        assert created.data["compare_at_price"] is None

        product_id = created.data["id"]
        detail_url = reverse("v1:catalog:admin-product-detail", args=[product_id])
        assert (
            admin_client.patch(
                detail_url, {"compare_at_price": "120.00"}, format="json"
            ).status_code
            == 200
        )
        cleared = admin_client.patch(detail_url, {"compare_at_price": None}, format="json")

        assert cleared.status_code == 200
        assert cleared.data["compare_at_price"] is None

    def test_a_patch_is_judged_against_the_stored_base_price(self, admin_client, category):
        created = admin_client.post(
            self.url(), draft(category, compare_at_price="100.00"), format="json"
        )
        detail_url = reverse("v1:catalog:admin-product-detail", args=[created.data["id"]])

        # only the compare-at moves: still judged against the stored 80.00
        assert (
            admin_client.patch(detail_url, {"compare_at_price": "80.00"}, format="json").status_code
            == 400
        )

    def test_raising_the_price_past_an_unchanged_compare_at_is_rejected(
        self, admin_client, category
    ):
        created = admin_client.post(
            self.url(), draft(category, compare_at_price="100.00"), format="json"
        )
        detail_url = reverse("v1:catalog:admin-product-detail", args=[created.data["id"]])

        response = admin_client.patch(detail_url, {"base_price": "100.00"}, format="json")

        assert response.status_code == 400
        assert "compare_at_price" in response.json()["fields"]
        assert Product.objects.get(pk=created.data["id"]).base_price == Decimal("80.00")

    def test_a_negative_value_is_rejected(self, admin_client, category):
        response = admin_client.post(
            self.url(), draft(category, compare_at_price="-1"), format="json"
        )
        assert response.status_code == 400


# ═══════════════════════════════════════════════════════════
#  Admin colour API
# ═══════════════════════════════════════════════════════════


class TestAdminColorApi:
    @pytest.fixture
    def product(self, category, public_policy, location):
        return make_product(category, public_policy, location, price="100.00")

    def colors_url(self, product):
        return reverse("v1:catalog:admin-product-colors", args=[product.pk])

    def post(self, client, product, **extra):
        body = {"name_ar": "أزرق", "name_en": "Blue", "hex": "#1E40AF", **extra}
        return client.post(self.colors_url(product), body, format="json")

    def test_a_colour_without_a_price_of_its_own_is_judged_against_the_products(
        self, admin_client, product
    ):
        assert self.post(admin_client, product, compare_at_price="100.00").status_code == 400
        created = self.post(admin_client, product, compare_at_price="130.00")

        assert created.status_code == 201, created.content
        assert created.data["compare_at_price"] == "130.00"

    def test_a_colour_with_its_own_price_is_judged_against_that(self, admin_client, product):
        # 80 is above the colour's own 60, though below the product's 100
        created = self.post(admin_client, product, price_override="60.00", compare_at_price="80.00")
        assert created.status_code == 201, created.content

        rejected = self.post(
            admin_client, product, name_ar="أحمر", name_en="Red",
            price_override="60.00", compare_at_price="60.00",
        )  # fmt: skip
        assert rejected.status_code == 400
        assert "compare_at_price" in rejected.json()["fields"]

    def test_clearing_the_price_override_is_rechecked(self, admin_client, product):
        created = self.post(admin_client, product, price_override="60.00", compare_at_price="80.00")
        url = reverse(
            "v1:catalog:admin-product-color-detail", args=[product.pk, created.data["id"]]
        )

        # back on the product's 100 the colour's old price of 80 is no longer above it
        assert admin_client.patch(url, {"price_override": None}, format="json").status_code == 400

    def test_a_colour_compare_at_change_is_a_price_change_in_the_history(
        self, admin_client, product
    ):
        created = self.post(admin_client, product)
        url = reverse(
            "v1:catalog:admin-product-color-detail", args=[product.pk, created.data["id"]]
        )

        admin_client.patch(url, {"compare_at_price": "150.00"}, format="json")

        entry = AuditLog.objects.filter(
            content_type=ContentType.objects.get_for_model(Product),
            object_id=str(product.pk),
            action=AuditAction.PRICE_CHANGE,
        ).first()
        assert entry is not None
        assert entry.changes["compare_at_price"] == {"old": None, "new": "150.00"}
