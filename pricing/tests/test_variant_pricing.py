"""
Pricing a variant — the baseline pinned before product colours arrived.

⚠️  Until package E the variant path had almost no tests: only the import flow
    and the seed touched `ProductVariant`. These pin what the engine does with a
    variant today, so the colour work can be told apart from a regression.
"""

from decimal import Decimal

import pytest

from catalog.models import Category, Product, ProductVariant
from core.models.settings import SystemSetting
from pricing import services
from pricing.models import PriceList, PriceRule


@pytest.fixture(autouse=True)
def tax_off(db):
    """Round numbers keep a failed assertion legible — tax has its own tests."""
    SystemSetting.set("tax.enabled", False, value_type="BOOL", label_ar="ض", label_en="t")


@pytest.fixture
def product(db):
    category = Category.objects.create(name_ar="فئة", name_en="Category")
    return Product.objects.create(
        sku="V-001",
        name_ar="سكراب",
        name_en="Scrub",
        category=category,
        base_price=Decimal("100.00"),
    )


@pytest.fixture
def retail(db):
    return PriceList.objects.create(
        code="retail", name_ar="تجزئة", name_en="Retail", is_default=True
    )


def make_variant(product, sku="V-001-M", adjustment="0.00", **extra):
    return ProductVariant.objects.create(
        product=product,
        sku=sku,
        name_ar=extra.pop("name_ar", "وسط"),
        name_en=extra.pop("name_en", "Medium"),
        price_adjustment=Decimal(adjustment),
        **extra,
    )


# ═══════════════════════════════════════════════════════════
#  Baseline — the variant difference
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestVariantAdjustmentBaseline:
    def test_adjustment_is_added_to_the_base_price(self, product, retail):
        variant = make_variant(product, adjustment="15.00")

        line = services.price_for(product, 1, variant=variant)

        assert line.unit_price == Decimal("115.00")
        assert line.applied_rules == ("base_price", "variant_adjustment")

    def test_negative_adjustment_lowers_the_price(self, product, retail):
        variant = make_variant(product, adjustment="-10.00")

        assert services.price_for(product, 1, variant=variant).unit_price == Decimal("90.00")

    def test_zero_adjustment_adds_no_marker(self, product, retail):
        variant = make_variant(product)

        line = services.price_for(product, 1, variant=variant)

        assert line.unit_price == Decimal("100.00")
        assert "variant_adjustment" not in line.applied_rules

    def test_variant_specific_rule_replaces_the_base_then_adjusts(self, product, retail):
        variant = make_variant(product, adjustment="5.00")
        PriceRule.objects.create(
            price_list=retail, product=product, variant=variant, unit_price=Decimal("80.00")
        )

        line = services.price_for(product, 1, variant=variant)

        assert line.unit_price == Decimal("85.00")
        assert line.applied_rules == ("price_rule", "variant_adjustment")
