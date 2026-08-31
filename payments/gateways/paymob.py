"""
The Paymob adapter.

⚠️  Charging is **three steps**, not one:

        1. authenticate  ⟵ api_key             →  auth_token
        2. register order ⟵ auth_token          →  order_id
        3. payment key   ⟵ order_id + details  →  payment_token
                                                  →  the iframe URL

    All three are consecutive calls, and a failure in any of them fails the
    whole operation. Ignoring that produces a payment link with an expired key
    that fails at the customer's end rather than at ours.

⚠️  **Amounts are in piastres** (`amount_cents`).

    Sending 150.00 instead of 15000 collects one and a half pounds instead of a
    hundred and fifty. The conversion happens here once, and with `Decimal`.

⚠️  Webhook verification is **HMAC-SHA512 over fields in a specific order**.

    The order is part of the contract, not an implementation detail: changing it
    makes every valid signature look forged, and the reverse is more dangerous.

⚠️  Not tested against a real account — see `payments/gateways/__init__.py`.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from decimal import Decimal

from payments.adapters import (
    AUTHORIZED,
    CAPTURED,
    FAILED,
    PENDING,
    REFUNDED,
    ChargeResult,
    PaymentAdapter,
    RefundResult,
    WebhookEnvelope,
    register,
)

from .transport import post_json

logger = logging.getLogger(__name__)

LIVE_BASE = "https://accept.paymob.com/api"
IFRAME_URL = "https://accept.paymob.com/api/acceptance/iframes/{iframe_id}"

#: ⚠️  The field order for the webhook signature — **part of the contract**.
#:     Alphabetical as Paymob documents it; any reordering breaks every verification.
HMAC_FIELDS = (
    "amount_cents",
    "created_at",
    "currency",
    "error_occured",
    "has_parent_transaction",
    "id",
    "integration_id",
    "is_3d_secure",
    "is_auth",
    "is_capture",
    "is_refunded",
    "is_standalone_payment",
    "is_voided",
    "order.id",
    "owner",
    "pending",
    "source_data.pan",
    "source_data.sub_type",
    "source_data.type",
    "success",
)

#: Billing details Paymob requires — an empty value is refused, and `NA` is the
#: agreed substitute for a field we do not have.
BILLING_PLACEHOLDER = "NA"


@register
class PaymobAdapter(PaymentAdapter):
    key = "paymob"

    #: ⚠️  All four, and the panel refuses to enable the gateway without them.
    #:
    #:     Three of four is not "nearly configured": the payment fails at whichever
    #:     step needs the fourth, after the customer has entered their card.
    required_credentials = ("api_key", "integration_id", "iframe_id", "hmac_secret")

    # ── Credentials ────────────────────────────────────────

    def _credential(self, name: str) -> str:
        value = self.credentials.get(name, "")
        if not value:
            # ⚠️  The failure names the missing key explicitly.
            #
            #     "Payment failed" alone makes the admin hunt through the gateway
            #     while the problem is a field left blank in their own panel.
            raise KeyError(name)
        return value

    # ── The three steps ────────────────────────────────────

    def _authenticate(self) -> str | None:
        response = post_json(f"{LIVE_BASE}/auth/tokens", {"api_key": self._credential("api_key")})
        if not response.ok:
            return None
        return response.data.get("token")

    def _register_order(self, auth_token: str, amount_cents: int, reference: str) -> int | None:
        response = post_json(
            f"{LIVE_BASE}/ecommerce/orders",
            {
                "auth_token": auth_token,
                # ⚠️  The order is created once per reference; a repeat is refused
                #     by Paymob, and that is the desired behaviour rather than an error.
                "delivery_needed": False,
                "amount_cents": amount_cents,
                "currency": "EGP",
                "merchant_order_id": reference,
                "items": [],
            },
        )
        if not response.ok:
            return None
        return response.data.get("id")

    def _payment_key(
        self, auth_token: str, order_id: int, amount_cents: int, metadata: dict
    ) -> str | None:
        response = post_json(
            f"{LIVE_BASE}/acceptance/payment_keys",
            {
                "auth_token": auth_token,
                "amount_cents": amount_cents,
                "expiration": 3600,
                "order_id": order_id,
                "currency": "EGP",
                "integration_id": int(self._credential("integration_id")),
                "billing_data": self._billing(metadata),
            },
        )
        if not response.ok:
            return None
        return response.data.get("token")

    def _billing(self, metadata: dict) -> dict:
        """
        ⚠️  Every field is mandatory at Paymob.

            An empty field gets the whole request refused with an obscure
            message, hence `NA` for what we genuinely do not have rather than
            leaving it blank.
        """
        return {
            "first_name": metadata.get("first_name") or BILLING_PLACEHOLDER,
            "last_name": metadata.get("last_name") or BILLING_PLACEHOLDER,
            "email": metadata.get("email") or "na@example.com",
            "phone_number": metadata.get("phone") or BILLING_PLACEHOLDER,
            "street": metadata.get("street") or BILLING_PLACEHOLDER,
            "building": metadata.get("building") or BILLING_PLACEHOLDER,
            "floor": BILLING_PLACEHOLDER,
            "apartment": BILLING_PLACEHOLDER,
            "city": metadata.get("city") or BILLING_PLACEHOLDER,
            "state": metadata.get("governorate") or BILLING_PLACEHOLDER,
            "country": "EG",
            "postal_code": BILLING_PLACEHOLDER,
            "shipping_method": BILLING_PLACEHOLDER,
        }

    # ── The interface ──────────────────────────────────────

    def charge(self, *, amount: Decimal, currency: str, reference: str, metadata: dict):
        try:
            iframe_id = self._credential("iframe_id")
        except KeyError as exc:
            return ChargeResult(
                success=False,
                failure_code="MISSING_CREDENTIAL",
                failure_message=f"بيانات اعتماد ناقصة: {exc.args[0]}",
            )

        # ⚠️  Piastres are an integer — round before the conversion, not after.
        amount_cents = int((amount * 100).to_integral_value())

        try:
            auth_token = self._authenticate()
            if not auth_token:
                return self._failure("AUTH_FAILED", "تعذّرت المصادقة مع البوابة")

            order_id = self._register_order(auth_token, amount_cents, reference)
            if not order_id:
                return self._failure("ORDER_FAILED", "تعذّر تسجيل الطلب لدى البوابة")

            payment_token = self._payment_key(auth_token, order_id, amount_cents, metadata)
            if not payment_token:
                return self._failure("KEY_FAILED", "تعذّر إصدار مفتاح الدفع")
        except KeyError as exc:
            return ChargeResult(
                success=False,
                failure_code="MISSING_CREDENTIAL",
                failure_message=f"بيانات اعتماد ناقصة: {exc.args[0]}",
            )

        return ChargeResult(
            success=True,
            provider_reference=str(order_id),
            # ⚠️  **Not paid yet.** The customer is redirected to the gateway's page,
            #     and the capture is confirmed by the webhook alone. Marking it paid here
            #     means phantom revenue for everyone who opened the page and closed it.
            requires_redirect=True,
            redirect_url=(
                f"{IFRAME_URL.format(iframe_id=iframe_id)}?payment_token={payment_token}"
            ),
            raw_response={"order_id": order_id, "amount_cents": amount_cents},
        )

    def _failure(self, code: str, message: str) -> ChargeResult:
        logger.warning("Paymob: %s — %s", code, message)
        return ChargeResult(success=False, failure_code=code, failure_message=message)

    def refund(self, *, provider_reference: str, amount: Decimal, reason: str):
        try:
            auth_token = self._authenticate()
        except KeyError as exc:
            return RefundResult(
                success=False, failure_message=f"بيانات اعتماد ناقصة: {exc.args[0]}"
            )

        if not auth_token:
            return RefundResult(success=False, failure_message="تعذّرت المصادقة مع البوابة")

        response = post_json(
            f"{LIVE_BASE}/acceptance/void_refund/refund",
            {
                "auth_token": auth_token,
                "transaction_id": provider_reference,
                "amount_cents": int((amount * 100).to_integral_value()),
            },
        )

        if not response.ok:
            return RefundResult(
                success=False,
                failure_message=response.error or "رفضت البوابة الاسترداد",
                raw_response=response.data,
            )

        return RefundResult(
            success=True,
            provider_reference=str(response.data.get("id", "")),
            raw_response=response.data,
        )

    # ── The webhook ────────────────────────────────────────

    def verify_webhook(self, payload: dict, signature: str) -> bool:
        """
        ⚠️  `compare_digest`, not `==`.

            An ordinary comparison stops at the first differing character, so
            its timing leaks the correct signature character by character to
            anyone measuring it.
        """
        try:
            secret = self._credential("hmac_secret")
        except KeyError:
            logger.error("Paymob: hmac_secret غير مضبوط — رُفض الحدث")
            return False

        obj = payload.get("obj", payload)
        message = "".join(_lookup(obj, field) for field in HMAC_FIELDS)

        expected = hmac.new(secret.encode(), message.encode(), hashlib.sha512).hexdigest()

        return hmac.compare_digest(expected, (signature or "").lower())

    def parse_webhook(self, *, payload: dict, params: dict):
        """
        ⚠️  The signature is in the **URL parameter** `hmac`, not in the body.

            Reading it from the body refuses every valid event, so every card
            order stays "processing" while the money is collected.

        ⚠️  And `merchant_order_id` is our own reference — sent in `charge` and
            returned by the gateway unchanged. Matching on it is more reliable
            than matching on Paymob's own order id.
        """
        obj = payload.get("obj")
        if not isinstance(obj, dict) or not obj.get("id"):
            return None

        order = obj.get("order") if isinstance(obj.get("order"), dict) else {}

        return WebhookEnvelope(
            # ⚠️  The transaction id, not the order id: a failed payment attempt
            #     and then a successful one on the same order are two different
            #     events, and merging them under one id makes the second look like a repeat and be
            #     discarded.
            event_id=str(obj["id"]),
            event_type=str(payload.get("type") or "TRANSACTION"),
            outcome=self._outcome(obj),
            signature=str(params.get("hmac") or ""),
            merchant_reference=str(order.get("merchant_order_id") or ""),
            provider_reference=str(order.get("id") or ""),
            amount=_piastres_to_pounds(obj.get("amount_cents")),
        )

    @staticmethod
    def _outcome(obj: dict) -> str:
        """
        ⚠️  The order is deliberate: refund and cancellation come before `success`.

            A refunded transaction arrives with `success=true` as well — so
            reading `success` first marks it paid again after the money was returned.
        """
        if obj.get("is_refunded"):
            return REFUNDED
        if obj.get("is_voided") or obj.get("error_occured") or not obj.get("success"):
            return FAILED
        if obj.get("pending"):
            return PENDING
        # ⚠️  An authorisation with no capture is not a receipt: the funds are held and
        #     the money has not moved yet. Marking it captured produces phantom revenue.
        if obj.get("is_auth") and not obj.get("is_capture"):
            return AUTHORIZED
        return CAPTURED


def _piastres_to_pounds(amount_cents) -> Decimal | None:
    """⚠️  `Decimal` division, not `float` — the same rule as `core.money`."""
    if amount_cents in (None, ""):
        return None
    try:
        return Decimal(str(amount_cents)) / Decimal("100")
    except (ArithmeticError, ValueError):
        return None


def _lookup(payload: dict, path: str) -> str:
    """
    Reading `source_data.pan` from a nested payload.

    ⚠️  Booleans are sent as lower-case strings (`true`/`false`).
        Using `str(True)` produces `True` and breaks the signature silently.
    """
    value: object = payload
    for part in path.split("."):
        if not isinstance(value, dict):
            return ""
        value = value.get(part, "")

    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value)
