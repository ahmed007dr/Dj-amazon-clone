"""
Guest checkout over HTTP — buying without an account.

⚠️  Owner decisions these tests pin:

      * PUBLIC products only; every other policy stays login-only
      * cash on delivery only · no coupons · no loyalty
      * stock is held longer than a card checkout, and released if nobody confirms
      * the buyer's access is a signed link — never the order number
      * an account is never attached by email at checkout
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.apps import apps
from django.core import signing
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from cart.models import Cart, CartLine, CartStatus
from customers.models import CustomerProfile
from inventory import services as inventory_services
from orders import guest, services
from orders.models import Order, OrderChannel, OrderStatus
from orders.tests.guest_support import (
    FORM,
    PASSWORD,
    SESSION,
    add_to_cart,
    available,
    checkout,
    guest_client,
    make_product,
    place,
)
from payments.models import PaymentMethodKind, PaymentTransaction
from shipping.models import ShippingMethod

pytest_plugins = ["orders.tests.guest_support"]

# ═══════════════════════════════════════════════════════════
#  The happy path
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPlacingAnOrder:
    def test_a_visitor_buys_without_an_account(self, world):
        client, response = place(world, quantity=2)

        assert response.status_code == 201, response.data
        body = response.data
        assert body["order_number"].startswith("ORD-")
        assert body["status"] == "PENDING"
        assert body["tracking_token"]
        assert body["replayed"] is False
        # 2 × 100 + 14% tax + 30 shipping
        assert body["totals"]["grand_total"] == "258.00"
        assert body["totals"]["shipping_total"] == "30.00"

        order = Order.objects.get(number=body["order_number"])
        # ⚠️  A guest order: no account, no dummy account, but an email
        assert order.customer is None
        assert order.channel == OrderChannel.ONLINE
        assert order.is_guest
        assert order.contact_email == "ahmed.buyer@example.com"  # lower-cased
        assert order.contact_language == "en"
        assert order.recipient_name == "أحمد محمود"
        assert order.recipient_phone == "+201001234567"  # canonical form
        assert order.governorate == "القاهرة"
        assert order.customer_note == "اتصل قبل الوصول"
        assert order.shipping_method_code == "standard"
        assert order.lines.count() == 1
        assert order.coupon_code == ""
        assert not CustomerProfile.objects.exists(), "no shadow customer may ever be created"
        assert not User.objects.exists(), "no shadow user either"

    def test_the_order_is_cash_on_delivery_with_a_payment_record(self, world):
        _, response = place(world)
        order = Order.objects.get(number=response.data["order_number"])

        payment = PaymentTransaction.objects.get(reference_type="order", reference_id=str(order.pk))
        assert payment.method == PaymentMethodKind.CASH_ON_DELIVERY
        assert payment.amount == order.grand_total
        assert payment.customer is None
        assert order.payment_status == "UNPAID"  # collected at the door, not now

    def test_stock_is_reserved_for_longer_than_a_card_checkout(self, world, settings):
        settings.GUEST_ORDER_RESERVATION_HOURS = 72
        before = available(world)

        _, response = place(world, quantity=3)
        order = Order.objects.get(number=response.data["order_number"])

        assert available(world) == before - 3
        reservations = inventory_services.active_reservations_for("order", order.pk)
        assert len(reservations) == 1
        hold = reservations[0].expires_at - timezone.now()
        assert timedelta(hours=71) < hold <= timedelta(hours=72, minutes=1)

    def test_the_reservation_length_is_configurable(self, world, settings):
        settings.GUEST_ORDER_RESERVATION_HOURS = 6
        _, response = place(world)
        order = Order.objects.get(number=response.data["order_number"])

        hold = inventory_services.active_reservations_for("order", order.pk)[0].expires_at
        assert hold - timezone.now() < timedelta(hours=7)

    def test_a_status_history_row_and_a_shipment_exist(self, world):
        _, response = place(world)
        order = Order.objects.get(number=response.data["order_number"])

        assert order.status_history.count() == 1
        from shipping import services as shipping_services  # noqa: F401  (shape check below)

        shipment = apps.get_model("shipping", "Shipment").objects.get(reference_id=str(order.pk))
        assert shipment.recipient_phone == "+201001234567"
        assert shipment.governorate == "القاهرة"

    def test_the_cart_is_converted_and_the_next_one_starts_empty(self, world):
        client, _ = place(world)

        assert Cart.objects.get(session_key=SESSION, status=CartStatus.CONVERTED)
        cart = client.get(reverse("v1:cart:detail"))
        assert cart.data["totals"]["item_count"] == 0

    def test_checking_out_with_an_empty_cart_is_refused(self, world):
        response = checkout(guest_client())
        assert response.status_code == 400
        assert response.data["code"] == "CART_EMPTY"
        assert not Order.objects.exists()

    def test_the_cart_header_is_required_and_validated(self, world):
        response = checkout(APIClient())
        assert response.status_code == 400

        response = checkout(guest_client("not-a-uuid"))
        assert response.status_code == 400
        assert not Order.objects.exists()

    def test_it_never_touches_a_members_cart(self, world):
        """The endpoint ignores identity: a signed-in user's cart is not reachable here."""
        member = User.objects.create_user(
            email="member@test.local", password=PASSWORD, account_type=AccountType.STUDENT
        )
        member.is_active = True
        member.save()
        CustomerProfile.objects.create(user=member)

        authed = APIClient()
        authed.force_authenticate(user=member)
        add_to_cart(authed, world)

        # Even sending the member's token, the guest endpoint looks at the session header only
        authed.credentials(HTTP_X_CART_SESSION=SESSION)
        response = checkout(authed)

        assert response.status_code == 400  # the *guest* cart is empty
        assert response.data["code"] == "CART_EMPTY"
        assert Cart.objects.get(user=member).lines.count() == 1


