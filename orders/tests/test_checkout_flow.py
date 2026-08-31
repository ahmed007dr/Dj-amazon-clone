"""
An integration test: the complete purchase cycle over HTTP.

⚠️  The other tests exercise the services directly. This one exercises **what
    the frontend actually sees**: the headers, the status codes and the response shapes.

    A correct service behind a broken interface helps nobody.
"""

from decimal import Decimal

import pytest
from django.apps import apps
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from catalog.models import Category, Product
from core.models.tax import TaxClass
from customers.models import CustomerProfile
from inventory import services as inventory_services
from promotions.models import Coupon, CouponKind

PASSWORD = "Str0ng-Test-Pass!23"

ADDRESS = {
    "recipient_name": "أحمد محمود",
    "phone": "+201001234567",
    "governorate": "القاهرة",
    "city": "مدينة نصر",
    "street": "شارع ١",
}


def location_model():
    return apps.get_model("inventory", "StockLocation")


@pytest.fixture
def location(db):
    return location_model().objects.create(
        code="main", name_ar="الرئيسي", name_en="Main", is_default=True
    )


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
def policies(db):
    from django.core.management import call_command

    call_command("seed_access_policies", verbosity=0)


@pytest.fixture
def product(db, location, tax_class, policies):
    category = Category.objects.create(name_ar="فئة", name_en="Category")
    product = Product.objects.create(
        sku="P-001",
        name_ar="منتج",
        name_en="Product",
        category=category,
        base_price=Decimal("100.00"),
        tax_class=tax_class,
    )
    inventory_services.receive(product, 50, Decimal("60.00"), location=location)
    return product


@pytest.fixture
def payment_provider(db):
    from payments.models import PaymentMethodKind, PaymentProvider

    return PaymentProvider.objects.create(
        code="cod",
        adapter_key="cash_on_delivery",
        name_ar="دفع عند الاستلام",
        name_en="Cash on delivery",
        supported_methods=[PaymentMethodKind.CASH_ON_DELIVERY],
        is_active=True,
    )


@pytest.fixture
def buyer(db):
    user = User.objects.create_user(
        email="buyer@test.local", password=PASSWORD, account_type=AccountType.STUDENT
    )
    user.is_active = True
    user.save()
    CustomerProfile.objects.create(user=user)
    return user


@pytest.fixture
def client(buyer):
    api = APIClient()
    api.force_authenticate(user=buyer)
    return api


# ═══════════════════════════════════════════════════════════
#  The complete cycle
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestFullPurchaseFlow:
    def test_browse_add_checkout_and_view(self, client, product, payment_provider, location):
        """
        ⚠️  The whole journey: browse ← cart ← checkout ← view the order.

        Every step depends on the one before it — a break in any link shows up
        here rather than in production.
        """
        # 1 — browse
        listing = client.get(reverse("v1:catalog:products"))
        assert listing.status_code == 200
        assert listing.data["results"][0]["sku"] == "P-001"

        # 2 — add to the cart
        added = client.post(
            reverse("v1:cart:lines"),
            {"product": str(product.pk), "quantity": 2},
            format="json",
        )
        assert added.status_code == 201
        assert added.data["totals"]["subtotal"] == "200.00"
        assert added.data["totals"]["tax_total"] == "28.00"
        assert added.data["is_checkoutable"]

        # 3 — checkout
        checkout = client.post(
            reverse("v1:orders:checkout"),
            {"address": ADDRESS, "payment_method": "COD"},
            format="json",
        )
        assert checkout.status_code == 201

        order = checkout.data["order"]
        assert order["grand_total"] == "228.00"
        assert order["status"] == "PENDING"
        assert order["number"].startswith("ORD-")

        # 4 — view the order
        detail = client.get(reverse("v1:orders:detail", args=[order["id"]]))
        assert detail.status_code == 200
        assert detail.data["lines"][0]["product_sku"] == "P-001"
        assert detail.data["lines"][0]["tax_rate"] == "14.00"

        # 5 — the cart has converted
        assert client.get(reverse("v1:cart:detail")).data["totals"]["item_count"] == 0

    def test_money_is_serialised_as_string(self, client, product):
        """
        ⚠️  ADR-31 — `JSON.parse` converts numbers to `double`.

            `450.00` becomes `450`, and `0.1+0.2` becomes `0.30000000000000004`.
        """
        client.post(
            reverse("v1:cart:lines"),
            {"product": str(product.pk), "quantity": 1},
            format="json",
        )
        totals = client.get(reverse("v1:cart:detail")).data["totals"]

        for key in ("subtotal", "tax_total", "total"):
            assert isinstance(totals[key], str), key


