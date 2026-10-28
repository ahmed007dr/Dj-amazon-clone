"""
The cart and a variant — the baseline pinned before product colours arrived.

⚠️  Until package E the cart's variant path was exercised by nothing: the API
    accepted any variant id and the UI alone enforced "pick a size first".
"""

from decimal import Decimal

import pytest
from django.apps import apps

from accounts.models import AccountType, User
from cart import services
from cart.models import CartLine
from catalog.models import Category, Product, ProductVariant
from core.errors import BusinessError
from inventory import services as inventory_services

PASSWORD = "Str0ng-Test-Pass!23"


@pytest.fixture
def location(db):
    return apps.get_model("inventory", "StockLocation").objects.create(
        code="main", name_ar="الرئيسي", name_en="Main", is_default=True
    )


@pytest.fixture(autouse=True)
def default_policy(db):
    from django.core.management import call_command

    call_command("seed_access_policies", verbosity=0)


@pytest.fixture
def user(db):
    user = User.objects.create_user(
        email="buyer@test.local", password=PASSWORD, account_type=AccountType.STUDENT
    )
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def product(db, location):
    from access.models import AccessPolicy

    category = Category.objects.create(name_ar="فئة", name_en="Category")
    return Product.objects.create(
        sku="CV-001",
        name_ar="سكراب",
        name_en="Scrub",
        category=category,
        base_price=Decimal("100.00"),
        access_policy=AccessPolicy.objects.get(code="public"),
    )


@pytest.fixture
def small(product, location):
    variant = ProductVariant.objects.create(
        product=product,
        sku="CV-001-S",
        name_ar="صغير",
        name_en="Small",
        price_adjustment=Decimal("10.00"),
    )
    inventory_services.receive(product, 4, Decimal("50.00"), location=location, variant=variant)
    return variant


@pytest.fixture
def large(product, location):
    variant = ProductVariant.objects.create(
        product=product, sku="CV-001-L", name_ar="كبير", name_en="Large"
    )
    inventory_services.receive(product, 20, Decimal("50.00"), location=location, variant=variant)
    return variant


@pytest.fixture
def cart(user):
    return services.get_active_cart(user=user)


@pytest.mark.django_db
class TestVariantLines:
    def test_a_variant_line_is_stored_with_its_variant(self, cart, product, small, user):
        line = services.add_line(cart, product, 2, variant=small, user=user)

        assert line.variant_id == small.pk

    def test_two_variants_are_two_lines(self, cart, product, small, large, user):
        services.add_line(cart, product, 1, variant=small, user=user)
        services.add_line(cart, product, 1, variant=large, user=user)

        assert cart.lines.count() == 2

    def test_same_variant_accumulates(self, cart, product, small, user):
        services.add_line(cart, product, 1, variant=small, user=user)
        services.add_line(cart, product, 2, variant=small, user=user)

        assert cart.lines.get().quantity == 3

    def test_stock_is_checked_on_the_variant_not_the_product(
        self, cart, product, small, large, user
    ):
        """Large has 20 in stock — Small's 4 is still the limit for a Small line."""
        with pytest.raises(BusinessError) as failure:
            services.add_line(cart, product, 5, variant=small, user=user)

        assert failure.value.code == "INSUFFICIENT_STOCK"

    def test_the_total_after_accumulating_is_what_is_checked(self, cart, product, small, user):
        services.add_line(cart, product, 3, variant=small, user=user)

        with pytest.raises(BusinessError):
            services.add_line(cart, product, 2, variant=small, user=user)

    def test_set_quantity_respects_the_variant_stock(self, cart, product, small, user):
        line = services.add_line(cart, product, 1, variant=small, user=user)

        with pytest.raises(BusinessError):
            services.set_quantity(cart, line, 5)

    def test_pricing_in_the_snapshot_includes_the_variant_difference(
        self, cart, product, small, user
    ):
        services.add_line(cart, product, 2, variant=small, user=user)

        snapshot = services.revalidate(cart, user=user)

        (_product, _quantity, variant), priced = snapshot.lines[0]
        assert variant == small
        assert priced.unit_price == Decimal("110.00")

    def test_stock_that_ran_out_flags_the_line(self, cart, product, small, location, user):
        services.add_line(cart, product, 4, variant=small, user=user)
        inventory_services.sell_immediately(product, 3, location=location, variant=small)

        snapshot = services.revalidate(cart, user=user)

        assert snapshot.has_issues
        assert snapshot.issues[0].code == "INSUFFICIENT_STOCK"

    def test_guest_merge_keeps_the_variant(self, product, small, user):
        guest = services.get_active_cart(session_key="guest-key-1")
        services.add_line(guest, product, 2, variant=small)

        merged = services.merge_guest_cart(user, "guest-key-1")

        assert CartLine.objects.get(cart=merged).variant_id == small.pk
