"""
خدمات الدفع — الواجهة المجرّدة.

⚠️  `orders` و`pos` يستدعيان `charge()` ولا يعرفان أي بوابة.

    اختيار البوابة يحدث هنا حسب القناة وطريقة الدفع والعملة
    والمبلغ والأولوية. إضافة بوابة أو تعطيلها لا يمس أي نطاق آخر.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.errors import BusinessError, ErrorCode
from core.money import ZERO
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
#  اختيار البوابة
# ═══════════════════════════════════════════════════════════


def available_providers(
    *, method: str, currency: str = "EGP", channel: str = "ONLINE", amount: Decimal = ZERO
) -> list[PaymentProvider]:
    """
    البوابات الصالحة لهذه العملية، مرتّبة بالأولوية.

    ⚠️  تُقرأ من قاعدة البيانات في كل مرة.

        بوابة يعطّلها الأدمن تختفي فورًا من الخيارات بلا إعادة نشر
        — وهذا جوهر المتطلب.
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
#  التحصيل
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
    تحصيل مبلغ.

    ⚠️  `idempotency_key` يمنع التكرار.

        نقرة مزدوجة أو إعادة محاولة على شبكة ضعيفة يجب ألا تنتج
        عمليتي دفع. المفتاح الموجود يعيد المعاملة الأصلية بلا
        تنفيذ ثانٍ.
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
        # ⚠️  فشل غير متوقع من المحوّل — تُسجَّل الحالة بوضوح
        #     لا تُترك المعاملة معلّقة بلا تفسير.
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
    تحصيل مبلغ مُصرَّح.

    للدفع عند الاستلام: يُستدعى عند تسليم الطلب فعلًا — تعليمه
    محصَّلًا قبل ذلك يعني إيرادًا وهميًا في التقارير.
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
    استرداد كلي أو جزئي.

    ⚠️  المبلغ لا يتجاوز المتبقي القابل للاسترداد — واسترداد أكثر
        مما دُفع خطأ محاسبي لا يُصحَّح بسهولة.
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
#  الأحداث الواردة
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def record_webhook(
    provider: PaymentProvider,
    *,
    event_id: str,
    event_type: str,
    payload: dict,
    signature: str = "",
) -> tuple[WebhookEvent, bool]:
    """
    تسجيل حدث وارد. يعيد `(الحدث, هل هو جديد)`.

    ⚠️  **التسجيل قبل المعالجة.**

        البوابة تعيد إرسال الحدث عند غياب الرد. بلا سجل بمعرّف
        فريد، الطلب يُعلَّم مدفوعًا مرتين — ومع الاسترداد يصير
        المبلغ مضاعفًا.
    """
    adapter = _build_adapter(provider)
    is_valid = adapter.verify_webhook(payload, signature)

    event, created = WebhookEvent.objects.get_or_create(
        provider=provider,
        event_id=event_id,
        defaults={
            "event_type": event_type,
            "payload": payload,
            "signature_valid": is_valid,
        },
    )
    return event, created


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
    """إجمالي المدفوع لمرجع — يدعم الدفع المقسّم."""
    from django.db.models import Sum

    total = PaymentTransaction.objects.filter(
        reference_type=reference_type,
        reference_id=str(reference_id),
        status__in=[TransactionStatus.AUTHORIZED, TransactionStatus.CAPTURED],
    ).aggregate(total=Sum("amount"))["total"]

    return total or ZERO