# ═══════════════════════════════════════════════════════════
#  Validation
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestValidation:
    @pytest.mark.parametrize(
        ("raw", "canonical"),
        [
            ("01001234567", "+201001234567"),
            ("010 0123 4567", "+201001234567"),
            ("010-0123-4567", "+201001234567"),
            ("+201001234567", "+201001234567"),
            ("00201001234567", "+201001234567"),
            ("201001234567", "+201001234567"),
            ("1001234567", "+201001234567"),
            ("٠١٠٠١٢٣٤٥٦٧", "+201001234567"),  # Arabic-Indic digits
            ("01112345678", "+201112345678"),
            ("01212345678", "+201212345678"),
            ("01512345678", "+201512345678"),
        ],
    )
    def test_egyptian_mobiles_are_accepted_and_normalised(self, world, raw, canonical):
        _, response = place(world, phone=raw, email=f"{abs(hash(raw))}@x.com")
        assert response.status_code == 201, response.data
        assert Order.objects.get().recipient_phone == canonical

    @pytest.mark.parametrize(
        "bad",
        [
            "0100123456",  # one digit short
            "010012345678",  # one digit long
            "01301234567",  # 013 is not a mobile prefix
            "0223456789",  # a Cairo landline: the owner must be able to ring it on a mobile
            "abcdefghijk",
            "+441234567890",
            "",
            "0" * 40,
        ],
    )
    def test_other_numbers_are_refused(self, world, bad):
        _, response = place(world, phone=bad)
        assert response.status_code == 400
        assert not Order.objects.exists()

    @pytest.mark.parametrize("bad", ["", "no-at-sign", "a@", "@b.com", "a b@c.com", "x" * 300])
    def test_a_bad_email_is_refused(self, world, bad):
        _, response = place(world, email=bad)
        assert response.status_code == 400

    @pytest.mark.parametrize("bad", ["Atlantis", "القاهره", "cairo", "", "الجيزة "])
    def test_the_governorate_must_be_from_the_closed_list(self, world, bad):
        """
        ⚠️  Shipping is priced by matching this literally against the zones: a
            near-miss spelling would silently fall to the default zone's fee.
        """
        _, response = place(world, governorate=bad)
        assert response.status_code == 400
        assert not Order.objects.exists()

    def test_every_listed_governorate_is_accepted_by_the_serializer(self):
        from orders.guest_serializers import GuestCheckoutSerializer
        from shipping.governorates import EGYPT_GOVERNORATES

        for name in EGYPT_GOVERNORATES:
            serializer = GuestCheckoutSerializer(data={**FORM, "governorate": name})
            serializer.is_valid()
            assert "governorate" not in serializer.errors, name

    @pytest.mark.parametrize("field", ["recipient_name", "city", "street", "shipping_method_code"])
    def test_required_fields(self, world, field):
        _, response = place(world, **{field: ""})
        assert response.status_code == 400

    def test_a_short_street_is_refused(self, world):
        _, response = place(world, street="ش 1")
        assert response.status_code == 400

    def test_an_unavailable_shipping_method_is_refused_not_priced_at_zero(self, world):
        """
        ⚠️  An unknown/unoffered code used to price shipping at 0 and still
            create the order — free delivery by typing a code.
        """
        ShippingMethod.objects.create(code="express", name_ar="سريع", name_en="Express")
        _, unknown = place(world, shipping_method_code="no-such-method")
        assert unknown.status_code == 400

        client = guest_client("4a1c2b0e-8a52-4a0e-9f43-5b2e0c6a1d02")
        add_to_cart(client, world)
        offered_nowhere = checkout(client, shipping_method_code="express")
        assert offered_nowhere.status_code == 400
        assert not Order.objects.exists()

    def test_only_cod_is_accepted_as_a_payment_method(self, world):
        _, card = place(world, payment_method="CARD")
        assert card.status_code == 400

        client = guest_client("5b1c2b0e-8a52-4a0e-9f43-5b2e0c6a1d03")
        add_to_cart(client, world)
        explicit = checkout(client, payment_method="COD")
        assert explicit.status_code == 201

    @pytest.mark.parametrize("field", ["address_id", "address", "coupon", "coupon_code", "credit"])
    def test_account_only_fields_are_rejected_not_ignored(self, world, field):
        _, response = place(world, **{field: "x"})
        assert response.status_code == 400
        assert field in str(response.data)
        assert not Order.objects.exists()

    def test_a_name_with_stray_whitespace_is_tidied(self, world):
        _, response = place(world, recipient_name="  أحمد    محمود  ")
        assert response.status_code == 201
        assert Order.objects.get().recipient_name == "أحمد محمود"

    def test_totals_sent_by_the_client_are_ignored(self, world):
        _, response = place(world, grand_total="1.00", subtotal="1.00", shipping_total="0.00")
        assert response.status_code == 201
        assert response.data["totals"]["grand_total"] == "144.00"  # 100 + 14 + 30


