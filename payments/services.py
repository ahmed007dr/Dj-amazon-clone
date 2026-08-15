"""
خدمات الدفع — الواجهة المجرّدة.

⚠️  `orders` و`pos` يستدعيان `charge()` ولا يعرفان أي بوابة.

    اختيار البوابة يحدث هنا حسب القناة وطريقة الدفع والعملة
    والمبلغ والأولوية. إضافة بوابة أو تعطيلها لا يمس أي نطاق آخر.
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

#: نتائج معالجة حدث وارد — تترجمها الواجهة إلى رمز HTTP.
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


#: نتيجة المحوّل ← حالة المعاملة
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
    تسجيل حدث وارد **موثَّق التوقيع**. يعيد `(الحدث, هل هو جديد)`.

    ⚠️  **التسجيل قبل المعالجة.**

        البوابة تعيد إرسال الحدث عند غياب الرد. بلا سجل بمعرّف
        فريد، الطلب يُعلَّم مدفوعًا مرتين — ومع الاسترداد يصير
        المبلغ مضاعفًا.

    ⚠️  **والحدث المزوَّر لا يدخل الجدول أصلًا** — يعيد `(None, False)`.

        تسجيله كان يبدو أدق للتدقيق، وهو في الحقيقة ثغرة تعطيل:
        الجدول مفتاحه `(البوابة, معرّف الحدث)`، فمن يرسل حدثًا
        مزوَّرًا بمعرّف يخمّنه **يحجز الخانة**. ثم يصل الحدث الحقيقي
        بنفس المعرّف فيبدو تكرارًا ويُهمَل — ويبقى طلب مدفوع بلا
        تعليم، بنداء واحد بلا أي مفتاح.

        المحاولات المرفوضة تُسجَّل في السجل النصي؛ وهذا الجدول
        دفتر منع تكرار لا سجل اختراقات.
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
    المسار الكامل لحدث وارد: قراءة ← تحقّق ← منع تكرار ← تطبيق.

    ⚠️  **التكرار يُقاس بالمعالجة لا بالتسجيل.**

        حدث سُجِّل ثم فشل تطبيقه يجب أن يُعاد تطبيقه حين تعيد
        البوابة إرساله. قياسه بالتسجيل وحده كان يجعل أول فشل
        نهائيًا: الحدث موجود ⟵ «تكرار» ⟵ يُهمَل إلى الأبد، والطلب
        لا يُعلَّم مدفوعًا أبدًا.

    ⚠️  والفشل غير المتوقع **يُرفع** لا يُبتلع.

        الاستجابة ٥٠٠ تجعل البوابة تعيد المحاولة — وهو ما نريده
        بالضبط. ابتلاعه وإعادة ٢٠٠ يقول للبوابة «استلمتُه» عن حدث
        لم يُطبَّق، فتتوقف عن الإرسال ويضيع نهائيًا.
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
    إسقاط الحدث على المعاملة.

    ⚠️  `select_for_update` إلزامي: البوابة قد ترسل حدثين متتاليين
        بأجزاء من الثانية، ومعالجتهما معًا تكتب حالتين فوق بعضهما
        بترتيب غير مضمون.
    """
    payment = _locate_transaction(provider, envelope)

    if payment is None:
        # ⚠️  لا معاملة بهذا المرجع — إعادة المحاولة لن تغيّر شيئًا.
        #     يُسجَّل بوضوح ولا يُطلَب من البوابة أن تكرّر بلا فائدة.
        logger.error(
            "حدث موثَّق بلا معاملة مطابقة — البوابة %s · مرجعنا %r · مرجعها %r",
            provider.code,
            envelope.merchant_reference,
            envelope.provider_reference,
        )
        return WebhookResult(WEBHOOK_UNKNOWN_TRANSACTION, detail="لا معاملة بهذا المرجع")

    if envelope.amount is not None and envelope.amount != payment.amount:
        # ⚠️  التوقيع الصحيح يثبت **المُرسِل** لا **المبلغ الصحيح**.
        #
        #     بوابة حصّلت غير ما طلبناه (أو دفعة جزئية في منفذ فوري)
        #     تصل بتوقيع سليم تمامًا. تعليمها مدفوعة يخلق طلبًا
        #     مكتملًا بمال ناقص — ولا يظهر إلا في مطابقة شهرية.
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
        # ⚠️  التحصيل يعني التصريح ضمنًا. معاملة محصَّلة بلا وقت
        #     تصريح تكسر أي تقرير يقيس المدة بينهما.
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
    ⚠️  مرجعنا أولًا ثم مرجع البوابة.

        `merchant_reference` نحن من ولّده وأرسلناه، فهو الأوثق.
        ومرجع البوابة احتياط للحالات التي لا تُعيده فيها.
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
    ⚠️  الحالة لا تتراجع.

        البوابة قد ترسل «مُصرَّح» بعد «محصَّل» (إعادة إرسال متأخرة
        لحدث قديم)، والاسترداد نهائي. تطبيق كل وارد بلا حارس يعيد
        معاملة مستردة إلى «محصَّلة» — فيظهر المال إيرادًا مرتين.
    """
    if current == incoming:
        return False
    if current == TransactionStatus.REFUNDED:
        return False
    return not (current == TransactionStatus.CAPTURED and incoming == TransactionStatus.AUTHORIZED)


def _announce(payment: PaymentTransaction, status: str) -> None:
    """
    ⚠️  **الإعلان لا الاستدعاء.**

        `payments` تحت `orders` في مخطط الطبقات، فلا يجوز أن يستورده
        ليعلّم الطلب مدفوعًا. الإشارة تقلب الاتجاه — انظر
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
    """إجمالي المدفوع لمرجع — يدعم الدفع المقسّم."""
    from django.db.models import Sum

    total = PaymentTransaction.objects.filter(
        reference_type=reference_type,
        reference_id=str(reference_id),
        status__in=[TransactionStatus.AUTHORIZED, TransactionStatus.CAPTURED],
    ).aggregate(total=Sum("amount"))["total"]

    return total or ZERO
