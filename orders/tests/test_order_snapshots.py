"""
What an order line remembers about the colour it sold.

⚠️  An invoice must keep saying "Blue, size M" after the shop renames the colour,
    reprices it, or deletes it — so the line copies the names and the hex at the time
    of sale. Lines written before colours existed have no copy; the serializer shows
    them the live variant instead of pretending nothing was chosen.
"""

from decimal import Decimal

import pytest
from django.apps import apps

from accounts.models import AccountType, User
from cart import services as cart_services
from catalog import colors as color_services
from catalog.models import Category, Product, ProductVariant
from core.models.settings import SystemSetting
from customers.models import CustomerProfile
from inventory import services as inventory_services
from orders import services as order_services
from orders.serializers import OrderDetailSerializer, OrderLineSerializer

PASSWORD = "Str0ng-Test-Pass!23"
ADDRESS = {
    "recipient_name": "أحمد",
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
        email="buyer@test.local", password=PASSWORD, account_type=AccountType.DOCTOR
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
    return Product.objects.create(
        sku="OS-001",
        name_ar="قميص",
        name_en="Top",
        category=Category.objects.create(name_ar="ملابس", name_en="Apparel"),
        base_price=Decimal("100.00"),
        access_policy=AccessPolicy.objects.get(code="public"),
    )


@pytest.fixture
def blue(product, location):
    color = color_services.create_color(
        product, name_ar="أزرق", name_en="Blue", hex="#1E40AF", price_override=Decimal("120.00")
    )
    inventory_services.receive(
        product, 10, Decimal("50.00"), location=location, variant=color.variants.get()
    )
    return color


def place(user, customer, product, variant, quantity=2):
    cart = cart_services.get_active_cart(user=user)
    cart_services.add_line(cart, product, quantity, variant=variant, user=user)
    return order_services.create_from_cart(cart, customer=customer, address=ADDRESS)


@pytest.mark.django_db
class TestSnapshot:
    def test_the_line_records_variant_and_colour(self, user, customer, product, blue):
        order = place(user, customer, product, blue.variants.get())

        line = order.lines.get()
        assert line.variant_sku == "OS-001-BLUE"
        assert (line.variant_name_ar, line.variant_name_en) == ("أزرق", "Blue")
        assert (line.color_name_ar, line.color_name_en, line.color_hex) == (
            "أزرق",
            "Blue",
            "#1E40AF",
        )
        assert line.unit_price == Decimal("120.00"), "سعر اللون"

    def test_a_plain_line_records_nothing_extra(self, user, customer, product, location):
        plain = Product.objects.create(
            sku="OS-PLAIN",
            name_ar="س",
            name_en="S",
            category=product.category,
            base_price=Decimal("5.00"),
            access_policy=product.access_policy,
        )
        inventory_services.receive(plain, 5, Decimal("1.00"), location=location)

        line = place(user, customer, plain, None).lines.get()

        assert (line.variant_sku, line.color_name_en, line.color_hex) == ("", "", "")

    def test_a_size_variant_without_a_colour_records_the_variant_only(
        self, user, customer, product, location
    ):
        plain = Product.objects.create(
            sku="OS-SIZE",
            name_ar="س",
            name_en="S",
            category=product.category,
            base_price=Decimal("5.00"),
            access_policy=product.access_policy,
        )
        size = ProductVariant.objects.create(
            product=plain, sku="OS-SIZE-M", name_ar="وسط", name_en="Medium"
        )
        inventory_services.receive(plain, 5, Decimal("1.00"), location=location, variant=size)

        line = place(user, customer, plain, size).lines.get()

        assert line.variant_sku == "OS-SIZE-M" and line.color_name_en == ""

    def test_renaming_or_deleting_the_colour_later_changes_nothing(
        self, user, customer, product, blue
    ):
        order = place(user, customer, product, blue.variants.get())

        color_services.update_color(blue, name_en="Royal blue", name_ar="ملكي", hex="#000080")
        color_services.delete_color(blue)

        data = OrderLineSerializer(order.lines.get()).data
        assert (data["color_name_en"], data["color_name_ar"], data["color_hex"]) == (
            "Blue",
            "أزرق",
            "#1E40AF",
        )
        assert data["variant_name_en"] == "Blue"

    def test_the_detail_payload_carries_it(self, user, customer, product, blue):
        order = place(user, customer, product, blue.variants.get())

        line = OrderDetailSerializer(order).data["lines"][0]

        assert line["variant_sku"] == "OS-001-BLUE" and line["color_hex"] == "#1E40AF"


@pytest.mark.django_db
class TestOldLines:
    def test_a_line_without_a_snapshot_falls_back_to_the_live_variant(
        self, user, customer, product, blue
    ):
        order = place(user, customer, product, blue.variants.get())
        line = order.lines.get()
        # Simulate a line written before colours existed: variant set, snapshot blank
        type(line).objects.filter(pk=line.pk).update(
            variant_sku="",
            variant_name_ar="",
            variant_name_en="",
            color_name_ar="",
            color_name_en="",
            color_hex="",
        )
        line.refresh_from_db()

        data = OrderLineSerializer(line).data

        assert data["variant_sku"] == "OS-001-BLUE"
        assert data["color_name_en"] == "Blue" and data["color_hex"] == "#1E40AF"

    def test_an_old_plain_line_stays_blank(self, user, customer, product, location):
        plain = Product.objects.create(
            sku="OS-OLD",
            name_ar="س",
            name_en="S",
            category=product.category,
            base_price=Decimal("5.00"),
            access_policy=product.access_policy,
        )
        inventory_services.receive(plain, 5, Decimal("1.00"), location=location)
        line = place(user, customer, plain, None).lines.get()

        data = OrderLineSerializer(line).data

        assert data["variant_sku"] == "" and data["color_hex"] == ""