# ═══════════════════════════════════════════════════════════
#  Cash on delivery must actually be available
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPaymentAvailability:
    def test_no_cod_gateway_means_no_order_and_no_stock_held(self, product, shipping, cod):
        cod.is_active = False
        cod.save()
        before = available(product)

        _, response = place(product)

        assert response.status_code == 409
        assert response.data["code"] == "PAYMENT_METHOD_UNAVAILABLE"
        # ⚠️  The whole order — and its stock reservation — rolled back
        assert not Order.objects.exists()
        assert available(product) == before


# ═══════════════════════════════════════════════════════════
#  Products a guest may not buy
# ═══════════════════════════════════════════════════════════

GUEST_MAY_BUY = {
    "public": True,
    "students": False,
    "professionals": False,
    "pharmacy_only": False,
    "wholesale": False,
    "registered": False,
    "otc_regulated": False,
}


@pytest.mark.django_db
@pytest.mark.parametrize(("code", "allowed"), list(GUEST_MAY_BUY.items()))
def test_checkout_per_seeded_access_policy(
    code, allowed, policies, category, location, tax_class, shipping, cod
):
    """
    The checkout leg of the policy matrix (add-to-cart and re-validation are in
    `cart/tests/test_guest_access.py`). The line is planted directly, as it would
    be if the policy had tightened after it was added.
    """
    assert set(GUEST_MAY_BUY) == set(policies), "a seeded policy has no guest expectation"
    item = make_product(f"POL-{code}", category, policies[code], location, tax_class)
    before = available(item)

    client = guest_client()
    client.get(reverse("v1:cart:detail"))  # opens the guest cart
    CartLine.objects.create(cart=Cart.objects.get(session_key=SESSION), product=item, quantity=1)

    response = checkout(client)

    if allowed:
        assert response.status_code == 201, response.data
        assert available(item) == before - 1
    else:
        assert response.status_code == 409
        assert response.data["code"] == "PRODUCT_ACCESS_DENIED"
        assert not Order.objects.exists()
        assert available(item) == before, "a refused checkout must hold no stock"


# ═══════════════════════════════════════════════════════════
#  Coupons and loyalty are for accounts
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestNoCouponsForGuests:
    def test_a_stale_coupon_on_a_guest_cart_gives_no_discount_and_is_not_stamped(self, world):
        from promotions.models import Coupon, CouponKind

        Coupon.objects.create(
            code="SAVE20",
            name_ar="خصم",
            name_en="Discount",
            kind=CouponKind.PERCENTAGE,
            value=Decimal("20.00"),
        )
        client = guest_client()
        add_to_cart(client, world)
        # Planted as if from before the rule existed — the apply endpoint refuses it now
        Cart.objects.filter(session_key=SESSION).update(coupon_code="SAVE20")

        response = checkout(client)

        assert response.status_code == 201, response.data
        order = Order.objects.get()
        assert order.coupon_discount == 0
        assert order.coupon_code == ""
        assert response.data["totals"]["grand_total"] == "144.00"
        from promotions.models import CouponRedemption

        assert not CouponRedemption.objects.exists()
        assert Coupon.objects.get(code="SAVE20").usage_count == 0


