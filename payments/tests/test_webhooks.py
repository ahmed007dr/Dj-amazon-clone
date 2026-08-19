"""
The gateway event endpoint.

⚠️  **This endpoint is the only thing that makes electronic payment real.**

    `charge` issues a link or a number; it does not know whether the customer
    paid. The webhook alone says "the money was taken". A missing or broken
    endpoint means orders left "processing" while the amounts are in the bank account.

⚠️  And it is **unauthenticated** — so every property here is a security guard,
    not a behavioural detail.
"""

import hashlib
import hmac
from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from payments import events
from payments.gateways.paymob import HMAC_FIELDS, _lookup
from payments.models import (
    PaymentMethodKind,
    PaymentProvider,
    PaymentTransaction,
    ProviderCredential,
    TransactionStatus,
    WebhookEvent,
)

pytestmark = pytest.mark.django_db

SECRET = "hmac-secret-for-tests"


# ═══════════════════════════════════════════════════════════
#  Setup
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def provider():
    gateway = PaymentProvider.objects.create(
        code="paymob",
        name_ar="بيموب",
        name_en="Paymob",
        adapter_key="paymob",
        supported_methods=[PaymentMethodKind.CARD],
        is_sandbox=True,
        is_active=True,
    )
    ProviderCredential.objects.create(
        provider=gateway, key="hmac_secret", value=SECRET, is_sandbox=True
    )
    return gateway


@pytest.fixture
def payment(provider):
    return PaymentTransaction.objects.create(
        provider=provider,
        method=PaymentMethodKind.CARD,
        amount=Decimal("150.00"),
        currency="EGP",
        reference_type="order",
        reference_id="ORD-1",
    )


@pytest.fixture
def client():
    return APIClient()


def webhook_url(code="paymob"):
    return reverse("v1:payments:webhook", kwargs={"provider_code": code})


def paymob_payload(payment, *, event_id="55501", **overrides):
    """A Paymob payload exactly as it arrives — nested and with boolean values."""
    obj = {
        "id": event_id,
        "amount_cents": 15000,
        "created_at": "2026-08-15T10:00:00",
        "currency": "EGP",
        "error_occured": False,
        "has_parent_transaction": False,
        "integration_id": 999,
        "is_3d_secure": True,
        "is_auth": False,
        "is_capture": True,
        "is_refunded": False,
        "is_standalone_payment": True,
        "is_voided": False,
        "order": {"id": 7777, "merchant_order_id": payment.reference},
        "owner": 42,
        "pending": False,
        "source_data": {"pan": "2346", "sub_type": "MasterCard", "type": "card"},
        "success": True,
    }
    obj.update(overrides)
    return {"type": "TRANSACTION", "obj": obj}


def sign(payload):
    message = "".join(_lookup(payload["obj"], field) for field in HMAC_FIELDS)
    return hmac.new(SECRET.encode(), message.encode(), hashlib.sha512).hexdigest()


def deliver(client, payload, *, signature=None, code="paymob"):
    """Delivering an event the way the gateway does: the signature in the URL parameter."""
    signature = sign(payload) if signature is None else signature
    return client.post(
        f"{webhook_url(code)}?hmac={signature}",
        payload,
        format="json",
    )


# ═══════════════════════════════════════════════════════════
#  The correct path
# ═══════════════════════════════════════════════════════════


class TestSuccessfulDelivery:
    def test_a_signed_event_marks_the_payment_captured(self, client, payment):
        response = deliver(client, paymob_payload(payment))

        assert response.status_code == 200
        assert response.data["status"] == "applied"

        payment.refresh_from_db()
        assert payment.status == TransactionStatus.CAPTURED
        assert payment.captured_at is not None
        # ⚠️  A capture implies an authorisation — a report measuring the interval
        #     between them breaks on a captured transaction with no authorisation time.
        assert payment.authorized_at is not None

    def test_the_event_is_recorded_for_audit(self, client, payment, provider):
        deliver(client, paymob_payload(payment, event_id="99001"))

        event = WebhookEvent.objects.get(provider=provider, event_id="99001")
        assert event.signature_valid
        assert event.is_processed
        assert event.processing_error == ""

    def test_higher_layers_are_told_without_being_imported(self, client, payment):
        """
        ⚠️  `payments` sits **below** `orders` in the layer diagram, so it must
            not mark the order paid itself. The signal is the only route.
        """
        received = []

        def listener(sender, payment, **kwargs):
            received.append(payment)

        events.payment_captured.connect(listener, weak=False)
        try:
            deliver(client, paymob_payload(payment))
        finally:
            events.payment_captured.disconnect(listener)

        assert [p.pk for p in received] == [payment.pk]

    def test_no_authentication_is_required(self, client, payment):
        """
        ⚠️  The gateway has no account and no token. A malformed authentication
            header must not drop a valid event.
        """
        client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        assert deliver(client, paymob_payload(payment)).status_code == 200