# ═══════════════════════════════════════════════════════════
#  The guest cart
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestGuestCart:
    def test_guest_shops_before_signing_up(self, product):
        """
        ⚠️  Forcing a visitor to register before adding loses the sale.
        """
        guest = APIClient()
        response = guest.post(
            reverse("v1:cart:lines"),
            {"product": str(product.pk), "quantity": 1},
            format="json",
            HTTP_X_CART_SESSION="guest-abc-123",
        )

        assert response.status_code == 201
        assert response.data["totals"]["item_count"] == 1

    def test_guest_without_session_header_is_rejected(self, product):
        guest = APIClient()
        response = guest.post(
            reverse("v1:cart:lines"),
            {"product": str(product.pk), "quantity": 1},
            format="json",
        )
        assert response.status_code == 400

    def test_merge_after_login_sums_quantities(self, client, buyer, product):
        guest = APIClient()
        guest.post(
            reverse("v1:cart:lines"),
            {"product": str(product.pk), "quantity": 2},
            format="json",
            HTTP_X_CART_SESSION="guest-merge",
        )

        client.post(
            reverse("v1:cart:lines"),
            {"product": str(product.pk), "quantity": 1},
            format="json",
        )

        merged = client.post(
            reverse("v1:cart:merge"), {"session_key": "guest-merge"}, format="json"
        )
        assert merged.data["totals"]["item_count"] == 3


# ═══════════════════════════════════════════════════════════
#  Coupons
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCouponEndpoint:
    def test_invalid_coupon_returns_200_with_reason(self, client, product):
        """
        ⚠️  A rejected coupon is not an error — the customer is trying codes.

            Answering `400` makes the frontend show "an error occurred" instead
            of the reason.
        """
        client.post(
            reverse("v1:cart:lines"),
            {"product": str(product.pk), "quantity": 1},
            format="json",
        )

        response = client.post(reverse("v1:cart:coupon"), {"code": "NOPE"}, format="json")

        assert response.status_code == 200
        assert response.data["coupon"]["is_valid"] is False
        assert response.data["coupon"]["reason"] == "COUPON_NOT_FOUND"

    def test_valid_coupon_reduces_the_total(self, client, product, db):
        Coupon.objects.create(
            code="SAVE20",
            name_ar="خصم",
            name_en="Discount",
            kind=CouponKind.PERCENTAGE,
            value=Decimal("20.00"),
        )
        client.post(
            reverse("v1:cart:lines"),
            {"product": str(product.pk), "quantity": 1},
            format="json",
        )

        response = client.post(reverse("v1:cart:coupon"), {"code": "save20"}, format="json")

        assert response.data["coupon"]["is_valid"]
        assert response.data["totals"]["coupon_discount"] == "20.00"


# ═══════════════════════════════════════════════════════════
#  Ownership
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestOrderOwnership:
    def test_cannot_view_another_customers_order(self, client, buyer, product, payment_provider):
        """
        ⚠️  The best-known hole in the legacy code: the identity taken from the
            URL rather than from the token.
        """
        client.post(
            reverse("v1:cart:lines"),
            {"product": str(product.pk), "quantity": 1},
            format="json",
        )
        order_id = client.post(
            reverse("v1:orders:checkout"),
            {"address": ADDRESS, "payment_method": "COD"},
            format="json",
        ).data["order"]["id"]

        intruder = User.objects.create_user(email="intruder@test.local", password=PASSWORD)
        intruder.is_active = True
        intruder.save()
        CustomerProfile.objects.create(user=intruder)

        other = APIClient()
        other.force_authenticate(user=intruder)

        # ⚠️  404, not 403 — the difference between them is an enumeration tool
        assert other.get(reverse("v1:orders:detail", args=[order_id])).status_code == 404
        assert (
            other.post(
                reverse("v1:orders:cancel", args=[order_id]),
                {"reason": "محاولة"},
                format="json",
            ).status_code
            == 404
        )

    def test_customer_cannot_reach_admin_endpoints(self, client):
        assert client.get(reverse("v1:orders:admin-orders")).status_code == 403


# ═══════════════════════════════════════════════════════════
#  Re-validation at checkout
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCheckoutRevalidation:
    def test_stock_lost_between_add_and_checkout_blocks_it(
        self, client, product, location, payment_provider
    ):
        client.post(
            reverse("v1:cart:lines"),
            {"product": str(product.pk), "quantity": 10},
            format="json",
        )

        # Another buyer consumes the stock
        inventory_services.sell_immediately(product, 50, location=location)

        response = client.post(
            reverse("v1:orders:checkout"),
            {"address": ADDRESS, "payment_method": "COD"},
            format="json",
        )

        assert response.status_code == 409
        assert response.data["code"] == "INSUFFICIENT_STOCK"

    def test_checkout_requires_an_address(self, client, product, payment_provider):
        client.post(
            reverse("v1:cart:lines"),
            {"product": str(product.pk), "quantity": 1},
            format="json",
        )

        response = client.post(
            reverse("v1:orders:checkout"), {"payment_method": "COD"}, format="json"
        )
        assert response.status_code == 400

    def test_empty_cart_cannot_check_out(self, client, payment_provider):
        response = client.post(
            reverse("v1:orders:checkout"),
            {"address": ADDRESS, "payment_method": "COD"},
            format="json",
        )
        assert response.status_code == 400
        assert response.data["code"] == "CART_EMPTY"