# ═══════════════════════════════════════════════════════════
#  Spam protection
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestHoneypot:
    def test_a_filled_trap_field_creates_nothing(self, world):
        before = available(world)
        _, response = place(world, website="http://spam.example")

        assert response.status_code == 400
        assert not Order.objects.exists()
        assert available(world) == before

    def test_an_empty_trap_field_is_fine(self, world):
        _, response = place(world, website="")
        assert response.status_code == 201

    def test_the_failure_is_a_plain_error_not_a_fake_success(self, world):
        """
        ⚠️  Deliberate: a browser extension that autofills every input must not
            leave a real customer believing an order exists.
        """
        _, response = place(world, website="x")
        assert "tracking_token" not in response.data
        assert "order_number" not in response.data


@pytest.mark.django_db
class TestCaptchaHook:
    def test_unset_means_no_captcha(self, world):
        _, response = place(world)
        assert response.status_code == 201

    def test_a_configured_verifier_gates_the_checkout(self, world, settings):
        settings.GUEST_CHECKOUT_CAPTCHA_VERIFIER = "orders.tests.test_guest_checkout.captcha_stub"

        _, refused = place(world, captcha_token="bad")
        assert refused.status_code == 400
        assert not Order.objects.exists()

        client = guest_client("6c1c2b0e-8a52-4a0e-9f43-5b2e0c6a1d04")
        add_to_cart(client, world)
        accepted = checkout(client, captcha_token="good")
        assert accepted.status_code == 201


def captcha_stub(token, request):
    return token == "good"


@pytest.mark.django_db
class TestOpenOrderCap:
    """⚠️  The exact (database-counted) brake on hoarding stock with fake COD orders."""

    def _order(self, world, n, **overrides):
        return place(
            world,
            session=f"7d1c2b0e-8a52-4a0e-9f43-5b2e0c6a{n:04d}",
            **overrides,
        )[1]

    def test_the_same_phone_cannot_stack_unconfirmed_orders(self, world, settings):
        settings.GUEST_CHECKOUT_MAX_OPEN_ORDERS = 3

        for n in range(3):
            response = self._order(world, n, email=f"person{n}@example.com")
            assert response.status_code == 201, response.data

        fourth = self._order(world, 3, email="person3@example.com")
        assert fourth.status_code == 429
        assert fourth.data["code"] == "RATE_LIMIT_EXCEEDED"
        assert Order.objects.count() == 3

    def test_the_same_email_cannot_either(self, world, settings):
        settings.GUEST_CHECKOUT_MAX_OPEN_ORDERS = 2

        for n in range(2):
            assert self._order(world, n, phone=f"010012345{n:02d}").status_code == 201

        # a different phone, the same email, in a different case
        blocked = self._order(world, 2, phone="01099999999", email="AHMED.BUYER@example.com")
        assert blocked.status_code == 429

    def test_other_people_are_unaffected(self, world, settings):
        settings.GUEST_CHECKOUT_MAX_OPEN_ORDERS = 1
        assert self._order(world, 0).status_code == 201

        other = self._order(world, 1, phone="01155556666", email="someone.else@example.com")
        assert other.status_code == 201

    def test_confirmed_and_cancelled_orders_do_not_count(self, world, settings):
        settings.GUEST_CHECKOUT_MAX_OPEN_ORDERS = 1
        first = self._order(world, 0)
        order = Order.objects.get(number=first.data["order_number"])

        assert self._order(world, 1).status_code == 429

        services.transition(order, OrderStatus.CONFIRMED)  # the owner phoned and confirmed
        assert self._order(world, 2).status_code == 201

    def test_old_orders_fall_out_of_the_window(self, world, settings):
        settings.GUEST_CHECKOUT_MAX_OPEN_ORDERS = 1
        settings.GUEST_CHECKOUT_OPEN_WINDOW_HOURS = 24
        first = self._order(world, 0)
        Order.objects.filter(number=first.data["order_number"]).update(
            created_at=timezone.now() - timedelta(hours=25)
        )

        assert self._order(world, 1).status_code == 201

    def test_zero_disables_the_cap(self, world, settings):
        settings.GUEST_CHECKOUT_MAX_OPEN_ORDERS = 0
        for n in range(5):
            assert self._order(world, n).status_code == 201

    def test_a_refused_attempt_holds_no_stock(self, world, settings):
        settings.GUEST_CHECKOUT_MAX_OPEN_ORDERS = 1
        self._order(world, 0)
        held = available(world)

        assert self._order(world, 1).status_code == 429
        assert available(world) == held