# ═══════════════════════════════════════════════════════════
#  Forgery
# ═══════════════════════════════════════════════════════════


class TestForgery:
    def test_a_bad_signature_changes_nothing(self, client, payment):
        """
        ⚠️  **The first and most obvious attack**: one call marks an order paid.
        """
        response = deliver(client, paymob_payload(payment), signature="0" * 128)

        assert response.status_code == 403
        payment.refresh_from_db()
        assert payment.status == TransactionStatus.PENDING

    def test_a_tampered_amount_is_rejected(self, client, payment):
        """The signature is computed over the original amount — altering it invalidates it."""
        payload = paymob_payload(payment)
        signature = sign(payload)
        payload["obj"]["amount_cents"] = 100

        response = client.post(f"{webhook_url()}?hmac={signature}", payload, format="json")

        assert response.status_code == 403
        payment.refresh_from_db()
        assert payment.status == TransactionStatus.PENDING

    def test_a_forged_event_cannot_block_the_genuine_one(self, client, payment, provider):
        """
        ⚠️  **A silent denial hole** — the most dangerous thing in this file.

            The deduplication table is keyed on `(gateway, event id)`. Were the
            forged event recorded before verification, it would occupy the slot:
            the real one then arrives with the same id, looks like a repeat and
            is discarded — leaving a paid order unmarked, from one call with no
            key at all.

            The forged event therefore never enters the table.
        """
        payload = paymob_payload(payment, event_id="ATTACKER-GUESS")

        assert deliver(client, payload, signature="deadbeef").status_code == 403
        assert not WebhookEvent.objects.filter(event_id="ATTACKER-GUESS").exists()

        # The real event with the same id passes as though nothing had happened
        assert deliver(client, payload).status_code == 200
        payment.refresh_from_db()
        assert payment.status == TransactionStatus.CAPTURED

    def test_an_amount_that_does_not_match_is_never_marked_paid(self, client, payment):
        """
        ⚠️  A valid signature proves **the sender**, not **the correct amount**.

            A gateway that collected something other than what we asked for
            arrives with a perfectly sound signature; and marking it paid
            creates a completed order with money missing, visible only in a
            monthly reconciliation.
        """
        response = deliver(client, paymob_payload(payment, amount_cents=9900))

        assert response.status_code == 200
        assert response.data["status"] == "amount_mismatch"

        payment.refresh_from_db()
        assert payment.status == TransactionStatus.PENDING


# ═══════════════════════════════════════════════════════════
#  Duplication
# ═══════════════════════════════════════════════════════════


class TestIdempotency:
    def test_the_same_event_is_applied_once(self, client, payment):
        """
        ⚠️  The gateway resends when no response arrives. Without deduplication
            the order is marked paid twice — and with a refund the amount is doubled.
        """
        payload = paymob_payload(payment)

        assert deliver(client, payload).data["status"] == "applied"

        payment.refresh_from_db()
        captured_at = payment.captured_at

        assert deliver(client, payload).data["status"] == "duplicate"

        payment.refresh_from_db()
        assert payment.captured_at == captured_at
        assert WebhookEvent.objects.count() == 1

    def test_an_unprocessed_event_is_retried_not_swallowed(self, client, payment, provider):
        """
        ⚠️  Duplication is measured by processing, not by recording.

            An event that was recorded and then failed to apply must be applied
            when the gateway resends it. Measuring by recording made the first
            failure final.
        """
        payload = paymob_payload(payment, event_id="42042")

        WebhookEvent.objects.create(
            provider=provider,
            event_id="42042",
            event_type="TRANSACTION",
            payload=payload,
            signature_valid=True,
            is_processed=False,
        )

        assert deliver(client, payload).data["status"] == "applied"
        payment.refresh_from_db()
        assert payment.status == TransactionStatus.CAPTURED


# ═══════════════════════════════════════════════════════════
#  States
# ═══════════════════════════════════════════════════════════


