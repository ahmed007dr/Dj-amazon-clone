"""
The colour step in the pricing engine, and the variant→product fallback fix.

Precedence (owner's decision): price-list / student rule → colour price →
product price → + variant difference → promotion.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from accounts.models import AccountType, User
from catalog.models import Category, Product, ProductColor, ProductVariant
from core.models.settings import SystemSetting
from pricing import services
from pricing.models import DiscountKind, PriceList, PriceOverride, PriceRule

PASSWORD = "Str0ng-Test-Pass!23"


@pytest.fixture(autouse=True)
def tax_off(db):
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


@pytest.fixture
def student_list(db):
    return PriceList.objects.create(
        code="student",
        name_ar="طلاب",
        name_en="Student",
        account_types=[AccountType.STUDENT],
        priority=10,
    )


@pytest.fixture
def student(db):
    user = User.objects.create_user(
        email="stu@test.local", password=PASSWORD, account_type=AccountType.STUDENT
    )
    user.is_active = True
    user.save()
    return user


def make_variant(product, sku="V-001-M", adjustment="0.00", **extra):
    return ProductVariant.objects.create(
        product=product,
        sku=sku,
        name_ar=extra.pop("name_ar", "وسط"),
        name_en=extra.pop("name_en", "Medium"),
        price_adjustment=Decimal(adjustment),
        **extra,
    )


def make_color(product, name_en="Blue", price=None, hex_="#1E40AF"):
    color = ProductColor.objects.create(
        product=product,
        name_ar="أزرق" if name_en == "Blue" else "أحمر",
        name_en=name_en,
        hex=hex_,
        price_override=Decimal(price) if price is not None else None,
    )
    variant = make_variant(
        product, sku=f"V-001-{name_en.upper()}", name_ar=color.name_ar, name_en=name_en, color=color
    )
    return color, variant


# ═══════════════════════════════════════════════════════════
#  The fallback fix — a variant line no longer ignores product-level rules
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestProductLevelFallback:
    def test_product_rule_applies_to_a_variant_line(self, product, retail, student_list, student):
        """
        ⚠️  **The latent bug this fixes.**

            `_rule_for` matched the variant EXACTLY, so a customer on the student
            list paid the full base price for any variant while the plain product
            line got their list price — the same item, two prices.
        """
        variant = make_variant(product, adjustment="10.00")
        PriceRule.objects.create(
            price_list=student_list, product=product, unit_price=Decimal("75.00")
        )

        line = services.price_for(product, 1, user=student, variant=variant)

        assert line.unit_price == Decimal("85.00"), "قاعدة المنتج + فرق النسخة"
        assert line.applied_rules[0] == "price_rule"

    def test_variant_rule_wins_over_the_product_rule(self, product, retail):
        variant = make_variant(product)
        PriceRule.objects.create(price_list=retail, product=product, unit_price=Decimal("90.00"))
        PriceRule.objects.create(
            price_list=retail, product=product, variant=variant, unit_price=Decimal("70.00")
        )

        assert services.price_for(product, 1, variant=variant).unit_price == Decimal("70.00")

    def test_the_plain_product_line_ignores_variant_rules(self, product, retail):
        variant = make_variant(product)
        PriceRule.objects.create(
            price_list=retail, product=product, variant=variant, unit_price=Decimal("70.00")
        )

        assert services.price_for(product, 1).unit_price == Decimal("100.00")

    def test_quantity_tier_falls_back_per_tier(self, product, retail):
        """A variant rule at ≥10 does not hide the product's ≥1 price for quantity 3."""
        variant = make_variant(product)
        PriceRule.objects.create(price_list=retail, product=product, unit_price=Decimal("90.00"))
        PriceRule.objects.create(
            price_list=retail,
            product=product,
            variant=variant,
            min_quantity=10,
            unit_price=Decimal("60.00"),
        )

        assert services.price_for(product, 3, variant=variant).unit_price == Decimal("90.00")
        assert services.price_for(product, 12, variant=variant).unit_price == Decimal("60.00")

    def test_product_promo_applies_to_a_variant_line(self, product, retail):
        variant = make_variant(product)
        PriceOverride.objects.create(
            product=product,
            discount_kind=DiscountKind.PERCENTAGE,
            discount_value=Decimal("10.00"),
            starts_at=timezone.now() - timedelta(days=1),
        )

        line = services.price_for(product, 1, variant=variant)

        assert line.discount_amount == Decimal("10.00")
        assert "price_override" in line.applied_rules

    def test_variant_promo_wins_over_the_product_promo(self, product, retail):
        variant = make_variant(product)
        past = timezone.now() - timedelta(days=1)
        PriceOverride.objects.create(
            product=product,
            discount_kind=DiscountKind.PERCENTAGE,
            discount_value=Decimal("10.00"),
            starts_at=past,
        )
        PriceOverride.objects.create(
            product=product,
            variant=variant,
            discount_kind=DiscountKind.PERCENTAGE,
            discount_value=Decimal("50.00"),
            starts_at=past - timedelta(days=1),
        )

        # Exact variant first even though the product-level promo started later.
        assert services.price_for(product, 1, variant=variant).discount_amount == Decimal("50.00")


