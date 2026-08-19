"""
Order tests — the complete purchase cycle.

⚠️  The critical groups:
      1. snapshots — an issued invoice does not change as the catalogue changes
      2. the state machine — a disallowed transition is refused
      3. re-validation — no order at a stale price or with missing stock
      4. cancellation — stock and coupon both come back
"""

from decimal import Decimal

import pytest
from django.apps import apps

from accounts.models import AccountType, User
from cart import services as cart_services
from cart.models import CartStatus
from catalog.models import Category, Product
from core.errors import BusinessError
from core.models.tax import TaxClass
from customers.models import CustomerProfile
from inventory import services as inventory_services
from orders import services as order_services
from orders.models import Order, OrderChannel, OrderStatus, PaymentStatus
from promotions.models import Coupon, CouponKind, CouponRedemption

PASSWORD = "Str0ng-Test-Pass!23"


# ⚠️  String references rather than imports — **and lazy ones**.
#
#     `orders` is in L6 and `inventory` in L3, and the contract forbids
#     importing another domain's models directly. The test is not an exception.
#
#     And the laziness is necessary: `apps.get_model` at module level runs
#     before the app registry is loaded and fails with AppRegistryNotReady.


def stock_model():
    return apps.get_model("inventory", "Stock")


def location_model():
    return apps.get_model("inventory", "StockLocation")


ADDRESS = {
    "recipient_name": "أحمد محمود",
    "phone": "+201001234567",
    "governorate": "القاهرة",
    "city": "مدينة نصر",
    "street": "شارع ١",
}


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
def product(db, tax_class, location):
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
def cart(user, product):
    cart = cart_services.get_active_cart(user=user)
    cart_services.add_line(cart, product, 2, user=user)
    return cart


def make_order(cart, customer, **kwargs):
    return order_services.create_from_cart(cart, customer=customer, address=ADDRESS, **kwargs)


# ═══════════════════════════════════════════════════════════
#  Snapshots —  ADR-30
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSnapshots:
    def test_line_captures_price_and_tax_rate(self, cart, customer, product):
        order = make_order(cart, customer)
        line = order.lines.first()

        assert line.unit_price == Decimal("100.00")
        assert line.tax_rate == Decimal("14.00")
        assert line.tax_amount == Decimal("28.00")  # 14% on 200
        assert line.product_sku == "P-001"
        assert line.product_name_ar == "منتج"

    def test_price_change_does_not_alter_issued_order(self, cart, customer, product):
        """
        ⚠️  **The heart of the snapshot.**

        An issued invoice does not change when the catalogue price changes afterwards.
        """
        order = make_order(cart, customer)
        original_total = order.grand_total

        product.base_price = Decimal("500.00")
        product.save()

        order.refresh_from_db()
        line = order.lines.first()

        assert line.unit_price == Decimal("100.00")
        assert order.grand_total == original_total

    def test_tax_rate_change_does_not_alter_issued_order(self, cart, customer, tax_class):
        """
        ⚠️  The rate changes by government decree; old invoices keep their rate.

        Computing it later from the current rate falsifies the accounting record.
        """
        order = make_order(cart, customer)

        tax_class.rate = Decimal("20.00")
        tax_class.save()

        order.refresh_from_db()
        assert order.lines.first().tax_rate == Decimal("14.00")

    def test_product_rename_does_not_alter_invoice(self, cart, customer, product):
        order = make_order(cart, customer)

        product.name_ar = "اسم جديد تمامًا"
        product.save()

        order.refresh_from_db()
        assert order.lines.first().product_name_ar == "منتج"

    def test_totals_are_consistent(self, cart, customer):
        order = make_order(cart, customer)

        # 2 × 100 = 200 · tax 28 · total 228
        assert order.subtotal == Decimal("200.00")
        assert order.tax_total == Decimal("28.00")
        assert order.grand_total == Decimal("228.00")


# ═══════════════════════════════════════════════════════════
#  Early fields —  ADR-09
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEarlyFields:
    def test_channel_defaults_to_online(self, cart, customer):
        assert make_order(cart, customer).channel == OrderChannel.ONLINE

    def test_channel_supports_pos_before_phase_seven(self, cart, customer, location):
        """
        ⚠️  Point of sale arrives in phase 7, and the field works now.

        Adding it after orders have accumulated means every previous order has
        no channel — so no sales report can separate the channels retrospectively.
        """
        order = make_order(cart, customer, channel=OrderChannel.POS, location=location)
        assert order.channel == OrderChannel.POS
        assert order.location == location

    def test_attribution_fields_exist_and_stay_empty(self, cart, customer):
        """The attribution fields are created now and populated in phase 10."""
        order = make_order(cart, customer)

        assert order.owner_employee is None
        assert order.commission_employee is None

        names = {f.name for f in Order._meta.get_fields()}
        assert {"created_by", "owner_employee", "commission_employee"} <= names

    def test_location_is_recorded(self, cart, customer, location):
        assert make_order(cart, customer).location == location


