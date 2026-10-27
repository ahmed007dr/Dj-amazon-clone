"""
A counter sale of a variant — the baseline pinned before product colours arrived.

⚠️  The backend has accepted `variant` on `/pos/quote/` and `/pos/checkout/`
    since the beginning; the cashier UI never sent one. These pin that the
    server half already works.
"""

from decimal import Decimal

import pytest

from accounts.models import AccountType, User
from catalog.models import Category, Product, ProductVariant
from core.models.settings import SystemSetting
from core.models.tax import TaxClass
from inventory import services as inventory_services
from inventory.models import LocationKind, StockLocation
from orders.models import Order
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
def pos_payment_providers(db):
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
def location(db):
    return StockLocation.objects.create(
        code="branch-1",
        name_ar="فرع",
        name_en="Branch",
        kind=LocationKind.BRANCH,
        is_default=True,
        is_sellable=True,
    )


@pytest.fixture
def session(location):
    cashier = User.objects.create_user(
        email="cashier@test.local", password=PASSWORD, account_type=AccountType.EMPLOYEE
    )
    cashier.is_active = True
    cashier.save()
    register = Register.objects.create(
        code="reg-1", name_ar="كاونتر", name_en="Counter", location=location
    )
    return services.open_session(register, cashier, opening_float=Decimal("0.00"))


@pytest.fixture
def product(db):
    category = Category.objects.create(slug="c", name_ar="فئة", name_en="Cat")
    return Product.objects.create(
        sku="PV-1",
        name_ar="سكراب",
        name_en="Scrub",
        category=category,
        base_price=Decimal("50.00"),
    )


@pytest.fixture
def variant(product, location):
    variant = ProductVariant.objects.create(
        product=product,
        sku="PV-1-L",
        name_ar="كبير",
        name_en="Large",
        price_adjustment=Decimal("10.00"),
    )
    inventory_services.receive(product, 10, Decimal("30.00"), location=location, variant=variant)
    return variant


def cash(amount: str):
    return services.SplitPayment(method="CASH", amount=Decimal(amount))


@pytest.mark.django_db
class TestVariantSale:
    def test_quote_prices_the_variant(self, session, product, variant):
        result = services.quote(session, [services.SaleLine(product, 2, variant)])

        assert result.total == Decimal("120.00")

    def test_checkout_sells_from_the_variants_stock_and_keeps_it_on_the_line(
        self, session, product, variant, location
    ):
        result = services.checkout(
            session, [services.SaleLine(product, 2, variant)], [cash("120.00")]
        )

        line = Order.objects.get(pk=result.order.pk).lines.get()
        assert line.variant_id == variant.pk
        assert line.unit_price == Decimal("60.00")
        assert inventory_services.available_quantity(product, location=location, variant=variant) == 8

    def test_a_variant_with_no_stock_cannot_be_sold(self, session, product, variant):
        from core.errors import BusinessError

        with pytest.raises(BusinessError):
            services.checkout(session, [services.SaleLine(product, 11, variant)], [cash("660.00")])

    def test_refund_returns_stock_to_the_variant(self, session, product, variant, location):
        result = services.checkout(
            session, [services.SaleLine(product, 2, variant)], [cash("120.00")]
        )

        services.refund_sale(session, result.order, reason="مرتجع")

        assert inventory_services.available_quantity(product, location=location, variant=variant) == 10
