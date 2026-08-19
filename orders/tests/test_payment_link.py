"""
Linking a payment confirmation to the order.

⚠️  **The missing link**: `charge()` issues a gateway link and does not know
    whether the customer paid. The confirmation arrives by webhook and marks the
    transaction captured — and without the listener it stops there: the money is
    in the account and the order is "unpaid".

⚠️  And the test emits the signal directly rather than over HTTP.

    The full webhook path is covered in `payments/tests/test_webhooks.py`. What
    is covered here is the other side: what `orders` does when it arrives.
"""

from decimal import Decimal

import pytest

from accounts.models import AccountType, User
from catalog.models import Category, Product
from customers.models import CustomerProfile
from orders.events import order_paid
from orders.models import Order, OrderChannel, OrderStatus, PaymentStatus
from payments.events import payment_captured, payment_failed, payment_refunded
from payments.models import PaymentMethodKind, PaymentProvider, PaymentTransaction

pytestmark = pytest.mark.django_db

PASSWORD = "Str0ng-Test-Pass!23"


@pytest.fixture
def customer(db):
    user = User.objects.create_user(
        email="buyer@test.local", password=PASSWORD, account_type=AccountType.DOCTOR
    )
    user.is_active = True
    user.save()
    return CustomerProfile.objects.create(user=user)


@pytest.fixture
def order(customer):
    category = Category.objects.create(name_ar="فئة", name_en="Category")
    Product.objects.create(sku="P-1", name_ar="منتج", name_en="Product", category=category)

    return Order.objects.create(
        customer=customer,
        channel=OrderChannel.ONLINE,
        subtotal=Decimal("100.00"),
        grand_total=Decimal("100.00"),
        currency="EGP",
    )


@pytest.fixture
def provider(db):
    return PaymentProvider.objects.create(
        code="paymob", name_ar="بيموب", name_en="Paymob", adapter_key="paymob"
    )


def transaction_for(provider, order, **overrides):
    body = {
        "provider": provider,
        "method": PaymentMethodKind.CARD,
        "amount": Decimal("100.00"),
        "currency": "EGP",
        "reference_type": "order",
        "reference_id": str(order.pk),
    }
    body.update(overrides)
    return PaymentTransaction.objects.create(**body)


# ═══════════════════════════════════════════════════════════
#  Capture
# ═══════════════════════════════════════════════════════════


class TestCaptured:
    def test_a_captured_payment_marks_the_order_paid(self, provider, order):
        payment = transaction_for(provider, order)

        payment_captured.send(sender=PaymentTransaction, payment=payment)

        order.refresh_from_db()
        assert order.payment_status == PaymentStatus.PAID

    def test_paying_confirms_a_pending_order(self, provider, order):
        """Payment confirms the order automatically — it does not wait for an admin click."""
        assert order.status == OrderStatus.PENDING
        payment = transaction_for(provider, order)

        payment_captured.send(sender=PaymentTransaction, payment=payment)

        order.refresh_from_db()
        assert order.status == OrderStatus.CONFIRMED

    def test_higher_layers_hear_that_the_order_was_paid(self, provider, order):
        """
        ⚠️  `order_paid` was defined with no emitter — a definition with no send
            makes every listener for it dead code.
        """
        heard = []

        def listener(sender, order, **kwargs):
            heard.append(order.pk)

        payment = transaction_for(provider, order)

        order_paid.connect(listener, weak=False)
        try:
            payment_captured.send(sender=PaymentTransaction, payment=payment)
        finally:
            order_paid.disconnect(listener)

        assert heard == [order.pk]

    def test_a_second_confirmation_is_harmless(self, provider, order):
        """
        ⚠️  "Already paid" is not a failure but the desired state.

            The gateway resends, and two attempts may arrive with different ids
            for the same order. Raising produced a 500 that retried forever on
            an order that lacks nothing.
        """
        first = transaction_for(provider, order)
        second = transaction_for(provider, order)

        payment_captured.send(sender=PaymentTransaction, payment=first)
        payment_captured.send(sender=PaymentTransaction, payment=second)

        order.refresh_from_db()
        assert order.payment_status == PaymentStatus.PAID


# ═══════════════════════════════════════════════════════════
#  What does not belong to orders
# ═══════════════════════════════════════════════════════════