# ═══════════════════════════════════════════════════════════
#  The state machine
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestStateMachine:
    def test_valid_path_to_completion(self, cart, customer):
        order = make_order(cart, customer)

        for status in (
            OrderStatus.CONFIRMED,
            OrderStatus.PROCESSING,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
        ):
            order = order_services.transition(order, status)
            assert order.status == status

        order = order_services.complete(order)
        assert order.status == OrderStatus.COMPLETED

    def test_illegal_transition_is_rejected(self, cart, customer):
        """
        ⚠️  Without a state machine, a "completed" order returns to "pending" in
            one call — corrupting every sales report and every computed commission.
        """
        order = make_order(cart, customer)

        with pytest.raises(BusinessError) as exc:
            order_services.transition(order, OrderStatus.DELIVERED)

        assert exc.value.code == "INVALID_STATE_TRANSITION"
        assert exc.value.status_code == 409

    def test_terminal_states_have_no_exit(self, cart, customer):
        order = make_order(cart, customer)
        order_services.cancel(order, reason="اختبار")

        for status in (OrderStatus.CONFIRMED, OrderStatus.PROCESSING):
            with pytest.raises(BusinessError):
                order_services.transition(order, status)

    def test_every_transition_is_recorded(self, cart, customer):
        order = make_order(cart, customer)
        order_services.transition(order, OrderStatus.CONFIRMED, note="دفع مؤكد")

        history = order.status_history.all()
        assert history.count() == 2  # creation + confirmation
        assert history.filter(to_status=OrderStatus.CONFIRMED, note="دفع مؤكد").exists()

    def test_payment_status_is_independent_of_order_status(self, cart, customer):
        """
        ⚠️  A confirmed order may be unpaid (cash on delivery), and a cancelled
            order may be paid and awaiting a refund.
        """
        order = make_order(cart, customer)
        assert order.payment_status == PaymentStatus.UNPAID

        order = order_services.transition(order, OrderStatus.CONFIRMED)
        assert order.payment_status == PaymentStatus.UNPAID

    def test_marking_paid_confirms_a_pending_order(self, cart, customer):
        order = make_order(cart, customer)
        order = order_services.mark_paid(order)

        assert order.payment_status == PaymentStatus.PAID
        assert order.status == OrderStatus.CONFIRMED

    def test_cannot_pay_twice(self, cart, customer):
        order = order_services.mark_paid(make_order(cart, customer))

        with pytest.raises(BusinessError) as exc:
            order_services.mark_paid(order)
        assert exc.value.code == "ORDER_ALREADY_PAID"


# ═══════════════════════════════════════════════════════════
#  Stock
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestInventoryIntegration:
    def test_order_reserves_not_deducts(self, cart, customer, product, location):
        """
        ⚠️  The order reserves; shipping deducts.

        Deducting at creation means goods missing from the balance for an order
        that may be cancelled a minute later.
        """
        make_order(cart, customer)

        stock = stock_model().objects.get(product=product, location=location)
        assert stock.quantity_physical == 50
        assert stock.quantity_reserved == 2
        assert stock.available == 48

    def test_shipping_commits_the_reservation(self, cart, customer, product, location):
        order = make_order(cart, customer)

        for status in (
            OrderStatus.CONFIRMED,
            OrderStatus.PROCESSING,
            OrderStatus.SHIPPED,
        ):
            order = order_services.transition(order, status)

        stock = stock_model().objects.get(product=product, location=location)
        assert stock.quantity_physical == 48
        assert stock.quantity_reserved == 0

    def test_cancelling_releases_the_reservation(self, cart, customer, product, location):
        order = make_order(cart, customer)
        order_services.cancel(order, reason="غيّر رأيه")

        stock = stock_model().objects.get(product=product, location=location)
        assert stock.quantity_reserved == 0
        assert stock.available == 50

    def test_order_fails_when_stock_ran_out(self, user, customer, product, location):
        """Stock may run out between adding to the cart and checking out."""
        cart = cart_services.get_active_cart(user=user)
        cart_services.add_line(cart, product, 10, user=user)

        # Another buyer consumes all the stock
        inventory_services.sell_immediately(product, 50, location=location)

        with pytest.raises(BusinessError) as exc:
            make_order(cart, customer)
        assert exc.value.code == "INSUFFICIENT_STOCK"