@pytest.mark.django_db
class TestGlobalBreaker:
    def test_more_than_the_hourly_ceiling_is_refused(self, world, settings):
        settings.GUEST_CHECKOUT_GLOBAL_PER_HOUR = 2
        settings.GUEST_CHECKOUT_MAX_OPEN_ORDERS = 0

        for n in range(2):
            _, ok = place(
                world,
                session=f"8e1c2b0e-8a52-4a0e-9f43-5b2e0c6a{n:04d}",
                phone=f"0100000000{n}",
                email=f"g{n}@x.com",
            )
            assert ok.status_code == 201

        _, busy = place(world, session="8e1c2b0e-8a52-4a0e-9f43-5b2e0c6a0009", email="g9@x.com")
        assert busy.status_code == 429


@pytest.mark.django_db
class TestThrottling:
    def test_the_scopes_exist_in_settings(self, settings):
        rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
        for scope in ("guest_checkout", "guest_lookup", "guest_token"):
            assert scope in rates, scope

    def test_num_proxies_is_read_from_the_environment_and_has_no_guessed_default(self, settings):
        # Unset in the test environment: None, i.e. "trust the whole header" — the
        # report documents that production MUST set it.
        assert "NUM_PROXIES" in settings.REST_FRAMEWORK

    def test_views_use_their_own_scopes(self):
        from orders import guest_api
        from orders.throttles import GuestCheckoutThrottle, GuestLookupThrottle, GuestTokenThrottle

        assert guest_api.GuestCheckoutAPI.throttle_classes == [GuestCheckoutThrottle]
        assert guest_api.GuestOrderLookupAPI.throttle_classes == [GuestLookupThrottle]
        assert guest_api.GuestOrderDetailAPI.throttle_classes == [GuestTokenThrottle]
        assert guest_api.GuestOrderCancelAPI.throttle_classes == [GuestTokenThrottle]

    def test_the_checkout_throttle_bites(self, world, monkeypatch, settings):
        from orders.throttles import GuestCheckoutThrottle

        settings.GUEST_CHECKOUT_MAX_OPEN_ORDERS = 0
        monkeypatch.setitem(GuestCheckoutThrottle.THROTTLE_RATES, "guest_checkout", "2/hour")

        statuses = []
        for n in range(3):
            client = guest_client(f"9f1c2b0e-8a52-4a0e-9f43-5b2e0c6a{n:04d}")
            add_to_cart(client, world)
            statuses.append(checkout(client, email=f"t{n}@x.com").status_code)

        assert statuses == [201, 201, 429]

    def test_a_stale_bearer_token_does_not_break_a_guest(self, world):
        """
        ⚠️  `authentication_classes = []`: a member whose session lapsed and who
            keeps shopping as a guest must not get a 401 from an endpoint that
            never needed a session.
        """
        client = guest_client()
        add_to_cart(client, world)
        client.credentials(
            HTTP_X_CART_SESSION=SESSION, HTTP_AUTHORIZATION="Bearer expired.or.garbage"
        )

        assert checkout(client).status_code == 201


# ═══════════════════════════════════════════════════════════
#  Idempotency
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestIdempotency:
    def test_a_retry_with_the_same_key_returns_the_same_order(self, world):
        client = guest_client()
        add_to_cart(client, world)

        first = client.post(
            reverse("v1:orders:guest-checkout"),
            FORM,
            format="json",
            HTTP_IDEMPOTENCY_KEY="try-0001",
        )
        retry = client.post(
            reverse("v1:orders:guest-checkout"),
            FORM,
            format="json",
            HTTP_IDEMPOTENCY_KEY="try-0001",
        )

        assert first.status_code == 201
        assert retry.status_code == 200
        assert retry.data["replayed"] is True
        assert retry.data["order_number"] == first.data["order_number"]
        assert Order.objects.count() == 1
        assert PaymentTransaction.objects.count() == 1

    def test_the_key_can_travel_in_the_body_too(self, world):
        client = guest_client()
        add_to_cart(client, world)

        first = checkout(client, idempotency_key="body-key-1")
        retry = checkout(client, idempotency_key="body-key-1")

        assert retry.data["order_number"] == first.data["order_number"]
        assert Order.objects.count() == 1

    def test_a_different_key_is_a_different_attempt(self, world):
        client = guest_client()
        add_to_cart(client, world)
        checkout(client, idempotency_key="key-a")

        add_to_cart(client, world)
        second = checkout(client, idempotency_key="key-b")

        assert second.status_code == 201
        assert Order.objects.count() == 2

    def test_the_key_is_scoped_to_the_cart_session(self, world):
        """
        ⚠️  Someone replaying a guessed key from their own session must not be
            handed another buyer's order out of the "already done" branch.
        """
        mine = guest_client()
        add_to_cart(mine, world)
        first = checkout(mine, idempotency_key="shared-key")

        theirs = guest_client("aa1c2b0e-8a52-4a0e-9f43-5b2e0c6a0001")
        add_to_cart(theirs, world)
        other = checkout(
            theirs, idempotency_key="shared-key", email="other@x.com", phone="01155556666"
        )

        assert other.status_code == 201
        assert other.data["order_number"] != first.data["order_number"]
        assert other.data["replayed"] is False

    def test_the_raw_key_is_not_stored(self, world):
        client = guest_client()
        add_to_cart(client, world)
        checkout(client, idempotency_key="super-secret-key")

        stored = Order.objects.get().checkout_key
        assert stored and "super-secret-key" not in stored and len(stored) == 64


