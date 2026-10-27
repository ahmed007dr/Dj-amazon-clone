"""
Stock on a variant — the baseline pinned before product colours arrived.

⚠️  Stock is keyed `(product, variant, location)`. A size M glove runs out while
    L is in stock, so every figure below is per variant, and "no variant"
    (`variant=None`) is a row of its own — not a total.
"""

from decimal import Decimal

import pytest

from catalog.models import Category, Product, ProductVariant
from core.errors import BusinessError
from inventory import services
from inventory.models import Stock, StockLocation, StockMovement


@pytest.fixture
def location(db):
    return StockLocation.objects.create(
        code="main", name_ar="الرئيسي", name_en="Main", is_default=True
    )


@pytest.fixture
def product(db):
    category = Category.objects.create(name_ar="فئة", name_en="Category")
    return Product.objects.create(
        sku="VS-001", name_ar="سكراب", name_en="Scrub", category=category
    )


@pytest.fixture
def small(product):
    return ProductVariant.objects.create(
        product=product, sku="VS-001-S", name_ar="صغير", name_en="Small"
    )


@pytest.fixture
def large(product):
    return ProductVariant.objects.create(
        product=product, sku="VS-001-L", name_ar="كبير", name_en="Large"
    )


@pytest.mark.django_db
class TestPerVariantBalances:
    def test_available_quantity_is_exact_per_variant(self, product, small, large, location):
        services.receive(product, 5, Decimal("10.00"), location=location, variant=small)
        services.receive(product, 3, Decimal("10.00"), location=location, variant=large)
        services.receive(product, 7, Decimal("10.00"), location=location)

        assert services.available_quantity(product, variant=small) == 5
        assert services.available_quantity(product, variant=large) == 3
        assert services.available_quantity(product) == 7, "بلا نسخة صفّ مستقل"

    def test_availability_for_sums_every_variant(self, product, small, large, location):
        services.receive(product, 5, Decimal("10.00"), location=location, variant=small)
        services.receive(product, 3, Decimal("10.00"), location=location, variant=large)

        result = services.availability_for([product.pk])

        assert result[str(product.pk)].available == 8
        assert result[str(product.pk)].is_available

    def test_reserve_is_limited_to_the_variants_own_stock(self, product, small, large, location):
        services.receive(product, 5, Decimal("10.00"), location=location, variant=small)
        services.receive(product, 50, Decimal("10.00"), location=location, variant=large)

        with pytest.raises(BusinessError):
            services.reserve(product, 6, location=location, variant=small)

        services.reserve(product, 5, location=location, variant=small)
        assert services.available_quantity(product, variant=small) == 0
        assert services.available_quantity(product, variant=large) == 50

    def test_sale_deducts_the_variant_and_records_it_on_the_movement(
        self, product, small, location
    ):
        services.receive(product, 10, Decimal("10.00"), location=location, variant=small)

        movements = services.sell_immediately(product, 4, location=location, variant=small)

        assert services.available_quantity(product, variant=small) == 6
        assert all(movement.variant_id == small.pk for movement in movements)

    def test_in_stock_filter_sees_any_variant_with_stock(self, product, small, large, location):
        services.receive(product, 2, Decimal("10.00"), location=location, variant=large)

        assert Product.objects.filter(services.in_stock_filter()).filter(pk=product.pk).exists()

    def test_in_stock_filter_hides_a_product_with_every_variant_empty(
        self, product, small, large, location
    ):
        services.receive(product, 2, Decimal("10.00"), location=location, variant=large)
        services.sell_immediately(product, 2, location=location, variant=large)

        assert not Product.objects.filter(services.in_stock_filter()).filter(pk=product.pk).exists()

    def test_each_variant_has_one_stock_row_per_location(self, product, small, location):
        services.receive(product, 2, Decimal("10.00"), location=location, variant=small)
        services.receive(product, 3, Decimal("10.00"), location=location, variant=small)

        assert Stock.objects.filter(product=product, variant=small, location=location).count() == 1
        assert StockMovement.objects.filter(variant=small).count() == 2
