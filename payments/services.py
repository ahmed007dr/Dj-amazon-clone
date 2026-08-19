"""
Payment services — the abstract interface.

⚠️  `orders` and `pos` call `charge()` and know no gateway.

    Gateway selection happens here, by channel, payment method, currency, amount
    and priority. Adding or disabling a gateway touches no other domain.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.errors import BusinessError, ErrorCode
from core.money import ZERO
from payments import adapters, events
from payments.adapters import PaymentAdapter, get_adapter_class
from payments.models import (
    PaymentProvider,
    PaymentTransaction,
    ProviderCredential,
    Refund,
    RefundStatus,
    TransactionStatus,
    WebhookEvent,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  Gateway selection
# ═══════════════════════════════════════════════════════════


def available_providers(
    *, method: str, currency: str = "EGP", channel: str = "ONLINE", amount: Decimal = ZERO
) -> list[PaymentProvider]:
    """
    The gateways suitable for this operation, ordered by priority.

    ⚠️  Read from the database every time.

        A gateway the admin disables disappears from the options immediately
        with no redeployment — and that is the heart of the requirement.
    """
    return [
        provider
        for provider in PaymentProvider.objects.filter(is_active=True)
        if provider.supports(method=method, currency=currency, channel=channel, amount=amount)
    ]


def _build_adapter(provider: PaymentProvider) -> PaymentAdapter:
    adapter_class = get_adapter_class(provider.adapter_key)
    if adapter_class is None:
        raise BusinessError(
            ErrorCode.PAYMENT_GATEWAY_ERROR,
            detail=f"محوّل غير معروف: {provider.adapter_key}",
        )

    credentials = {
        credential.key: credential.value
        for credential in ProviderCredential.objects.filter(
            provider=provider, is_sandbox=provider.is_sandbox
        )
    }
    return adapter_class(credentials, sandbox=provider.is_sandbox)


# ═══════════════════════════════════════════════════════════
#  Capture
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def charge(
    *,
    amount: Decimal,
    method: str,
    currency: str = "EGP",
    channel: str = "ONLINE",
    reference_type: str = "",
    reference_id: str = "",
    customer=None,
    provider: PaymentProvider | None = None,
    idempotency_key: str = "",
    metadata: dict | None = None,
) -> PaymentTransaction:
    """
    Charge an amount.

    ⚠️  `idempotency_key` prevents duplication.

        A double-click or a retry on a weak connection must not produce two
        payment operations. An existing key returns the original transaction
        with no second execution.
    """
    if idempotency_key:
        existing = PaymentTransaction.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            return existing

    if provider is None:
        candidates = available_providers(
            method=method, currency=currency, channel=channel, amount=amount
        )
        if not candidates:
            raise BusinessError(
                ErrorCode.PAYMENT_METHOD_UNAVAILABLE,
                detail="لا توجد بوابة مفعّلة لهذه العملية",
            )
        provider = candidates[0]

    payment = PaymentTransaction.objects.create(
        provider=provider,
        method=method,
        amount=amount,
        currency=currency,
        reference_type=reference_type,
        reference_id=str(reference_id) if reference_id else "",
        customer=customer,
        idempotency_key=idempotency_key,
    )

    adapter = _build_adapter(provider)

    try:
        result = adapter.charge(
            amount=amount,
            currency=currency,
            reference=payment.reference,
            metadata=metadata or {},
        )
    except Exception as exc:
        # ⚠️  An unexpected failure from the adapter — the status is recorded clearly
        #     rather than leaving the transaction suspended with no explanation.
        logger.exception("انهيار محوّل %s", provider.adapter_key)
        payment.status = TransactionStatus.FAILED
        payment.failure_code = "ADAPTER_ERROR"
        payment.failure_message = str(exc)
        payment.save(update_fields=["status", "failure_code", "failure_message"])
        raise BusinessError(ErrorCode.PAYMENT_GATEWAY_ERROR) from exc

    payment.provider_reference = result.provider_reference
    payment.provider_response = result.raw_response

    if result.success:
        payment.status = TransactionStatus.AUTHORIZED
        payment.authorized_at = timezone.now()
    else:
        payment.status = TransactionStatus.FAILED
        payment.failure_code = result.failure_code
        payment.failure_message = result.failure_message

    payment.save()
    return payment


@transaction.atomic
def capture(payment: PaymentTransaction) -> PaymentTransaction:
    """
    Capture an authorised amount.

    For cash on delivery: called when the order is actually delivered — marking
    it captured before that means phantom revenue in the reports.
    """
    if payment.status == TransactionStatus.CAPTURED:
        return payment

    if payment.status != TransactionStatus.AUTHORIZED:
        raise BusinessError(
            ErrorCode.INVALID_STATE_TRANSITION,
            detail=f"لا يمكن تحصيل معاملة في حالة {payment.status}",
            status_code=409,
        )

    payment.status = TransactionStatus.CAPTURED
    payment.captured_at = timezone.now()
    payment.save(update_fields=["status", "captured_at"])
    return payment


@transaction.atomic
def refund(
    payment: PaymentTransaction,
    amount: Decimal | None = None,
    *,
    reason: str,
    requested_by=None,
) -> Refund:
    """
    A full or partial refund.

    ⚠️  The amount does not exceed the remaining refundable balance — and
        refunding more than was paid is an accounting error that is not easily corrected.
    """
    if not payment.is_successful:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="لا يمكن استرداد معاملة غير ناجحة")
    if not reason:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="سبب الاسترداد إلزامي")

    amount = amount if amount is not None else payment.refundable_amount

    if amount <= 0:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="المبلغ يجب أن يكون موجبًا")
    if amount > payment.refundable_amount:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            detail=f"المتاح للاسترداد: {payment.refundable_amount}",
        )

    record = Refund.objects.create(
        transaction=payment, amount=amount, reason=reason, requested_by=requested_by
    )

    adapter = _build_adapter(payment.provider)
    try:
        result = adapter.refund(
            provider_reference=payment.provider_reference, amount=amount, reason=reason
        )
    except Exception as exc:
        logger.exception("فشل استرداد %s", payment.reference)
        record.status = RefundStatus.FAILED
        record.save(update_fields=["status"])
        raise BusinessError(ErrorCode.PAYMENT_GATEWAY_ERROR) from exc

    if result.success:
        record.status = RefundStatus.COMPLETED
        record.provider_reference = result.provider_reference
        record.completed_at = timezone.now()

        payment.status = (
            TransactionStatus.REFUNDED
            if payment.refundable_amount - amount <= 0
            else payment.status
        )
        payment.save(update_fields=["status"])
    else:
        record.status = RefundStatus.FAILED

    record.save()
    return record


# ═══════════════════════════════════════════════════════════
#  Inbound events
# ═══════════════════════════════════════════════════════════

#: The outcomes of processing an inbound event — the endpoint translates them into an HTTP code.
WEBHOOK_APPLIED = "applied"
WEBHOOK_DUPLICATE = "duplicate"
WEBHOOK_IGNORED = "ignored"
WEBHOOK_REJECTED = "rejected"
WEBHOOK_UNREADABLE = "unreadable"
WEBHOOK_UNKNOWN_TRANSACTION = "unknown_transaction"
WEBHOOK_AMOUNT_MISMATCH = "amount_mismatch"


@dataclass(frozen=True)
class WebhookResult:
    status: str
    payment: PaymentTransaction | None = None
    detail: str = ""


#: The adapter's outcome ← the transaction status
_OUTCOME_STATUS = {
    adapters.AUTHORIZED: TransactionStatus.AUTHORIZED,
    adapters.CAPTURED: TransactionStatus.CAPTURED,
    adapters.FAILED: TransactionStatus.FAILED,
    adapters.REFUNDED: TransactionStatus.REFUNDED,
}


@transaction.atomic
def record_webhook(
    provider: PaymentProvider,
    *,
    event_id: str,
    event_type: str,
    payload: dict,
    signature: str = "",
) -> tuple[WebhookEvent | None, bool]:
    """
    Record an inbound event **with a verified signature**. Returns `(the event, whether it is new)`.

    ⚠️  **Recording comes before processing.**

        The gateway resends the event when no response arrives. Without a record
        under a unique id, the order is marked paid twice — and with a refund
        the amount is doubled.

    ⚠️  **And a forged event never enters the table at all** — it returns `(None, False)`.

        Recording it looked more thorough for auditing, and is in truth a denial
        hole: the table is keyed on `(gateway, event id)`, so whoever sends a
        forged event with a guessed id **occupies the slot**. The real event
        then arrives with the same id, looks like a repeat and is discarded —
        leaving a paid order unmarked, from one call with no key at all.

        Rejected attempts are recorded in the text log; this table is a
        deduplication ledger, not an intrusion log.
    """
    adapter = _build_adapter(provider)

    if not adapter.verify_webhook(payload, signature):
        logger.warning("رُفض حدث بتوقيع غير صالح — البوابة %s · الحدث %s", provider.code, event_id)
        return None, False

    event, created = WebhookEvent.objects.get_or_create(
        provider=provider,
        event_id=event_id,
        defaults={
            "event_type": event_type,
            "payload": payload,
            "signature_valid": True,
        },
    )
    return event, created


def handle_webhook(provider: PaymentProvider, *, payload: dict, params: dict) -> WebhookResult:
    """
    The full path for an inbound event: read ← verify ← deduplicate ← apply.

    ⚠️  **Duplication is measured by processing, not by recording.**

        An event that was recorded and then failed to apply must be reapplied
        when the gateway resends it. Measuring by recording alone made the first
        failure final: the event exists ⟵ "a duplicate" ⟵ discarded forever, and
        the order is never marked paid.

    ⚠️  And an unexpected failure **is raised**, not swallowed.

        A 500 response makes the gateway retry — which is exactly what we want.
        Swallowing it and returning 200 tells the gateway "I have it" about an
        event that was never applied, so it stops sending and it is lost for good.
    """
    adapter = _build_adapter(provider)
    envelope = adapter.parse_webhook(payload=payload, params=params)

    if envelope is None:
        return WebhookResult(WEBHOOK_UNREADABLE, detail="حمولة لا يقرؤها محوّل هذه البوابة")

    event, created = record_webhook(
        provider,
        event_id=envelope.event_id,
        event_type=envelope.event_type,
        payload=payload,
        signature=envelope.signature,
    )

    if event is None:
        return WebhookResult(WEBHOOK_REJECTED, detail="توقيع غير صالح")

    if not created and event.is_processed:
        return WebhookResult(WEBHOOK_DUPLICATE)

    try:
        result = _apply_webhook(provider, envelope)
    except Exception as exc:
        logger.exception("فشل تطبيق حدث %s للبوابة %s", envelope.event_id, provider.code)
        mark_webhook_processed(event, error=str(exc))
        raise

    mark_webhook_processed(event, error=result.detail if result.status != WEBHOOK_APPLIED else "")
    return result


@transaction.atomic
def _apply_webhook(provider: PaymentProvider, envelope) -> WebhookResult:
    """
    Apply the event to the transaction.

    ⚠️  `select_for_update` is mandatory: the gateway may send two events a
        fraction of a second apart, and processing them together writes two
        statuses over each other in an unguaranteed order.
    """
    payment = _locate_transaction(provider, envelope)

    if payment is None:
        # ⚠️  No transaction with this reference — a retry will change nothing.
        #     It is logged clearly, and the gateway is not asked to repeat for nothing.
        logger.error(
            "حدث موثَّق بلا معاملة مطابقة — البوابة %s · مرجعنا %r · مرجعها %r",
            provider.code,
            envelope.merchant_reference,
            envelope.provider_reference,
        )
        return WebhookResult(WEBHOOK_UNKNOWN_TRANSACTION, detail="لا معاملة بهذا المرجع")

    if envelope.amount is not None and envelope.amount != payment.amount:
        # ⚠️  A valid signature proves **the sender**, not **the correct amount**.
        #
        #     A gateway that collected something other than what we asked for (or a
        #     partial payment at an outlet) arrives with a perfectly sound signature.
        #     Marking it paid creates a completed order with money missing — visible only in a monthly reconciliation.
        logger.error(
            "مبلغ الحدث لا يطابق المعاملة %s: %s مقابل %s",
            payment.reference,
            envelope.amount,
            payment.amount,
        )
        return WebhookResult(
            WEBHOOK_AMOUNT_MISMATCH,
            payment=payment,
            detail=f"المبلغ الوارد {envelope.amount} والمعاملة {payment.amount}",
        )

    new_status = _OUTCOME_STATUS.get(envelope.outcome)

    if new_status is None or not _is_forward(payment.status, new_status):
        return WebhookResult(WEBHOOK_IGNORED, payment=payment, detail=f"حالة {envelope.outcome}")

    payment.status = new_status
    updates = ["status"]

    if envelope.provider_reference and not payment.provider_reference:
        payment.provider_reference = envelope.provider_reference
        updates.append("provider_reference")

    now = timezone.now()
    if new_status == TransactionStatus.AUTHORIZED and payment.authorized_at is None:
        payment.authorized_at = now
        updates.append("authorized_at")
    if new_status == TransactionStatus.CAPTURED:
        # ⚠️  A capture implies an authorisation. A captured transaction with no
        #     authorisation time breaks any report measuring the interval between them.
        if payment.authorized_at is None:
            payment.authorized_at = now
            updates.append("authorized_at")
        payment.captured_at = now
        updates.append("captured_at")

    payment.save(update_fields=updates)

    _announce(payment, new_status)
    return WebhookResult(WEBHOOK_APPLIED, payment=payment)


def _locate_transaction(provider: PaymentProvider, envelope) -> PaymentTransaction | None:
    """
    ⚠️  Our reference first, then the gateway's.

        `merchant_reference` is the one we generated and sent, so it is the most
        reliable. The gateway's reference is a fallback for the cases where it
        does not return ours.
    """
    locked = PaymentTransaction.objects.select_for_update()

    if envelope.merchant_reference:
        payment = locked.filter(reference=envelope.merchant_reference).first()
        if payment is not None:
            return payment

    if envelope.provider_reference:
        return locked.filter(
            provider=provider, provider_reference=envelope.provider_reference
        ).first()

    return None


def _is_forward(current: str, incoming: str) -> bool:
    """
    ⚠️  The status does not go backwards.

        The gateway may send "authorised" after "captured" (a late resend of an
        old event), and a refund is final. Applying everything inbound with no
        guard returns a refunded transaction to "captured" — so the money
        appears as revenue twice.
    """
    if current == incoming:
        return False
    if current == TransactionStatus.REFUNDED:
        return False
    return not (current == TransactionStatus.CAPTURED and incoming == TransactionStatus.AUTHORIZED)


def _announce(payment: PaymentTransaction, status: str) -> None:
    """
    ⚠️  **Announce, do not call.**

        `payments` sits below `orders` in the layer diagram, so it must not
        import it to mark the order paid. The signal inverts the direction — see
        `payments/events.py`.
    """
    signal = {
        TransactionStatus.AUTHORIZED: events.payment_authorized,
        TransactionStatus.CAPTURED: events.payment_captured,
        TransactionStatus.FAILED: events.payment_failed,
        TransactionStatus.REFUNDED: events.payment_refunded,
    }.get(status)

    if signal is not None:
        signal.send(sender=PaymentTransaction, payment=payment)


@transaction.atomic
def mark_webhook_processed(event: WebhookEvent, *, error: str = "") -> WebhookEvent:
    event.is_processed = not error
    event.processed_at = timezone.now()
    event.processing_error = error
    event.save(update_fields=["is_processed", "processed_at", "processing_error"])
    return event


def transactions_for(reference_type: str, reference_id) -> list[PaymentTransaction]:
    return list(
        PaymentTransaction.objects.filter(
            reference_type=reference_type, reference_id=str(reference_id)
        ).select_related("provider")
    )


def total_paid(reference_type: str, reference_id) -> Decimal:
    """The total paid against a reference — it supports split payment."""
    from django.db.models import Sum

    total = PaymentTransaction.objects.filter(
        reference_type=reference_type,
        reference_id=str(reference_id),
        status__in=[TransactionStatus.AUTHORIZED, TransactionStatus.CAPTURED],
    ).aggregate(total=Sum("amount"))["total"]

    return total or ZERO