# ═══════════════════════════════════════════════════════════
#  An account is never attached at checkout
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestNoAccountEnumeration:
    def test_the_response_is_identical_whether_or_not_an_account_exists(self, world):
        existing = User.objects.create_user(
            email="ahmed.buyer@example.com", password=PASSWORD, account_type=AccountType.STUDENT
        )
        existing.is_active = True
        existing.email_verified_at = timezone.now()
        existing.save()
        CustomerProfile.objects.create(user=existing)

        _, with_account = place(world, session="bb1c2b0e-8a52-4a0e-9f43-5b2e0c6a0001")
        _, without = place(
            world,
            session="bb1c2b0e-8a52-4a0e-9f43-5b2e0c6a0002",
            email="nobody.here@example.com",
            phone="01155556666",
        )

        assert with_account.status_code == without.status_code == 201
        assert set(with_account.data) == set(without.data)

    def test_the_order_is_not_linked_to_the_account_even_when_verified(self, world):
        existing = User.objects.create_user(
            email="ahmed.buyer@example.com", password=PASSWORD, account_type=AccountType.STUDENT
        )
        existing.is_active = True
        existing.email_verified_at = timezone.now()
        existing.save()
        profile = CustomerProfile.objects.create(user=existing)

        _, response = place(world)

        order = Order.objects.get(number=response.data["order_number"])
        assert order.customer is None
        assert not profile.orders.exists()


# ═══════════════════════════════════════════════════════════
#  The tracking link
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def placed(world):
    _, response = place(world, quantity=2)
    return response.data["tracking_token"], Order.objects.get(number=response.data["order_number"])


def detail(token):
    return APIClient().get(reverse("v1:orders:guest-detail", args=[token]))


def cancel(token, reason="غيّرت رأيي"):
    return APIClient().post(
        reverse("v1:orders:guest-cancel", args=[token]), {"reason": reason}, format="json"
    )