# ═══════════════════════════════════════════════════════════
#  Cash on delivery — collection happens at the door
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCashOnDeliveryCollection:
    """
    ⚠️  Cash on delivery is the shop's default method and the one with no inbound
        event — nothing tells the system the money arrived except the delivery
        itself. These tests guard the two links that were missing between them.
    """

    def place_order(self, client, product):
        client.post(
            reverse("v1:cart:lines"),
            {"product": str(product.pk), "quantity": 1},
            format="json",
        )
        response = client.post(
            reverse("v1:orders:checkout"),
            {"address": ADDRESS, "payment_method": "COD"},
            format="json",
        )
        assert response.status_code == 201

        from orders.models import Order

        return Order.objects.get(pk=response.data["order"]["id"])

    def test_checkout_authorises_without_collecting(self, client, product, payment_provider):
        """
        ⚠️  `AUTHORIZED`, never `CAPTURED`.

            Nothing has been collected at checkout — the courier has not left yet.
            Capturing here puts revenue that may never arrive into every report.
        """
        from orders.models import PaymentStatus
        from payments.models import PaymentTransaction, TransactionStatus

        order = self.place_order(client, product)

        payment = PaymentTransaction.objects.get(reference_id=str(order.pk))
        assert payment.status == TransactionStatus.AUTHORIZED
        assert order.payment_status != PaymentStatus.PAID

    def test_delivery_captures_and_marks_the_order_paid(self, client, product, payment_provider):
        """
        ⚠️  **The gap this closes.**

            The courier collected the cash, the goods were handed over, and the
            order stayed "awaiting payment" until somebody remembered to open the
            payments screen and press capture. The revenue reports counted what
            was remembered rather than what was sold.
        """
        from orders import services as order_services
        from orders.models import OrderStatus, PaymentStatus
        from payments.models import PaymentTransaction, TransactionStatus

        order = self.place_order(client, product)

        for status in (OrderStatus.CONFIRMED, OrderStatus.PROCESSING, OrderStatus.SHIPPED):
            order = order_services.transition(order, status)

        order = order_services.transition(order, OrderStatus.DELIVERED)

        payment = PaymentTransaction.objects.get(reference_id=str(order.pk))
        assert payment.status == TransactionStatus.CAPTURED
        assert payment.captured_at is not None

        order.refresh_from_db()
        assert order.payment_status == PaymentStatus.PAID

    def test_a_manual_capture_also_marks_the_order_paid(self, client, product, payment_provider):
        """
        ⚠️  `capture()` announces wherever it is called from.

            It used to announce from the webhook path alone, so a capture entered
            by hand changed the transaction and told nobody — and cash on delivery
            has no webhook by construction.
        """
        from orders.models import PaymentStatus
        from payments import services as payment_services
        from payments.models import PaymentTransaction

        order = self.place_order(client, product)
        payment_services.capture(PaymentTransaction.objects.get(reference_id=str(order.pk)))

        order.refresh_from_db()
        assert order.payment_status == PaymentStatus.PAID

    def test_capturing_twice_announces_once(self, client, product, payment_provider):
        """
        ⚠️  A delivery recorded after a manual capture must not announce again —
            the listeners write finance entries and loyalty points off it.
        """
        from payments import services as payment_services
        from payments.events import payment_captured
        from payments.models import PaymentTransaction

        order = self.place_order(client, product)
        payment = PaymentTransaction.objects.get(reference_id=str(order.pk))

        received = []

        def listener(sender, payment, **kwargs):
            received.append(payment.reference)

        payment_captured.connect(listener, weak=False)
        try:
            payment_services.capture(payment)
            payment_services.capture(payment)
        finally:
            payment_captured.disconnect(listener)

        assert len(received) == 1

    def test_delivery_does_not_capture_a_card_payment(self, client, product, db):
        """
        ⚠️  A card is captured by its gateway's inbound event.

            Capturing it from this side records a collection the gateway never
            made — the order reads paid and the money is nowhere.
        """
        from orders import services as order_services
        from orders.models import OrderStatus
        from payments.models import (
            PaymentMethodKind,
            PaymentProvider,
            PaymentTransaction,
            TransactionStatus,
        )

        PaymentProvider.objects.create(
            code="card-test",
            adapter_key="cash",
            name_ar="بطاقة",
            name_en="Card",
            supported_methods=[PaymentMethodKind.CARD],
            is_active=True,
        )

        client.post(
            reverse("v1:cart:lines"),
            {"product": str(product.pk), "quantity": 1},
            format="json",
        )
        response = client.post(
            reverse("v1:orders:checkout"),
            {"address": ADDRESS, "payment_method": "CARD"},
            format="json",
        )
        assert response.status_code == 201

        from orders.models import Order

        order = Order.objects.get(pk=response.data["order"]["id"])
        for status in (OrderStatus.CONFIRMED, OrderStatus.PROCESSING, OrderStatus.SHIPPED):
            order = order_services.transition(order, status)
        order_services.transition(order, OrderStatus.DELIVERED)

        payment = PaymentTransaction.objects.get(reference_id=str(order.pk))
        assert payment.status == TransactionStatus.AUTHORIZED
