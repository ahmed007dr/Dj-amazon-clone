"""
"Price before discount" on a cart line.

⚠️  A line shows the old price only while it is above the line's `unit_price` — the same
    figure the product page showed this customer — and the server sends the verdict
    (`compare_at_price` / `discount_percent`), never the browser's arithmetic.
"""

from decimal import Decimal

import pytest
from django.apps import apps
from django.urls import reverse
from rest_framework.test import APIClient

from access.models import AccessPolicy
from accounts.models import AccountType, User
from cart import services
from catalog import colors as color_services
from catalog.models import Category, Product, ProductVariant
from core.models.settings import SystemSetting
from inventory import services as inventory_services

PASSWORD = "Str0ng-Test-Pass!23"


def price_list_model(name):
    """
    Through `apps.get_model`: `cart` may not import `pricing.models` (and its tests obey the
    same contract the code does).
    """
    return apps.get_model("pricing", name)


pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def tax_off(db):
    SystemSetting.set("tax.enabled", False, value_type="BOOL", label_ar="ض", label_en="t")


@pytest.fixture
def location(db):
    return apps.get_model("inventory", "StockLocation").objects.create(
        code="main", name_ar="الرئيسي", name_en="Main", is_default=True
    )


def make_user(email, account_type):
    user = User.objects.create_user(email=email, password=PASSWORD, account_type=account_type)
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def doctor(db):
    return make_user("cmp-doctor@test.local", AccountType.DOCTOR)


@pytest.fixture
def student(db):
    return make_user("cmp-student@test.local", AccountType.STUDENT)


@pytest.fixture
def product(db, location):
    from django.core.management import call_command

    call_command("seed_access_policies", verbosity=0)
    item = Product.objects.create(
        sku="CC-1",
        name_ar="قميص",
        name_en="Top",
        category=Category.objects.create(name_ar="ملابس", name_en="Apparel"),
        base_price=Decimal("80.00"),
        compare_at_price=Decimal("100.00"),
        access_policy=AccessPolicy.objects.get(code="public"),
    )
    inventory_services.receive(item, 20, Decimal("40.00"), location=location)
    return item


def snapshot_lines(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client.get(reverse("v1:cart:detail")).data["lines"]


def add(user, product, quantity=1, variant=None):
    cart = services.get_active_cart(user=user)
    services.add_line(cart, product, quantity, variant=variant, user=user)


class TestCartLine:
    def test_a_line_carries_the_old_price_and_the_percentage(self, doctor, product):
        add(doctor, product, 2)

        line = snapshot_lines(doctor)[0]

        assert line["pricing"]["unit_price"] == "80.00"
        assert line["compare_at_price"] == "100.00"
        assert line["discount_percent"] == 20

    def test_no_compare_at_means_null_fields(self, doctor, product):
        Product.objects.filter(pk=product.pk).update(compare_at_price=None)
        add(doctor, product)

        line = snapshot_lines(doctor)[0]

        assert line["compare_at_price"] is None
        assert line["discount_percent"] is None

    def test_a_student_price_changes_the_verdict(self, student, product):
        students = price_list_model("PriceList").objects.create(
            code="students",
            name_ar="طلاب",
            name_en="Students",
            account_types=[AccountType.STUDENT],
            priority=10,
        )
        price_list_model("PriceRule").objects.create(
            price_list=students, product=product, unit_price=Decimal("50.00")
        )
        add(student, product)

        line = snapshot_lines(student)[0]

        assert line["pricing"]["unit_price"] == "50.00"
        assert line["compare_at_price"] == "100.00"
        assert line["discount_percent"] == 50

    def test_a_price_above_the_old_price_hides_it(self, student, product):
        students = price_list_model("PriceList").objects.create(
            code="students",
            name_ar="طلاب",
            name_en="Students",
            account_types=[AccountType.STUDENT],
            priority=10,
        )
        price_list_model("PriceRule").objects.create(
            price_list=students, product=product, unit_price=Decimal("120.00")
        )
        add(student, product)

        line = snapshot_lines(student)[0]

        assert line["compare_at_price"] is None
        assert line["discount_percent"] is None

    def test_a_colour_line_uses_the_colours_own_old_price(self, doctor, product, location):
        green = color_services.create_color(
            product,
            name_ar="أخضر",
            name_en="Green",
            hex="#15803D",
            price_override=Decimal("60.00"),
            compare_at_price=Decimal("90.00"),
        )
        variant = green.variants.get()
        inventory_services.receive(product, 5, Decimal("30.00"), location=location, variant=variant)
        add(doctor, product, variant=variant)

        line = snapshot_lines(doctor)[0]

        assert line["pricing"]["unit_price"] == "60.00"
        assert line["compare_at_price"] == "90.00"
        assert line["discount_percent"] == 33

    def test_a_size_variant_carries_its_difference_on_the_old_price(
        self, doctor, product, location
    ):
        xl = ProductVariant.objects.create(
            product=product,
            sku="CC-1-XL",
            name_ar="كبير",
            name_en="XL",
            price_adjustment=Decimal("20.00"),
        )
        inventory_services.receive(product, 5, Decimal("30.00"), location=location, variant=xl)
        add(doctor, product, variant=xl)

        line = snapshot_lines(doctor)[0]

        assert line["pricing"]["unit_price"] == "100.00"
        assert line["compare_at_price"] == "120.00"
        assert line["discount_percent"] == 16