@pytest.mark.django_db
class TestTrackingLink:
    def test_a_valid_token_shows_the_order(self, placed):
        token, order = placed
        response = detail(token)

        assert response.status_code == 200
        data = response.data
        assert data["number"] == order.number
        assert data["status"] == "PENDING"
        assert data["payment_method"] == "COD"
        assert data["can_cancel"] is True
        assert data["grand_total"] == "258.00"
        assert data["currency"] == "EGP"
        assert data["item_count"] == 2
        assert data["lines"][0]["quantity"] == 2
        assert data["lines"][0]["product_name_ar"].startswith("منتج")
        assert [row["to_status"] for row in data["timeline"]] == ["PENDING"]
        assert data["governorate"] == "القاهرة" and data["city"] == "مدينة نصر"

    def test_it_shows_no_personal_details_beyond_a_masked_phone(self, placed):
        token, order = placed
        text = str(detail(token).data)

        assert "ahmed.buyer@example.com" not in text  # the full email
        assert "01001234567" not in text and "+201001234567" not in text  # the full phone
        assert "التسعين" not in text  # the street
        assert "اتصل قبل الوصول" not in text  # the customer note
        assert detail(token).data["phone_masked"] == "010******67"
        assert (
            detail(token).data["email_masked"] == "a***r@example.com"
            or "***" in (detail(token).data["email_masked"])
        )
        for forbidden in ("recipient_phone", "contact_email", "street", "customer_note", "id"):
            assert forbidden not in detail(token).data

    def test_the_timeline_carries_no_staff_identity(self, placed):
        token, order = placed
        staff = User.objects.create_user(email="staff@test.local", password=PASSWORD)
        services.transition(order, OrderStatus.CONFIRMED, note="اتصلنا بالعميل", actor=staff)

        data = detail(token).data
        assert [row["to_status"] for row in data["timeline"]] == ["PENDING", "CONFIRMED"]
        assert "staff@test.local" not in str(data) and "اتصلنا" not in str(data)
        assert data["can_cancel"] is False

    def test_the_response_is_not_cacheable(self, placed):
        token, _ = placed
        response = detail(token)
        assert response["Cache-Control"] == "no-store"
        assert response["Referrer-Policy"] == "no-referrer"

    def test_no_authentication_is_needed_and_a_bad_bearer_is_ignored(self, placed):
        token, _ = placed
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer garbage")
        assert client.get(reverse("v1:orders:guest-detail", args=[token])).status_code == 200

    @pytest.mark.parametrize(
        "make_bad",
        [
            lambda t: t[:-3] + ("AAA" if not t.endswith("AAA") else "BBB"),  # tampered signature
            lambda t: "x" + t,  # tampered payload
            lambda t: t.split(":")[0],  # signature stripped
            lambda t: "",
            lambda t: "totally-not-a-token",
            lambda t: "a:b:c",
        ],
    )
    def test_tampered_or_garbage_tokens_are_a_uniform_404(self, placed, make_bad):
        token, _ = placed
        bad = make_bad(token)
        if not bad:
            return  # an empty path segment does not route at all
        response = detail(bad)
        assert response.status_code == 404
        assert response.data["code"] == "NOT_FOUND"
        assert cancel(bad).status_code == 404

    def test_a_token_signed_with_another_salt_is_refused(self, placed):
        """A signed value minted for some other purpose can never open an order."""
        _, order = placed
        foreign = signing.dumps(
            {"o": str(order.pk), "e": guest._email_digest(order.contact_email)},
            salt="something.else",
        )
        assert detail(foreign).status_code == 404

    def test_a_token_for_a_nonexistent_order_is_a_404(self, placed):
        _, order = placed
        import uuid

        ghost = signing.dumps(
            {"o": str(uuid.uuid4()), "e": guest._email_digest("a@b.com")}, salt=guest.TOKEN_SALT
        )
        assert detail(ghost).status_code == 404

    def test_a_token_cannot_be_pointed_at_a_member_order(self, world):
        """Even a validly signed token needs the order to be a guest one with a matching email."""
        member = User.objects.create_user(email="m@test.local", password=PASSWORD)
        profile = CustomerProfile.objects.create(user=member)
        order = Order.objects.create(customer=profile, channel=OrderChannel.ONLINE)
        forged = signing.dumps(
            {"o": str(order.pk), "e": guest._email_digest("")}, salt=guest.TOKEN_SALT
        )

        assert detail(forged).status_code == 404

    def test_a_token_is_bound_to_its_own_order(self, world):
        _, first = place(world, session="cc1c2b0e-8a52-4a0e-9f43-5b2e0c6a0001")
        _, second = place(
            world,
            session="cc1c2b0e-8a52-4a0e-9f43-5b2e0c6a0002",
            email="second@example.com",
            phone="01155556666",
        )
        assert detail(first.data["tracking_token"]).data["number"] == first.data["order_number"]
        assert detail(second.data["tracking_token"]).data["number"] == second.data["order_number"]

    def test_the_token_stops_working_if_the_email_on_the_order_changes(self, placed):
        token, order = placed
        Order.objects.filter(pk=order.pk).update(contact_email="changed@example.com")
        assert detail(token).status_code == 404

    def test_an_expired_link_says_so_with_410(self, placed, monkeypatch):
        token, _ = placed
        import time

        real = time.time

        class Later:
            @staticmethod
            def time():
                return real() + 91 * 86400

        monkeypatch.setattr(signing, "time", Later())

        response = detail(token)
        assert response.status_code == 410
        assert response.data["code"] == "TOKEN_EXPIRED"

    def test_the_lifetime_is_configurable(self, placed, settings, monkeypatch):
        token, _ = placed
        settings.GUEST_ORDER_TOKEN_MAX_AGE_DAYS = 200
        import time

        real = time.time

        class Later:
            @staticmethod
            def time():
                return real() + 150 * 86400

        monkeypatch.setattr(signing, "time", Later())
        assert detail(token).status_code == 200


# ═══════════════════════════════════════════════════════════
#  Cancelling through the link
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCancelByLink:
    def test_a_pending_order_can_be_cancelled_and_its_stock_comes_back(self, world, placed):
        token, order = placed
        held = available(world)

        response = cancel(token, "غيّرت رأيي")

        assert response.status_code == 200
        assert response.data["status"] == "CANCELLED"
        assert response.data["can_cancel"] is False
        order.refresh_from_db()
        assert order.status == OrderStatus.CANCELLED
        assert "غيّرت رأيي" in order.cancellation_reason
        assert available(world) == held + 2
        assert not inventory_services.active_reservations_for("order", order.pk)

    def test_a_reason_is_optional(self, placed):
        token, _ = placed
        response = APIClient().post(
            reverse("v1:orders:guest-cancel", args=[token]), {}, format="json"
        )
        assert response.status_code == 200

    def test_a_confirmed_order_cannot_be_cancelled_this_way(self, placed):
        token, order = placed
        services.transition(order, OrderStatus.CONFIRMED)

        response = cancel(token)

        assert response.status_code == 409
        assert response.data["code"] == "ORDER_CANNOT_BE_CANCELLED"
        order.refresh_from_db()
        assert order.status == OrderStatus.CONFIRMED

    def test_cancelling_twice_is_refused(self, placed):
        token, _ = placed
        assert cancel(token).status_code == 200
        assert cancel(token).status_code == 409

    def test_a_cancel_cannot_reach_someone_elses_order(self, world, placed):
        _, mine = placed
        _, other = place(
            world,
            session="dd1c2b0e-8a52-4a0e-9f43-5b2e0c6a0001",
            email="other@example.com",
            phone="01155556666",
        )
        cancel(other.data["tracking_token"])

        mine.refresh_from_db()
        assert mine.status == OrderStatus.PENDING