class TestScoping:
    def test_a_pos_sale_reference_is_ignored(self, provider, order):
        """
        ⚠️  Filtering by reference type is mandatory: a counter sale and a
            credit payment pass through the same table with references of other
            kinds, and matching the id alone marks an order unrelated to the payment.
        """
        payment = transaction_for(provider, order, reference_type="pos_session")

        payment_captured.send(sender=PaymentTransaction, payment=payment)

        order.refresh_from_db()
        assert order.payment_status == PaymentStatus.UNPAID

    def test_an_unknown_order_reference_does_not_crash(self, provider, order):
        payment = transaction_for(
            provider, order, reference_id="01a00000-0000-7000-8000-000000000000"
        )

        payment_captured.send(sender=PaymentTransaction, payment=payment)

        order.refresh_from_db()
        assert order.payment_status == PaymentStatus.UNPAID

    def test_a_payment_without_a_reference_is_ignored(self, provider, order):
        payment = transaction_for(provider, order, reference_id="")

        payment_captured.send(sender=PaymentTransaction, payment=payment)

        order.refresh_from_db()
        assert order.payment_status == PaymentStatus.UNPAID

    def test_a_reference_that_is_not_a_uuid_does_not_crash(self, provider, order):
        """
        ⚠️  **A regression**: `reference_id` is a free-text field and the order's key is a UUID.

            Passing an invalid string to `filter(pk=…)` raises
            `ValidationError` before it reaches the database — so the webhook
            collapses with a 500 and the gateway keeps resending an event that
            will never succeed. And an unfamiliar reference is not an error: it
            is a payment that does not belong to orders.
        """
        payment = transaction_for(provider, order, reference_id="ORD-1")

        payment_captured.send(sender=PaymentTransaction, payment=payment)

        order.refresh_from_db()
        assert order.payment_status == PaymentStatus.UNPAID


# ═══════════════════════════════════════════════════════════
#  Failure and refund
# ═══════════════════════════════════════════════════════════


class TestFailureAndRefund:
    def test_a_failed_payment_is_recorded(self, provider, order):
        payment = transaction_for(provider, order)

        payment_failed.send(sender=PaymentTransaction, payment=payment)

        order.refresh_from_db()
        assert order.payment_status == PaymentStatus.FAILED

    def test_a_late_failure_never_unpays_a_paid_order(self, provider, order):
        """
        ⚠️  A failed attempt may arrive **after** a successful one (a late
            resend). Applying it with no guard erases a genuine payment and
            makes the order look unsettled.
        """
        payment = transaction_for(provider, order)
        payment_captured.send(sender=PaymentTransaction, payment=payment)

        payment_failed.send(sender=PaymentTransaction, payment=transaction_for(provider, order))

        order.refresh_from_db()
        assert order.payment_status == PaymentStatus.PAID

    def test_a_refund_marks_payment_only_not_the_order_status(self, provider, order):
        """
        ⚠️  Refunding the money does not mean the order is cancelled: goods may
            have been delivered and then refunded. Moving the order's status is
            the admin's decision.
        """
        payment = transaction_for(provider, order)
        payment_captured.send(sender=PaymentTransaction, payment=payment)

        order.refresh_from_db()
        status_before = order.status

        payment_refunded.send(sender=PaymentTransaction, payment=payment)

        order.refresh_from_db()
        assert order.payment_status == PaymentStatus.REFUNDED
        assert order.status == status_before


# ═══════════════════════════════════════════════════════════
#  The full path
# ═══════════════════════════════════════════════════════════


class TestEndToEnd:
    def test_a_gateway_webhook_marks_the_order_paid(self, provider, order):
        """
        ⚠️  **The test that proves the loop is closed.**

            From an HTTP call the gateway makes through to
            `payment_status = PAID` on the order — with no manual call in the
            middle. Every link individually used to pass while the chain was broken.
        """
        import hashlib
        import hmac

        from django.urls import reverse
        from rest_framework.test import APIClient

        from payments.gateways.paymob import HMAC_FIELDS, _lookup
        from payments.models import ProviderCredential

        secret = "webhook-secret"
        provider.is_active = True
        provider.is_sandbox = True
        provider.save(update_fields=["is_active", "is_sandbox"])
        ProviderCredential.objects.create(
            provider=provider, key="hmac_secret", value=secret, is_sandbox=True
        )

        payment = transaction_for(provider, order)

        payload = {
            "type": "TRANSACTION",
            "obj": {
                "id": "77001",
                "amount_cents": 10000,
                "created_at": "2026-08-16T09:00:00",
                "currency": "EGP",
                "error_occured": False,
                "has_parent_transaction": False,
                "integration_id": 1,
                "is_3d_secure": True,
                "is_auth": False,
                "is_capture": True,
                "is_refunded": False,
                "is_standalone_payment": True,
                "is_voided": False,
                "order": {"id": 900, "merchant_order_id": payment.reference},
                "owner": 1,
                "pending": False,
                "source_data": {"pan": "1111", "sub_type": "Visa", "type": "card"},
                "success": True,
            },
        }
        message = "".join(_lookup(payload["obj"], field) for field in HMAC_FIELDS)
        signature = hmac.new(secret.encode(), message.encode(), hashlib.sha512).hexdigest()

        url = reverse("v1:payments:webhook", kwargs={"provider_code": "paymob"})
        response = APIClient().post(f"{url}?hmac={signature}", payload, format="json")

        assert response.status_code == 200
        assert response.data["status"] == "applied"

        order.refresh_from_db()
        assert order.payment_status == PaymentStatus.PAID
        assert order.status == OrderStatus.CONFIRMED