class TestOutcomes:
    def test_a_failed_transaction_is_recorded_as_failed(self, client, payment):
        response = deliver(client, paymob_payload(payment, success=False))

        assert response.data["status"] == "applied"
        payment.refresh_from_db()
        assert payment.status == TransactionStatus.FAILED

    def test_authorisation_without_capture_is_not_payment(self, client, payment):
        """
        ⚠️  The funds are held and the money has not moved. Marking it captured
            produces phantom revenue in every financial report.
        """
        deliver(client, paymob_payload(payment, is_auth=True, is_capture=False))

        payment.refresh_from_db()
        assert payment.status == TransactionStatus.AUTHORIZED
        assert payment.captured_at is None

    def test_a_refunded_transaction_is_never_pulled_back(self, client, payment):
        """
        ⚠️  A late resend of an old success event after the money was returned
            used to show the amount as revenue a second time.
        """
        payment.status = TransactionStatus.REFUNDED
        payment.save(update_fields=["status"])

        response = deliver(client, paymob_payload(payment, event_id="late-1"))

        assert response.data["status"] == "ignored"
        payment.refresh_from_db()
        assert payment.status == TransactionStatus.REFUNDED

    def test_a_refund_event_marks_the_transaction_refunded(self, client, payment):
        payment.status = TransactionStatus.CAPTURED
        payment.save(update_fields=["status"])

        deliver(client, paymob_payload(payment, is_refunded=True))

        payment.refresh_from_db()
        assert payment.status == TransactionStatus.REFUNDED


# ═══════════════════════════════════════════════════════════
#  Boundaries
# ═══════════════════════════════════════════════════════════


class TestBoundaries:
    def test_a_disabled_provider_receives_nothing(self, client, payment, provider):
        """
        ⚠️  Disabling a gateway must be a complete shutdown.

            Leaving its endpoint open means it still marks orders as paid while
            it has disappeared from the customer's options.
        """
        provider.is_active = False
        provider.save(update_fields=["is_active"])

        assert deliver(client, paymob_payload(payment)).status_code == 404

    def test_an_unknown_provider_code_is_not_found(self, client, payment):
        assert deliver(client, paymob_payload(payment), code="stripe").status_code == 404

    def test_an_unreadable_payload_is_refused(self, client, provider):
        """A payload the adapter does not understand is neither recorded nor applied."""
        response = client.post(f"{webhook_url()}?hmac=x", {"hello": "world"}, format="json")

        assert response.status_code == 400
        assert response.data["status"] == "unreadable"
        assert WebhookEvent.objects.count() == 0

    def test_an_event_without_a_matching_transaction_is_not_retried(self, client, provider):
        """
        ⚠️  200, not an error: the gateway resends on any unsuccessful response,
            and an event with a reference we do not know would arrive every few
            minutes forever. It is logged clearly and not asked to repeat for nothing.
        """
        orphan = PaymentTransaction(
            provider=provider,
            method=PaymentMethodKind.CARD,
            amount=Decimal("150.00"),
            currency="EGP",
        )
        orphan.reference = "PAY-NOT-IN-DB"

        response = deliver(client, paymob_payload(orphan))

        assert response.status_code == 200
        assert response.data["status"] == "unknown_transaction"


# ═══════════════════════════════════════════════════════════
#  Fawry
# ═══════════════════════════════════════════════════════════


class TestFawryEnvelope:
    """
    ⚠️  Fawry sends no event id — it sends the reference number and its status,
        and the number is constant over the order's lifetime. Taking it as the
        id makes "paid" after "the number was issued" look like a repeat and be
        discarded, leaving the order unpaid while the money was taken at the outlet.
    """

    def _adapter(self):
        from payments.gateways.fawry import FawryAdapter

        return FawryAdapter({"secure_key": "SK"}, sandbox=True)

    def _payload(self, status):
        return {
            "fawryRefNumber": "9988776655",
            "merchantRefNumber": "PAY-1",
            "orderStatus": status,
            "paymentAmount": "150.00",
            "messageSignature": "sig",
        }

    def test_each_status_change_is_a_distinct_event(self):
        adapter = self._adapter()

        issued = adapter.parse_webhook(payload=self._payload("NEW"), params={})
        paid = adapter.parse_webhook(payload=self._payload("PAID"), params={})

        assert issued.event_id != paid.event_id
        assert issued.outcome == "PENDING"
        assert paid.outcome == "CAPTURED"

    def test_the_reference_number_alone_is_not_payment(self):
        """`NEW` means "the number was issued" — and the customer has time to pay."""
        envelope = self._adapter().parse_webhook(payload=self._payload("NEW"), params={})
        assert envelope.outcome == "PENDING"

    def test_the_signature_comes_from_the_body_not_the_url(self):
        """Unlike Paymob — reading it from the URL refuses every valid notification."""
        envelope = self._adapter().parse_webhook(payload=self._payload("PAID"), params={})
        assert envelope.signature == "sig"
        assert envelope.amount == Decimal("150.00")

    def test_a_payload_without_a_status_is_unreadable(self):
        assert self._adapter().parse_webhook(payload={"fawryRefNumber": "1"}, params={}) is None
