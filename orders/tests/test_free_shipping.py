"""
Free shipping above an amount — what the cart shows and what the order is charged.

⚠️  The server decides. The cart payload says where the customer stands, the
    checkout and the guest checkout price the order from the cart again, and
    nothing the browser sends can claim a qualifying total.
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from cart import services as cart_services
from customers.models import CustomerProfile
from orders import services as order_services
from orders.models import Order
from orders.tests.guest_support import PASSWORD, add_to_cart, checkout, guest_client
from promotions.models import Coupon, CouponKind
from shipping import services as shipping_services
from shipping.models import ShippingMethod, ShippingRate, ShippingZone

pytest_plugins = ["orders.tests.guest_support"]

pytestmark = pytest.mark.django_db

CAIRO = "القاهرة"
ADDRESS = {
    "recipient_name": "أحمد محمود",
    "phone": "+201001234567",
    "governorate": CAIRO,
    "city": "مدينة نصر",
    "street": "شارع ١",
}


def turn_on(threshold="500.00"):
    shipping_services.save_free_shipping_rule(enabled=True, threshold=Decimal(threshold))


@pytest.fixture
def methods(world):
    """`standard` (30) from the shared world, plus a paid-only express and a pickup."""
    zone = ShippingZone.objects.get(code="cairo")
    express = ShippingMethod.objects.create(
        code="express", name_ar="سريع", name_en="Express", eligible_for_free_shipping=False
    )
    pickup = ShippingMethod.objects.create(
        code="pickup", name_ar="استلام", name_en="Pickup", is_pickup=True
    )
    ShippingRate.objects.create(zone=zone, method=express, base_fee=Decimal("60.00"))
    ShippingRate.objects.create(zone=zone, method=pickup, base_fee=Decimal("0.00"))
    return world


@pytest.fixture
def buyer(db):
    user = User.objects.create_user(
        email="free-ship@test.local", password=PASSWORD, account_type=AccountType.STUDENT
    )
    user.is_active = True
    user.save()
    CustomerProfile.objects.create(user=user)
    return user


@pytest.fixture
def member(buyer):
    client = APIClient()
    client.force_authenticate(user=buyer)
    return client


def member_cart(member, product, quantity, **params):
    add = member.post(
        reverse("v1:cart:lines"), {"product": str(product.pk), "quantity": quantity}, format="json"
    )
    assert add.status_code == 201, add.data
    return member.get(reverse("v1:cart:detail"), params).data


# ═══════════════════════════════════════════════════════════
#  The cart payload
# ═══════════════════════════════════════════════════════════


class TestCartPayload:
    def test_disabled_draws_nothing(self, methods, member, product):
        cart = member_cart(member, product, 5)

        assert cart["free_shipping"] == {
            "enabled": False,
            "threshold": "0.00",
            "qualifies": False,
            "remaining": "0.00",
        }

    def test_below_the_threshold_says_how_much_is_missing(self, methods, member, product):
        turn_on("500.00")

        cart = member_cart(member, product, 4)  # 400

        assert cart["free_shipping"] == {
            "enabled": True,
            "threshold": "500.00",
            "qualifies": False,
            "remaining": "100.00",
        }

    def test_exactly_the_threshold_qualifies(self, methods, member, product):
        turn_on("500.00")

        cart = member_cart(member, product, 5)  # 500

        assert cart["free_shipping"]["qualifies"] is True
        assert cart["free_shipping"]["remaining"] == "0.00"

    def test_one_piastre_short_does_not(self, methods, member, product):
        turn_on("500.01")

        cart = member_cart(member, product, 5)  # 500.00

        assert cart["free_shipping"]["qualifies"] is False
        assert cart["free_shipping"]["remaining"] == "0.01"

    def test_totals_follow_the_chosen_method(self, methods, member, product):
        turn_on("500.00")

        cart = member_cart(member, product, 5, governorate=CAIRO, shipping_method="standard")
        assert cart["totals"]["shipping_amount"] == "0.00"
        assert cart["totals"]["total"] == "570.00"  # 500 + 14% tax, no shipping

        express = member.get(
            reverse("v1:cart:detail"), {"governorate": CAIRO, "shipping_method": "express"}
        ).data
        assert express["totals"]["shipping_amount"] == "60.00"

    def test_a_coupon_that_drops_the_cart_under_the_threshold_takes_it_away(
        self, methods, member, product
    ):
        """
        ⚠️  The amount is after the coupon: 500 − 20% = 400 < 450, so shipping is charged again.
        """
        turn_on("450.00")
        Coupon.objects.create(
            code="SAVE20",
            name_ar="خصم",
            name_en="Discount",
            kind=CouponKind.PERCENTAGE,
            value=Decimal("20.00"),
        )
        qualifying = member_cart(member, product, 5, governorate=CAIRO, shipping_method="standard")
        assert qualifying["free_shipping"]["qualifies"] is True
        assert qualifying["totals"]["shipping_amount"] == "0.00"

        applied = member.post(reverse("v1:cart:coupon"), {"code": "SAVE20"}, format="json")
        assert applied.status_code == 200
        assert applied.data["coupon"]["is_valid"] is True

        after = member.get(
            reverse("v1:cart:detail"), {"governorate": CAIRO, "shipping_method": "standard"}
        ).data
        assert after["free_shipping"]["qualifies"] is False
        assert after["free_shipping"]["remaining"] == "50.00"
        assert after["totals"]["shipping_amount"] == "30.00"

    def test_item_discounts_count_too(self, methods, product, buyer):
        """The amount is the net of the lines, not the list price."""
        turn_on("500.00")
        cart = cart_services.get_active_cart(user=buyer)
        cart_services.add_line(cart, product, 5, user=buyer)
        snapshot = cart_services.revalidate(cart, user=buyer)

        assert snapshot.free_shipping.qualifies is True
        assert snapshot.priced.net_sales == Decimal("500.00")

    def test_guest_cart_has_it_too(self, methods, product):
        turn_on("500.00")
        guest = guest_client()
        add_to_cart(guest, product, 2)

        status = guest.get(reverse("v1:cart:detail")).data["free_shipping"]
        assert (status["enabled"], status["qualifies"], status["remaining"]) == (
            True,
            False,
            "300.00",
        )


# ═══════════════════════════════════════════════════════════
#  The order is priced on the server
# ═══════════════════════════════════════════════════════════


class TestOrderPricing:
    def test_qualifying_order_ships_free_and_records_why(self, methods, buyer, product):
        turn_on("500.00")
        cart = cart_services.get_active_cart(user=buyer)
        cart_services.add_line(cart, product, 5, user=buyer)

        order = order_services.create_from_cart(
            cart, customer=buyer.customer_profile, address=ADDRESS, shipping_method_code="standard"
        )

        assert order.shipping_total == Decimal("0.00")
        assert order.shipping_discount == Decimal("30.00")
        assert order.grand_total == Decimal("570.00")

    def test_below_the_threshold_pays_the_rate(self, methods, buyer, product):
        turn_on("500.00")
        cart = cart_services.get_active_cart(user=buyer)
        cart_services.add_line(cart, product, 4, user=buyer)

        order = order_services.create_from_cart(
            cart, customer=buyer.customer_profile, address=ADDRESS, shipping_method_code="standard"
        )

        assert order.shipping_total == Decimal("30.00")
        assert order.shipping_discount == Decimal("0.00")

    def test_off_means_off(self, methods, buyer, product):
        cart = cart_services.get_active_cart(user=buyer)
        cart_services.add_line(cart, product, 20, user=buyer)

        order = order_services.create_from_cart(
            cart, customer=buyer.customer_profile, address=ADDRESS, shipping_method_code="standard"
        )

        assert order.shipping_total == Decimal("30.00")
        assert order.shipping_discount == Decimal("0.00")

    def test_ineligible_method_keeps_its_price(self, methods, buyer, product):
        turn_on("500.00")
        cart = cart_services.get_active_cart(user=buyer)
        cart_services.add_line(cart, product, 5, user=buyer)

        order = order_services.create_from_cart(
            cart, customer=buyer.customer_profile, address=ADDRESS, shipping_method_code="express"
        )

        assert order.shipping_total == Decimal("60.00")
        assert order.shipping_discount == Decimal("0.00")

    def test_pickup_is_free_by_nature_not_by_the_rule(self, methods, buyer, product):
        turn_on("500.00")
        cart = cart_services.get_active_cart(user=buyer)
        cart_services.add_line(cart, product, 5, user=buyer)

        order = order_services.create_from_cart(
            cart, customer=buyer.customer_profile, address=ADDRESS, shipping_method_code="pickup"
        )

        assert order.shipping_total == Decimal("0.00")
        assert order.shipping_discount == Decimal("0.00")

    def test_coupon_dropping_below_the_threshold_charges_shipping(self, methods, buyer, product):
        turn_on("450.00")
        Coupon.objects.create(
            code="SAVE20",
            name_ar="خصم",
            name_en="Discount",
            kind=CouponKind.PERCENTAGE,
            value=Decimal("20.00"),
        )
        cart = cart_services.get_active_cart(user=buyer)
        cart_services.add_line(cart, product, 5, user=buyer)
        cart_services.apply_coupon(cart, "SAVE20")

        order = order_services.create_from_cart(
            cart, customer=buyer.customer_profile, address=ADDRESS, shipping_method_code="standard"
        )

        assert order.coupon_discount == Decimal("100.00")
        assert order.shipping_total == Decimal("30.00")
        assert order.shipping_discount == Decimal("0.00")

    def test_signed_in_checkout_ignores_a_claimed_shipping_amount(
        self, methods, cod, member, product
    ):
        """
        ⚠️  Free shipping by editing a field in the browser: the body claims zero, the
            cart is one item short of the threshold, and the order is charged the rate.
        """
        turn_on("500.00")
        member_cart(member, product, 4)

        response = member.post(
            reverse("v1:orders:checkout"),
            {
                "address": ADDRESS,
                "shipping_method_code": "standard",
                "payment_method": "COD",
                "shipping_total": "0.00",
                "shipping_amount": "0.00",
                "shipping_fee": "0.00",
                "shipping_discount": "30.00",
                "free_shipping": True,
                "eligible_amount": "99999.00",
            },
            format="json",
        )

        assert response.status_code == 201, response.data
        order = Order.objects.get(pk=response.data["order"]["id"])
        assert order.shipping_total == Decimal("30.00")
        assert order.shipping_discount == Decimal("0.00")

    def test_a_display_quote_cannot_be_used_to_claim_it(self, methods, cod, member, product):
        """The quote endpoint trusts the amount it is shown; the order never does."""
        turn_on("500.00")
        member_cart(member, product, 1)
        shown = APIClient().get(
            reverse("v1:shipping:quote"),
            {"governorate": CAIRO, "subtotal": "99999", "eligible_amount": "99999"},
        )
        standard = next(q for q in shown.data["quotes"] if q["method_code"] == "standard")
        assert standard["fee"] == "0.00"  # what a forged hint displays …

        response = member.post(
            reverse("v1:orders:checkout"),
            {"address": ADDRESS, "shipping_method_code": "standard", "payment_method": "COD"},
            format="json",
        )

        assert response.status_code == 201, response.data
        assert Order.objects.get(pk=response.data["order"]["id"]).shipping_total == Decimal(
            "30.00"
        )  # … and what is really charged

    def test_signed_in_checkout_over_http_waives_it(self, methods, cod, member, product):
        turn_on("500.00")
        member_cart(member, product, 5)

        response = member.post(
            reverse("v1:orders:checkout"),
            {"address": ADDRESS, "shipping_method_code": "standard", "payment_method": "COD"},
            format="json",
        )

        assert response.status_code == 201, response.data
        assert response.data["order"]["shipping_total"] == "0.00"
        assert response.data["order"]["shipping_discount"] == "30.00"
        assert response.data["order"]["grand_total"] == "570.00"


# ═══════════════════════════════════════════════════════════
#  Guest checkout
# ═══════════════════════════════════════════════════════════


class TestGuestCheckout:
    def test_guest_over_the_threshold_ships_free(self, methods, cod, product):
        turn_on("500.00")
        guest = guest_client()
        add_to_cart(guest, product, 5)

        response = checkout(guest)

        assert response.status_code == 201, response.data
        assert response.data["totals"]["shipping_total"] == "0.00"
        order = Order.objects.get(number=response.data["order_number"])
        assert order.shipping_discount == Decimal("30.00")
        assert order.grand_total == Decimal("570.00")

    def test_guest_under_the_threshold_pays(self, methods, cod, product):
        turn_on("500.00")
        guest = guest_client()
        add_to_cart(guest, product, 4)

        response = checkout(guest)

        assert response.status_code == 201, response.data
        assert response.data["totals"]["shipping_total"] == "30.00"
        order = Order.objects.get(number=response.data["order_number"])
        assert order.shipping_discount == Decimal("0.00")

    def test_guest_cannot_claim_it(self, methods, cod, product):
        turn_on("500.00")
        guest = guest_client()
        add_to_cart(guest, product, 1)

        response = checkout(guest, shipping_total="0.00", free_shipping=True)

        # Either the unknown keys are refused or they are ignored — never honoured
        if response.status_code == 201:
            assert response.data["totals"]["shipping_total"] == "30.00"
        else:
            assert response.status_code == 400

    def test_guest_ineligible_method_keeps_its_price(self, methods, cod, product):
        turn_on("500.00")
        guest = guest_client()
        add_to_cart(guest, product, 5)

        response = checkout(guest, shipping_method_code="express")

        assert response.status_code == 201, response.data
        assert response.data["totals"]["shipping_total"] == "60.00"

    def test_guest_off_means_charged(self, methods, cod, product):
        guest = guest_client()
        add_to_cart(guest, product, 8)

        response = checkout(guest)

        assert response.status_code == 201, response.data
        assert response.data["totals"]["shipping_total"] == "30.00"
