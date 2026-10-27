"""
An order line and its variant — the baseline pinned before product colours arrived.
"""

from decimal import Decimal

import pytest
from django.apps import apps

from accounts.models import AccountType, User
from cart import services as cart_services
from catalog.models import Category, Product, ProductVariant
from core.models.settings import SystemSetting
from customers.models import CustomerProfile
from inventory import services as inventory_services
from orders import services as order_services

PASSWORD = "Str0ng-Test-Pass!23"

ADDRESS = {
    "recipient_name": "أحمد محمود",
    "phone": "+201001234567",
    "governorate": "القاهرة",
    "city": "مدينة نصر",
    "street": "شارع ١",
}


@pytest.fixture(autouse=True)
def tax_off(db):
    SystemSetting.set("tax.enabled", False, value_type="BOOL", label_ar="ض", label_en="t")


@pytest.fixture
def location(db):
    return apps.get_model("inventory", "StockLocation").objects.create(
        code="main", name_ar="الرئيسي", name_en="Main", is_default=True
    )


@pytest.fixture
def user(db):
    user = User.objects.create_user(
        email="buyer@test.local", password=PASSWORD, account_type=AccountType.STUDENT
    )
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def customer(user):
    return CustomerProfile.objects.create(user=user)


@pytest.fixture
def product(db, location):
    from django.core.management import call_command

    from access.models import AccessPolicy

    call_command("seed_access_policies", verbosity=0)
    category = Category.objects.create(name_ar="فئة", name_en="Category")
    return Product.objects.create(
        sku="OV-001",
        name_ar="سكراب",
        name_en="Scrub",
        category=category,
        base_price=Decimal("100.00"),
        access_policy=AccessPolicy.objects.get(code="public"),
    )


@pytest.fixture
def variant(product, location):
    variant = ProductVariant.objects.create(
        product=product,
        sku="OV-001-M",
        name_ar="وسط",
        name_en="Medium",
        price_adjustment=Decimal("15.00"),
    )
    inventory_services.receive(product, 10, Decimal("60.00"), location=location, variant=variant)
    return variant


@pytest.mark.django_db
class TestVariantOrderLine:
    def test_the_line_keeps_the_variant_and_its_adjusted_price(
        self, user, customer, product, variant
    ):
        cart = cart_services.get_active_cart(user=user)
        cart_services.add_line(cart, product, 2, variant=variant, user=user)

        order = order_services.create_from_cart(cart, customer=customer, address=ADDRESS)
        line = order.lines.get()

        assert line.variant_id == variant.pk
        assert line.unit_price == Decimal("115.00")
        assert line.product_sku == "OV-001"

    def test_the_reservation_is_taken_on_the_variants_stock(
        self, user, customer, product, variant, location
    ):
        cart = cart_services.get_active_cart(user=user)
        cart_services.add_line(cart, product, 3, variant=variant, user=user)

        order_services.create_from_cart(cart, customer=customer, address=ADDRESS)

        assert inventory_services.available_quantity(product, variant=variant) == 7