# ═══════════════════════════════════════════════════════════
#  Re-validation
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRevalidation:
    def test_deactivated_product_blocks_checkout(self, cart, customer, product):
        product.is_active = False
        product.save()

        with pytest.raises(BusinessError) as exc:
            make_order(cart, customer)
        assert exc.value.code == "PRODUCT_UNAVAILABLE"

    def test_empty_cart_is_rejected(self, user, customer):
        cart = cart_services.get_active_cart(user=user)

        with pytest.raises(BusinessError) as exc:
            make_order(cart, customer)
        assert exc.value.code == "CART_EMPTY"

    def test_price_is_recomputed_not_taken_from_client(self, user, customer, product, location):
        """
        ⚠️  Any prices the frontend sends are ignored entirely.

        The price is recomputed from the source when the order is created.
        """
        cart = cart_services.get_active_cart(user=user)
        cart_services.add_line(cart, product, 1, user=user)

        product.base_price = Decimal("250.00")
        product.save()

        order = make_order(cart, customer)
        assert order.lines.first().unit_price == Decimal("250.00")

    def test_cart_is_marked_converted(self, cart, customer):
        make_order(cart, customer)
        cart.refresh_from_db()

        assert cart.status == CartStatus.CONVERTED
        assert cart.converted_at is not None


# ═══════════════════════════════════════════════════════════
#  Coupons
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCouponIntegration:
    @pytest.fixture
    def coupon(self, db):
        return Coupon.objects.create(
            code="SAVE10",
            name_ar="خصم ١٠٪",
            name_en="10% off",
            kind=CouponKind.PERCENTAGE,
            value=Decimal("10.00"),
        )

    def test_coupon_reduces_the_total(self, cart, customer, coupon):
        cart_services.apply_coupon(cart, "SAVE10")
        order = make_order(cart, customer)

        assert order.coupon_code == "SAVE10"
        assert order.coupon_discount == Decimal("20.00")  # 10% of 200

    def test_redemption_is_recorded(self, cart, customer, coupon, user):
        cart_services.apply_coupon(cart, "SAVE10")
        order = make_order(cart, customer)

        redemption = CouponRedemption.objects.get(coupon=coupon, user=user)
        assert redemption.reference_id == str(order.pk)

        coupon.refresh_from_db()
        assert coupon.usage_count == 1

    def test_cancelling_the_order_restores_the_coupon(self, cart, customer, coupon):
        """
        ⚠️  The record remains and the counter decrements.

        Deleting erases the audit trail: nothing is left to prove this customer
        used the coupon and then cancelled.
        """
        cart_services.apply_coupon(cart, "SAVE10")
        order = make_order(cart, customer)
        order_services.cancel(order, reason="اختبار")

        coupon.refresh_from_db()
        assert coupon.usage_count == 0

        redemption = CouponRedemption.objects.get(coupon=coupon)
        assert redemption.is_cancelled
        assert redemption.cancelled_at is not None

    def test_lowercase_code_is_accepted(self, cart, customer, coupon):
        """`SAVE10` and `save10` are one coupon."""
        snapshot = cart_services.apply_coupon(cart, "save10")
        assert snapshot.coupon_result.is_valid


# ═══════════════════════════════════════════════════════════
#  Cancellation
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCancellation:
    def test_reason_is_required(self, cart, customer):
        order = make_order(cart, customer)

        with pytest.raises(BusinessError):
            order_services.cancel(order, reason="")

    def test_shipped_order_cannot_be_cancelled_after_delivery(self, cart, customer):
        order = make_order(cart, customer)
        for status in (
            OrderStatus.CONFIRMED,
            OrderStatus.PROCESSING,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
        ):
            order = order_services.transition(order, status)

        with pytest.raises(BusinessError) as exc:
            order_services.cancel(order, reason="متأخر")
        assert exc.value.code == "ORDER_CANNOT_BE_CANCELLED"

    def test_cancellation_records_reason_and_time(self, cart, customer):
        order = make_order(cart, customer)
        order_services.cancel(order, reason="نفد الصبر")

        order.refresh_from_db()
        assert order.status == OrderStatus.CANCELLED
        assert order.cancellation_reason == "نفد الصبر"
        assert order.cancelled_at is not None


# ═══════════════════════════════════════════════════════════
#  Domain boundaries
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestDomainBoundaries:
    def test_orders_does_not_import_inventory_models(self):
        """
        ⚠️  The legacy code edited `product.quantity` directly from
            `orders/api.py` — one domain writing into another domain's model.
        """
        import inspect

        from orders import services

        source = inspect.getsource(services)
        assert "from inventory.models" not in source
        assert "from catalog.models" not in source

    def test_orders_does_not_reimplement_coupon_logic(self):
        """
        ⚠️  The logic was implemented twice, in two places that drifted apart —
            a coupon accepted on one path and refused on another.
        """
        import inspect

        from orders import services

        source = inspect.getsource(services)
        assert "promotion_services.validate" not in source
        assert "promotion_services" in source  # it calls rather than duplicating

    def test_order_number_is_not_the_url_identifier(self, cart, customer):
        """`ORD-2026-XXXXXX` for display · the URL carries a UUID."""
        import uuid

        order = make_order(cart, customer)
        assert order.number.startswith("ORD-")
        assert isinstance(order.pk, uuid.UUID)
