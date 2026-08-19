"""
The Fawry adapter.

⚠️  The signature is **SHA-256 over an ordered string** — and the order is part of the contract.

        merchantCode + merchantRefNum + customerProfileId +
        paymentMethod + amount + secureKey

    The amount in the string always has two decimal places (`150.00`, not
    `150`), or verification fails with no useful message.

⚠️  Fawry is not cards only: `PAYATFAWRY` generates a **reference number** the
    customer pays with at any outlet within a time limit.

    Which means a successful `charge` **does not mean the money was taken** — it
    means the payment number was issued. The capture is confirmed by the webhook
    alone, and marking it paid here produces phantom revenue for everyone who
    requested a number and never paid.

⚠️  Not tested against a real account — see `payments/gateways/__init__.py`.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from decimal import ROUND_HALF_UP, Decimal

from payments.adapters import (
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

LIVE_BASE = "https://www.atfawry.com"
SANDBOX_BASE = "https://atfawry.fawrystaging.com"

CHARGE_PATH = "/ECommerceWeb/Fawry/payments/charge"
REFUND_PATH = "/ECommerceWeb/Fawry/payments/refund"


def _money(amount: Decimal) -> str:
    """
    ⚠️  Two decimal places **always** — in the signature and in the payload alike.

        `Decimal("150")` serialises as `150`, so the signature is computed over
        a different string from the one the server computes, and it fails for no
        comprehensible reason.
    """
    return str(amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


@register
class FawryAdapter(PaymentAdapter):
    key = "fawry"

    @property
    def base_url(self) -> str:
        return SANDBOX_BASE if self.sandbox else LIVE_BASE

    def _credential(self, name: str) -> str:
        value = self.credentials.get(name, "")
        if not value:
            raise KeyError(name)
        return value

    def _signature(self, *parts: str) -> str:
        return hashlib.sha256("".join(parts).encode()).hexdigest()

    # ── The interface ──────────────────────────────────────

    def charge(self, *, amount: Decimal, currency: str, reference: str, metadata: dict):
        try:
            merchant_code = self._credential("merchant_code")
            secure_key = self._credential("secure_key")
        except KeyError as exc:
            return ChargeResult(
                success=False,
                failure_code="MISSING_CREDENTIAL",
                failure_message=f"بيانات اعتماد ناقصة: {exc.args[0]}",
            )

        customer_id = str(metadata.get("customer_id", ""))
        payment_method = metadata.get("payment_method", "PAYATFAWRY")
        total = _money(amount)

        payload = {
            "merchantCode": merchant_code,
            "merchantRefNum": reference,
            "customerProfileId": customer_id,
            "customerMobile": metadata.get("phone", ""),
            "customerEmail": metadata.get("email", ""),
            "paymentMethod": payment_method,
            "amount": total,
            "currencyCode": currency or "EGP",
            "description": metadata.get("description", ""),
            "chargeItems": metadata.get("items", []),
            "signature": self._signature(
                merchant_code, reference, customer_id, payment_method, total, secure_key
            ),
        }

        response = post_json(f"{self.base_url}{CHARGE_PATH}", payload)

        if not response.ok:
            return ChargeResult(
                success=False,
                failure_code="GATEWAY_ERROR",
                failure_message=response.error or "رفضت البوابة الطلب",
                raw_response=response.data,
            )

        # ⚠️  `200 OK` is **not success**: Fawry returns the status code in the body.
        #
        #     Inferring from the HTTP code alone marks an order paid while the
        #     body says "invalid data".
        status_code = str(response.data.get("statusCode", ""))
        if status_code != "200":
            return ChargeResult(
                success=False,
                failure_code=f"FAWRY_{status_code or 'UNKNOWN'}",
                failure_message=response.data.get("statusDescription", "فشل الدفع"),
                raw_response=response.data,
            )

        redirect_url = response.data.get("paymentAmount") and response.data.get("nextAction", {})
        redirect = ""
        if isinstance(redirect_url, dict):
            redirect = redirect_url.get("redirectUrl", "") or ""

        return ChargeResult(
            success=True,
            provider_reference=str(response.data.get("referenceNumber", "")),
            # ⚠️  A card needs a redirect; paying at an outlet does not,
            #     because the customer carries the number to the branch.
            requires_redirect=bool(redirect),
            redirect_url=redirect,
            raw_response=response.data,
        )

    def refund(self, *, provider_reference: str, amount: Decimal, reason: str):
        try:
            merchant_code = self._credential("merchant_code")
            secure_key = self._credential("secure_key")
        except KeyError as exc:
            return RefundResult(
                success=False, failure_message=f"بيانات اعتماد ناقصة: {exc.args[0]}"
            )

        total = _money(amount)

        payload = {
            "merchantCode": merchant_code,
            "referenceNumber": provider_reference,
            "refundAmount": total,
            "reason": reason,
            "signature": self._signature(
                merchant_code, provider_reference, total, reason, secure_key
            ),
        }

        response = post_json(f"{self.base_url}{REFUND_PATH}", payload)
        status_code = str(response.data.get("statusCode", ""))

        if not response.ok or status_code != "200":
            return RefundResult(
                success=False,
                failure_message=response.data.get("statusDescription", "رفضت البوابة الاسترداد"),
                raw_response=response.data,
            )

        return RefundResult(
            success=True,
            provider_reference=provider_reference,
            raw_response=response.data,
        )

    # ── The webhook ────────────────────────────────────────

    def verify_webhook(self, payload: dict, signature: str) -> bool:
        """
        ⚠️  The notification's signature is computed over **different** fields
            from the request's signature.

            Using the request's formula here refuses every valid notification —
            so every order stays "processing" while the money has actually been collected.
        """
        try:
            secure_key = self._credential("secure_key")
        except KeyError:
            logger.error("Fawry: secure_key غير مضبوط — رُفض الإشعار")
            return False

        expected = self._signature(
            str(payload.get("fawryRefNumber", "")),
            str(payload.get("merchantRefNumber", "")),
            _money(Decimal(str(payload.get("paymentAmount", "0")))),
            _money(Decimal(str(payload.get("orderAmount", "0")))),
            str(payload.get("orderStatus", "")),
            str(payload.get("paymentMethod", "")),
            secure_key,
        )

        # A constant-time comparison — see its counterpart in the Paymob adapter
        return hmac.compare_digest(expected, (signature or "").lower())

    def parse_webhook(self, *, payload: dict, params: dict):
        """
        ⚠️  **Fawry does not send an event id.**

            It sends the reference number and its status only, and the number is
            constant over the order's lifetime: "the number was issued", then
            "paid", then "refunded" all arrive with the same `fawryRefNumber`.
            Taking it as the id makes every event after the first look like a
            repeat, so it is discarded — and the order stays unpaid while the
            money was taken at the outlet.

            The id is therefore **the number together with the status**: every
            transition is recorded once, and a resend of the same transition is
            discarded. Which is exactly what we want from a deduplication table.

        ⚠️  And the signature is in the body, not the URL — unlike Paymob.
        """
        reference = str(payload.get("fawryRefNumber") or "")
        status = str(payload.get("orderStatus") or "")

        if not reference or not status:
            return None

        return WebhookEnvelope(
            event_id=f"{reference}:{status}",
            event_type=f"ORDER_{status}",
            outcome=_STATUS_OUTCOMES.get(status, PENDING),
            signature=str(payload.get("messageSignature") or ""),
            merchant_reference=str(payload.get("merchantRefNumber") or ""),
            provider_reference=reference,
            amount=_amount_or_none(payload.get("paymentAmount")),
        )


#: Fawry statuses ← our outcomes.
#:
#: ⚠️  `NEW` is not a failure: the number was issued and the customer has time to pay at an outlet.
#:     Their transaction must stay pending rather than be closed — closing it
#:     refuses a payment that will arrive an hour later.
_STATUS_OUTCOMES = {
    "PAID": CAPTURED,
    "DELIVERED": CAPTURED,
    "NEW": PENDING,
    "UNPAID": PENDING,
    "CANCELED": FAILED,
    "EXPIRED": FAILED,
    "FAILED": FAILED,
    "REFUNDED": REFUNDED,
}


def _amount_or_none(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except ArithmeticError:
        return None