# ═══════════════════════════════════════════════════════════
#  The colour price
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestColourPrice:
    def test_colour_without_a_price_uses_the_product_price(self, product, retail):
        _color, variant = make_color(product, price=None)

        line = services.price_for(product, 1, variant=variant)

        assert line.unit_price == Decimal("100.00")
        assert line.applied_rules == ("base_price",)

    def test_colour_price_replaces_the_base_price(self, product, retail):
        _color, variant = make_color(product, price="120.00")

        line = services.price_for(product, 1, variant=variant)

        assert line.unit_price == Decimal("120.00")
        assert line.applied_rules == ("color_price",)

    def test_a_cheaper_colour_is_honoured(self, product, retail):
        _color, variant = make_color(product, price="80.00")

        assert services.price_for(product, 1, variant=variant).unit_price == Decimal("80.00")

    def test_a_zero_colour_price_is_a_price_not_an_absence(self, product, retail):
        """`0.00` is a legitimate (free) price — only `None` means "use the product's"."""
        _color, variant = make_color(product, price="0.00")

        assert services.price_for(product, 1, variant=variant).unit_price == Decimal("0.00")

    def test_price_list_rule_beats_the_colour_price(self, product, retail, student_list, student):
        """⚠️  The owner's precedence: price-list / student rule → colour → base."""
        _color, variant = make_color(product, price="120.00")
        PriceRule.objects.create(
            price_list=student_list, product=product, unit_price=Decimal("75.00")
        )

        line = services.price_for(product, 1, user=student, variant=variant)

        assert line.unit_price == Decimal("75.00")
        assert line.applied_rules == ("price_rule",)

    def test_variant_adjustment_still_stacks_on_the_colour_price(self, product, retail):
        color, _variant = make_color(product, price="120.00")
        sized = make_variant(
            product, sku="V-001-BLUE-L", adjustment="10.00", name_en="Blue L", color=color
        )

        line = services.price_for(product, 1, variant=sized)

        assert line.unit_price == Decimal("130.00")
        assert line.applied_rules == ("color_price", "variant_adjustment")

    def test_promo_discount_applies_on_top_of_the_colour_price(self, product, retail):
        _color, variant = make_color(product, price="200.00")
        PriceOverride.objects.create(
            product=product,
            discount_kind=DiscountKind.PERCENTAGE,
            discount_value=Decimal("10.00"),
            starts_at=timezone.now() - timedelta(days=1),
        )

        line = services.price_for(product, 1, variant=variant)

        assert line.unit_price == Decimal("200.00")
        assert line.discount_amount == Decimal("20.00")
        assert line.applied_rules == ("color_price", "price_override")

    def test_a_variant_without_a_colour_ignores_colour_prices(self, product, retail):
        make_color(product, price="120.00")
        plain = make_variant(product, sku="V-001-PLAIN")

        assert services.price_for(product, 1, variant=plain).unit_price == Decimal("100.00")
