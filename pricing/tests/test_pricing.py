"""
اختبارات محرك التسعير.

⚠️  هذا المحرك يستبدل **أربعة** مواضع حساب متعارضة في الكود القديم
    (الانتهاك H5). الاختبارات هنا تحرس أن يبقى مصدرًا واحدًا.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from accounts.models import AccountType, User
from catalog.models import Category, Product
from core.models.tax import TaxClass
from pricing import services
from pricing.models import DiscountKind, PriceList, PriceOverride, PriceRule

PASSWORD = "Str0ng-Test-Pass!23"


def make_user(email, account_type=AccountType.STUDENT):
    user = User.objects.create_user(email=email, password=PASSWORD, account_type=account_type)
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def tax_class(db):
    return TaxClass.objects.create(
        name_ar="قياسي",
        name_en="Standard",
        code="standard",
        rate=Decimal("14.00"),
        is_default=True,
    )


@pytest.fixture
def product(db, tax_class):
    category = Category.objects.create(name_ar="فئة", name_en="Category")
    return Product.objects.create(
        sku="P-001",
        name_ar="منتج",
        name_en="Product",
        category=category,
        base_price=Decimal("100.00"),
        tax_class=tax_class,
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


# ═══════════════════════════════════════════════════════════
#  الأساس
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestBasePricing:
    def test_falls_back_to_base_price(self, product, retail):
        line = services.price_for(product, 1)

        assert line.unit_price == Decimal("100.00")
        assert "base_price" in line.applied_rules

    def test_price_rule_overrides_base(self, product, retail):
        PriceRule.objects.create(price_list=retail, product=product, unit_price=Decimal("80.00"))
        line = services.price_for(product, 1)

        assert line.unit_price == Decimal("80.00")
        assert "price_rule" in line.applied_rules

    def test_totals_are_consistent(self, product, retail):
        line = services.price_for(product, 3)

        assert line.subtotal == Decimal("300.00")
        assert line.net == Decimal("300.00")
        assert line.tax_amount == Decimal("42.00")  # ١٤٪
        assert line.total == Decimal("342.00")


# ═══════════════════════════════════════════════════════════
#  قوائم الأسعار
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPriceLists:
    def test_account_type_selects_its_list(self, product, retail, student_list):
        PriceRule.objects.create(price_list=retail, product=product, unit_price=Decimal("100.00"))
        PriceRule.objects.create(
            price_list=student_list, product=product, unit_price=Decimal("75.00")
        )

        student = make_user("s@test.local", AccountType.STUDENT)
        doctor = make_user("d@test.local", AccountType.DOCTOR)

        assert services.price_for(product, 1, user=student).unit_price == Decimal("75.00")
        assert services.price_for(product, 1, user=doctor).unit_price == Decimal("100.00")

    def test_highest_priority_wins_on_multiple_matches(self, product, retail):
        """
        ⚠️  صيدلية قد تطابق «جملة» و«مهنيون» معًا.

        بلا أولوية صريحة يصير السعر رهن ترتيب الصفوف في قاعدة
        البيانات — أي عشوائيًا فعليًا.
        """
        low = PriceList.objects.create(
            code="wholesale",
            name_ar="جملة",
            name_en="Wholesale",
            account_types=[AccountType.PHARMACY],
            priority=5,
        )
        high = PriceList.objects.create(
            code="professional",
            name_ar="مهنيون",
            name_en="Professional",
            account_types=[AccountType.PHARMACY],
            priority=20,
        )

        PriceRule.objects.create(price_list=low, product=product, unit_price=Decimal("60.00"))
        PriceRule.objects.create(price_list=high, product=product, unit_price=Decimal("50.00"))

        pharmacy = make_user("ph@test.local", AccountType.PHARMACY)
        assert services.price_for(product, 1, user=pharmacy).unit_price == Decimal("50.00")

    def test_guest_gets_the_default_list(self, product, retail, student_list):
        PriceRule.objects.create(price_list=retail, product=product, unit_price=Decimal("100.00"))
        PriceRule.objects.create(
            price_list=student_list, product=product, unit_price=Decimal("75.00")
        )

        assert services.price_for(product, 1, user=None).unit_price == Decimal("100.00")


# ═══════════════════════════════════════════════════════════
#  أسعار الكميات
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestQuantityBreaks:
    @pytest.fixture(autouse=True)
    def _breaks(self, product, retail):
        for min_qty, price in ((1, "100.00"), (10, "90.00"), (50, "80.00")):
            PriceRule.objects.create(
                price_list=retail,
                product=product,
                min_quantity=min_qty,
                unit_price=Decimal(price),
            )

    @pytest.mark.parametrize(
        ("quantity", "expected"),
        [(1, "100.00"), (9, "100.00"), (10, "90.00"), (49, "90.00"), (50, "80.00"), (100, "80.00")],
    )
    def test_highest_matching_break_applies(self, product, quantity, expected):
        line = services.price_for(product, quantity)
        assert line.unit_price == Decimal(expected)


# ═══════════════════════════════════════════════════════════
#  الخصومات الترويجية
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestOverrides:
    def test_percentage_discount(self, product, retail):
        PriceOverride.objects.create(
            product=product,
            discount_kind=DiscountKind.PERCENTAGE,
            discount_value=Decimal("20.00"),
        )
        line = services.price_for(product, 2)

        assert line.discount_amount == Decimal("40.00")  # ٢٠٪ × ٢
        assert line.net == Decimal("160.00")
        assert line.tax_amount == Decimal("22.40")  # الضريبة على الصافي

    def test_fixed_discount(self, product, retail):
        PriceOverride.objects.create(
            product=product,
            discount_kind=DiscountKind.FIXED,
            discount_value=Decimal("15.00"),
        )
        assert services.price_for(product, 3).discount_amount == Decimal("45.00")

    def test_expired_override_is_ignored(self, product, retail):
        from datetime import timedelta

        PriceOverride.objects.create(
            product=product,
            discount_kind=DiscountKind.PERCENTAGE,
            discount_value=Decimal("50.00"),
            starts_at=timezone.now() - timedelta(days=10),
            ends_at=timezone.now() - timedelta(days=1),
        )
        assert services.price_for(product, 1).discount_amount == Decimal("0.00")

    def test_future_override_is_ignored(self, product, retail):
        from datetime import timedelta

        PriceOverride.objects.create(
            product=product,
            discount_kind=DiscountKind.PERCENTAGE,
            discount_value=Decimal("50.00"),
            starts_at=timezone.now() + timedelta(days=1),
        )
        assert services.price_for(product, 1).discount_amount == Decimal("0.00")

    def test_fixed_discount_never_exceeds_price(self, product, retail):
        """خصم أكبر من السعر يعني سطرًا سالبًا."""
        PriceOverride.objects.create(
            product=product,
            discount_kind=DiscountKind.FIXED,
            discount_value=Decimal("500.00"),
        )
        line = services.price_for(product, 1)

        assert line.net == Decimal("0.00")
        assert line.net >= 0


# ═══════════════════════════════════════════════════════════
#  الضريبة —  ADR-30
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestTax:
    def test_tax_is_computed_on_net_after_discount(self, product, retail):
        """
        ⚠️  الضريبة على الصافي لا على الإجمالي.

        حسابها قبل الخصم يضخّم الفاتورة ويخالف القاعدة الضريبية.
        """
        PriceOverride.objects.create(
            product=product,
            discount_kind=DiscountKind.PERCENTAGE,
            discount_value=Decimal("50.00"),
        )
        line = services.price_for(product, 1)

        assert line.net == Decimal("50.00")
        assert line.tax_amount == Decimal("7.00")  # ١٤٪ من ٥٠ لا من ١٠٠

    def test_rate_is_captured_as_snapshot(self, product, retail, tax_class):
        line = services.price_for(product, 1)
        assert line.tax_rate == Decimal("14.00")
        assert line.tax_class_code == "standard"

    def test_product_without_tax_class_uses_default(self, db, retail, tax_class):
        category = Category.objects.create(name_ar="فئة٢", name_en="Cat2")
        product = Product.objects.create(
            sku="P-002",
            name_ar="بلا فئة",
            name_en="No class",
            category=category,
            base_price=Decimal("100.00"),
        )
        assert services.price_for(product, 1).tax_rate == Decimal("14.00")

    def test_disabled_tax_yields_zero(self, product, retail, settings):
        from core.models.settings import SettingValueType, SystemSetting

        SystemSetting.set(
            "tax.enabled",
            False,
            value_type=SettingValueType.BOOL,
            group="tax",
            label_ar="الضريبة مفعّلة",
            label_en="Tax enabled",
        )
        line = services.price_for(product, 1)

        assert line.tax_rate == Decimal("0.00")
        assert line.tax_amount == Decimal("0.00")


# ═══════════════════════════════════════════════════════════
#  السلة
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCartPricing:
    def test_cart_totals_add_up(self, db, retail, tax_class):
        category = Category.objects.create(name_ar="فئة", name_en="Category")
        first = Product.objects.create(
            sku="A",
            name_ar="أ",
            name_en="A",
            category=category,
            base_price=Decimal("100.00"),
            tax_class=tax_class,
        )
        second = Product.objects.create(
            sku="B",
            name_ar="ب",
            name_en="B",
            category=category,
            base_price=Decimal("50.00"),
            tax_class=tax_class,
        )

        cart = services.price_cart(
            [(first, 2, None), (second, 1, None)],
            shipping_amount=Decimal("30.00"),
        )

        assert cart.subtotal == Decimal("250.00")
        assert cart.tax_total == Decimal("35.00")  # ١٤٪ من ٢٥٠
        assert cart.total == Decimal("315.00")  # + ٣٠ شحن
        assert cart.item_count == 3

    def test_coupon_discount_reduces_the_total(self, product, retail):
        cart = services.price_cart([(product, 2, None)], coupon_discount=Decimal("50.00"))

        assert cart.discount_total == Decimal("50.00")
        assert cart.net_sales == Decimal("150.00")


# ═══════════════════════════════════════════════════════════
#  الدقة العشرية
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestDecimalPrecision:
    def test_no_float_drift(self, db, retail, tax_class):
        """
        ⚠️  النموذج القديم استخدم `FloatField` في تسعة مواضع.

        مع ضريبة وخصومات ومرتجعات، فروق الفاصلة العائمة تتراكم
        حتى تكسر أي مطابقة محاسبية.
        """
        category = Category.objects.create(name_ar="فئة", name_en="Category")
        product = Product.objects.create(
            sku="ODD",
            name_ar="سعر كسري",
            name_en="Odd price",
            category=category,
            base_price=Decimal("33.33"),
            tax_class=tax_class,
        )

        line = services.price_for(product, 3)

        assert line.subtotal == Decimal("99.99")
        assert isinstance(line.total, Decimal)
        assert line.total == Decimal("113.99")  # ٩٩٫٩٩ + ١٤٪ = ١١٣٫٩٨٨٦ ⟵ ١١٣٫٩٩