# ═══════════════════════════════════════════════════════════
#  "Find my order"
# ═══════════════════════════════════════════════════════════


def lookup(number, phone):
    return APIClient().post(
        reverse("v1:orders:guest-lookup"), {"order_number": number, "phone": phone}, format="json"
    )


def mails_for(address):
    from mailing.models import OutboundMessage

    return OutboundMessage.objects.filter(to_email=address, template_key="guest_order_confirmation")


@pytest.mark.django_db
class TestLookup:
    def test_a_match_emails_the_link_to_the_address_on_the_order(self, placed):
        token, order = placed
        baseline = mails_for(order.contact_email).count()

        response = lookup(order.number, "01001234567")

        assert response.status_code == 200
        assert mails_for(order.contact_email).count() == baseline + 1
        body = mails_for(order.contact_email).latest("created_at").body
        assert order.number in body and "/order/guest/" in body

    def test_the_answer_is_identical_for_match_and_miss(self, placed):
        _, order = placed
        matched = lookup(order.number, "01001234567")
        wrong_phone = lookup(order.number, "01299999999")
        no_such_order = lookup("ORD-2020-ZZZZZZ", "01001234567")
        garbage = lookup("???", "not a phone")

        assert matched.status_code == wrong_phone.status_code == no_such_order.status_code == 200
        assert garbage.status_code == 200
        assert matched.data == wrong_phone.data == no_such_order.data == garbage.data

    def test_no_mail_goes_out_on_a_miss(self, placed):
        _, order = placed
        baseline = mails_for(order.contact_email).count()

        lookup(order.number, "01299999999")
        lookup("ORD-2020-ZZZZZZ", "01001234567")

        assert mails_for(order.contact_email).count() == baseline

    def test_the_mail_never_goes_to_an_address_the_requester_supplied(self, placed):
        _, order = placed
        APIClient().post(
            reverse("v1:orders:guest-lookup"),
            {"order_number": order.number, "phone": "01001234567", "email": "attacker@evil.com"},
            format="json",
        )
        assert not mails_for("attacker@evil.com").exists()

    @pytest.mark.parametrize(
        "phone", ["01001234567", "+201001234567", "٠١٠٠١٢٣٤٥٦٧", "010 0123 4567", "201001234567"]
    )
    def test_the_phone_is_compared_in_normalised_form(self, placed, phone):
        _, order = placed
        baseline = mails_for(order.contact_email).count()
        lookup(order.number.lower(), phone)  # and the number is case-insensitive
        assert mails_for(order.contact_email).count() == baseline + 1

    def test_one_order_cannot_be_used_to_flood_an_inbox(self, placed):
        _, order = placed
        baseline = mails_for(order.contact_email).count()
        for _ in range(8):
            lookup(order.number, "01001234567")
        assert mails_for(order.contact_email).count() == baseline + 3

    def test_member_orders_are_never_emailed_a_guest_link(self, world):
        member = User.objects.create_user(email="m@test.local", password=PASSWORD)
        profile = CustomerProfile.objects.create(user=member)
        order = Order.objects.create(
            customer=profile, channel=OrderChannel.ONLINE, recipient_phone="+201001234567"
        )
        lookup(order.number, "01001234567")
        # (the member's own "we received your order" mail is a different template)
        assert not mails_for("m@test.local").exists()

    def test_missing_fields_are_a_normal_400(self):
        response = APIClient().post(reverse("v1:orders:guest-lookup"), {}, format="json")
        assert response.status_code == 400

    def test_the_lookup_throttle_bites(self, placed, monkeypatch):
        from orders.throttles import GuestLookupThrottle

        _, order = placed
        monkeypatch.setitem(GuestLookupThrottle.THROTTLE_RATES, "guest_lookup", "2/hour")
        codes = [lookup(order.number, "01001234567").status_code for _ in range(3)]
        assert codes == [200, 200, 429]
