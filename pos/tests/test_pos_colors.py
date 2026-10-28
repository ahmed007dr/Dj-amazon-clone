"""
The counter and colours — the cashier picks a colour, the server holds the line to it.

⚠️  The backend has always accepted `variant`; what changes is that the search now
    *offers* the variants (with this register's stock), a scanned colour label finds its
    product and says which colour it was, and a sale can no longer name a variant that
    isn't the product's or leave the colour out when the product has them.
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from catalog import colors as color_services
from catalog.models import Category, Product, ProductVariant
from core.models.settings import SystemSetting
from core.models.tax import TaxClass
from inventory import services as inventory_services
from inventory.models import LocationKind, StockLocation
from pos import services
from pos.models import Register

PASSWORD = "Str0ng-Test-Pass!23"


@pytest.fixture(autouse=True)
def tax_off(db):
    SystemSetting.set("tax.enabled", False, value_type="BOOL", label_ar="ض", label_en="t")
    TaxClass.objects.create(
        code="zero", name_ar="صفري", name_en="Zero", rate=Decimal("0"), is_default=True
    )


@pytest.fixture(autouse=True)
def cash_provider(db):
    from payments.models import PaymentMethodKind, PaymentProvider

    PaymentProvider.objects.create(
        code="pos-cash",
        adapter_key="cash",
        name_ar="نقدي",
        name_en="Cash",
        supported_methods=[PaymentMethodKind.CASH],
        supported_channels=["POS"],
        priority=100,
        is_active=True,
        is_sandbox=False,
    )


@pytest.fixture
def branch(db):
    return StockLocation.objects.create(
        code="branch-1", name_ar="فرع", name_en="Branch", kind=LocationKind.BRANCH, is_default=True
    )


@pytest.fixture
def warehouse(db):
    return StockLocation.objects.create(code="wh", name_ar="مخزن", name_en="Warehouse")


@pytest.fixture
def cashier(db):
    user = User.objects.create_user(
        email="cashier@test.local", password=PASSWORD, account_type=AccountType.EMPLOYEE
    )
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def session(branch, cashier):
    register = Register.objects.create(
        code="reg-1", name_ar="كاونتر", name_en="Counter", location=branch
    )
    return services.open_session(register, cashier, opening_float=Decimal("0.00"))


@pytest.fixture
def client(cashier):
    client = APIClient()
    client.force_authenticate(user=cashier)
    return client


@pytest.fixture
def product(db):
    return Product.objects.create(
        sku="PC-1",
        name_ar="قميص",
        name_en="Top",
        category=Category.objects.create(slug="c", name_ar="فئة", name_en="Cat"),
        base_price=Decimal("50.00"),
        is_featured=True,
    )


@pytest.fixture
def blue(product, branch):
    color = color_services.create_color(
        product, name_ar="أزرق", name_en="Blue", hex="#1E40AF", price_override=Decimal("70.00")
    )
    variant = color.variants.get()
    variant.barcode = "6221234567890"
    variant.save()
    inventory_services.receive(product, 6, Decimal("20.00"), location=branch, variant=variant)
    return color


@pytest.fixture
def red(product, branch, warehouse):
    color = color_services.create_color(product, name_ar="أحمر", name_en="Red", hex="#B91C1C")
    # Red is in the warehouse only — nothing on this counter's shelf
    inventory_services.receive(
        product, 9, Decimal("20.00"), location=warehouse, variant=color.variants.get()
    )
    return color


def cash(amount: str):
    return services.SplitPayment(method="CASH", amount=Decimal(amount))


@pytest.mark.django_db
class TestSearch:
    def test_results_offer_the_variants_with_this_registers_stock(
        self, client, session, product, blue, red
    ):
        response = client.get(reverse("v1:pos:products"), {"search": "قميص"})

        assert response.status_code == 200
        [item] = response.data
        by_name = {v["name_en"]: v for v in item["variants"]}
        assert by_name["Blue"]["available"] == 6
        assert by_name["Blue"]["color"]["hex"] == "#1E40AF"
        assert by_name["Blue"]["color"]["price_override"] == "70.00"
        # Red has stock only in another location: it is listed, with zero HERE
        assert by_name["Red"]["available"] == 0

    def test_scanning_a_colours_barcode_finds_the_product_and_names_the_colour(
        self, client, session, product, blue
    ):
        response = client.get(reverse("v1:pos:products"), {"search": "6221234567890"})

        [item] = response.data
        assert item["sku"] == "PC-1"
        assert item["matched_variant"] == str(blue.variants.get().pk)

    def test_scanning_a_variant_sku_works_the_same(self, client, session, product, blue):
        response = client.get(reverse("v1:pos:products"), {"search": "PC-1-BLUE"})

        assert response.data[0]["matched_variant"] == str(blue.variants.get().pk)

    def test_a_plain_name_search_matches_no_variant(self, client, session, product, blue):
        response = client.get(reverse("v1:pos:products"), {"search": "قميص"})

        assert response.data[0]["matched_variant"] is None

    def test_a_product_without_variants_has_an_empty_list(self, client, session, branch):
        plain = Product.objects.create(
            sku="PLAIN",
            name_ar="عادي",
            name_en="Plain",
            category=Category.objects.create(slug="p", name_ar="ف", name_en="C"),
            base_price=Decimal("5.00"),
        )
        inventory_services.receive(plain, 3, Decimal("1.00"), location=branch)

        response = client.get(reverse("v1:pos:products"), {"search": "PLAIN"})

        assert response.data[0]["variants"] == []

    def test_a_deactivated_colour_is_not_offered(self, client, session, product, blue, red):
        color_services.update_color(red, is_active=False)

        [item] = client.get(reverse("v1:pos:products"), {"search": "قميص"}).data

        assert [v["name_en"] for v in item["variants"]] == ["Blue"]


@pytest.mark.django_db
class TestSale:
    def lines(self, product, variant=None, quantity=2):
        entry = {"product": str(product.pk), "quantity": quantity}
        if variant is not None:
            entry["variant"] = str(variant.pk)
        return [entry]

    def test_quote_prices_the_colour_and_echoes_it(self, client, session, product, blue):
        response = client.post(
            reverse("v1:pos:quote"),
            {"lines": self.lines(product, blue.variants.get())},
            format="json",
        )

        assert response.status_code == 200, response.data
        assert response.data["total"] == "140.00", "سعر اللون ٧٠ × ٢"
        assert response.data["lines"][0]["variant"] == str(blue.variants.get().pk)

    def test_checkout_sells_the_colour_and_snapshots_it(
        self, client, session, product, blue, branch
    ):
        response = client.post(
            reverse("v1:pos:checkout"),
            {
                "lines": self.lines(product, blue.variants.get()),
                "payments": [{"method": "CASH", "amount": "140.00"}],
            },
            format="json",
        )

        assert response.status_code == 201, response.data
        line = response.data["order"]["lines"][0]
        assert line["variant_sku"] == "PC-1-BLUE"
        assert (line["color_name_en"], line["color_hex"]) == ("Blue", "#1E40AF")
        assert (
            inventory_services.available_quantity(
                product, location=branch, variant=blue.variants.get()
            )
            == 4
        )

    def test_a_product_with_colours_cannot_be_sold_without_one(
        self, client, session, product, blue
    ):
        response = client.post(
            reverse("v1:pos:quote"), {"lines": self.lines(product)}, format="json"
        )

        assert response.status_code == 400

    def test_a_variant_of_another_product_is_refused(self, client, session, product, blue):
        other = Product.objects.create(
            sku="PC-2",
            name_ar="س",
            name_en="S",
            category=product.category,
            base_price=Decimal("1.00"),
        )
        foreign = ProductVariant.objects.create(
            product=other, sku="PC-2-X", name_ar="س", name_en="X"
        )

        response = client.post(
            reverse("v1:pos:quote"), {"lines": self.lines(product, foreign)}, format="json"
        )

        assert response.status_code == 400

    def test_an_unknown_variant_is_a_404(self, client, session, product, blue):
        import uuid

        response = client.post(
            reverse("v1:pos:quote"),
            {"lines": [{"product": str(product.pk), "variant": str(uuid.uuid4()), "quantity": 1}]},
            format="json",
        )

        assert response.status_code == 404

    def test_a_colour_out_of_stock_here_cannot_be_sold(self, client, session, product, blue, red):
        response = client.post(
            reverse("v1:pos:checkout"),
            {
                "lines": self.lines(product, red.variants.get(), 1),
                "payments": [{"method": "CASH", "amount": "50.00"}],
            },
            format="json",
        )

        assert response.status_code >= 400
