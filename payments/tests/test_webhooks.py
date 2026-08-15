"""
نقطة استقبال أحداث البوابات.

⚠️  **هذه النقطة هي الطرف الوحيد الذي يجعل الدفع الإلكتروني حقيقيًا.**

    `charge` تُصدر رابطًا أو رقمًا؛ ولا تعرف إن دفع العميل. الويب‌هوك
    وحده يقول «قُبض المال». نقطة غائبة أو معطوبة تعني طلبات تبقى
    «قيد المعالجة» بينما المبالغ في الحساب البنكي.

⚠️  وهي **بلا مصادقة** — فكل خاصية هنا حارس أمني لا تفصيل سلوكي.
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
#  التركيب
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
    """حمولة Paymob كما تصل فعلًا — متداخلة وبقيم منطقية."""
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
    """تسليم حدث كما تفعل البوابة: التوقيع في معامل الرابط."""
    signature = sign(payload) if signature is None else signature
    return client.post(
        f"{webhook_url(code)}?hmac={signature}",
        payload,
        format="json",
    )


# ═══════════════════════════════════════════════════════════
#  المسار الصحيح
# ═══════════════════════════════════════════════════════════


class TestSuccessfulDelivery:
    def test_a_signed_event_marks_the_payment_captured(self, client, payment):
        response = deliver(client, paymob_payload(payment))

        assert response.status_code == 200
        assert response.data["status"] == "applied"

        payment.refresh_from_db()
        assert payment.status == TransactionStatus.CAPTURED
        assert payment.captured_at is not None
        # ⚠️  التحصيل يعني التصريح ضمنًا — تقرير يقيس المدة بينهما
        #     ينكسر على معاملة محصَّلة بلا وقت تصريح.
        assert payment.authorized_at is not None

    def test_the_event_is_recorded_for_audit(self, client, payment, provider):
        deliver(client, paymob_payload(payment, event_id="99001"))

        event = WebhookEvent.objects.get(provider=provider, event_id="99001")
        assert event.signature_valid
        assert event.is_processed
        assert event.processing_error == ""

    def test_higher_layers_are_told_without_being_imported(self, client, payment):
        """
        ⚠️  `payments` **تحت** `orders` في مخطط الطبقات، فلا يجوز أن
            يعلّم الطلب مدفوعًا بنفسه. الإشارة هي الطريق الوحيد.
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
        ⚠️  البوابة لا تملك حسابًا ولا توكنًا. ترويسة مصادقة تالفة
            يجب ألا تُسقط حدثًا صحيحًا.
        """
        client.credentials(HTTP_AUTHORIZATION="Bearer not-a-real-token")
        assert deliver(client, paymob_payload(payment)).status_code == 200


# ═══════════════════════════════════════════════════════════
#  التزوير
# ═══════════════════════════════════════════════════════════


class TestForgery:
    def test_a_bad_signature_changes_nothing(self, client, payment):
        """
        ⚠️  **الهجوم الأول والأوضح**: نداء واحد يعلّم طلبًا كمدفوع.
        """
        response = deliver(client, paymob_payload(payment), signature="0" * 128)

        assert response.status_code == 403
        payment.refresh_from_db()
        assert payment.status == TransactionStatus.PENDING

    def test_a_tampered_amount_is_rejected(self, client, payment):
        """التوقيع محسوب على المبلغ الأصلي — تعديله يبطله."""
        payload = paymob_payload(payment)
        signature = sign(payload)
        payload["obj"]["amount_cents"] = 100

        response = client.post(f"{webhook_url()}?hmac={signature}", payload, format="json")

        assert response.status_code == 403
        payment.refresh_from_db()
        assert payment.status == TransactionStatus.PENDING

    def test_a_forged_event_cannot_block_the_genuine_one(self, client, payment, provider):
        """
        ⚠️  **ثغرة تعطيل صامتة** — أخطر ما في هذا الملف.

            جدول المنع التكراري مفتاحه `(البوابة, معرّف الحدث)`.
            لو سُجِّل الحدث المزوَّر قبل التحقق لَحجز الخانة: ثم يصل
            الحقيقي بنفس المعرّف فيبدو تكرارًا ويُهمَل — ويبقى طلب
            مدفوع بلا تعليم، بنداء واحد بلا أي مفتاح.

            ولذلك المزوَّر لا يدخل الجدول أصلًا.
        """
        payload = paymob_payload(payment, event_id="ATTACKER-GUESS")

        assert deliver(client, payload, signature="deadbeef").status_code == 403
        assert not WebhookEvent.objects.filter(event_id="ATTACKER-GUESS").exists()

        # الحدث الحقيقي بنفس المعرّف يمرّ كأن شيئًا لم يكن
        assert deliver(client, payload).status_code == 200
        payment.refresh_from_db()
        assert payment.status == TransactionStatus.CAPTURED

    def test_an_amount_that_does_not_match_is_never_marked_paid(self, client, payment):
        """
        ⚠️  التوقيع الصحيح يثبت **المُرسِل** لا **المبلغ الصحيح**.

            بوابة حصّلت غير ما طلبناه تصل بتوقيع سليم تمامًا؛
            وتعليمها مدفوعة يخلق طلبًا مكتملًا بمال ناقص لا يظهر
            إلا في مطابقة شهرية.
        """
        response = deliver(client, paymob_payload(payment, amount_cents=9900))

        assert response.status_code == 200
        assert response.data["status"] == "amount_mismatch"

        payment.refresh_from_db()
        assert payment.status == TransactionStatus.PENDING


# ═══════════════════════════════════════════════════════════
#  التكرار
# ═══════════════════════════════════════════════════════════


class TestIdempotency:
    def test_the_same_event_is_applied_once(self, client, payment):
        """
        ⚠️  البوابة تعيد الإرسال عند غياب الرد. بلا منع تكرار،
            الطلب يُعلَّم مدفوعًا مرتين — ومع الاسترداد يصير المبلغ
            مضاعفًا.
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
        ⚠️  التكرار يُقاس بالمعالجة لا بالتسجيل.

            حدث سُجِّل ثم فشل تطبيقه يجب أن يُطبَّق حين تعيد البوابة
            إرساله. قياسه بالتسجيل كان يجعل أول فشل نهائيًا.
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
#  الحالات
# ═══════════════════════════════════════════════════════════


class TestOutcomes:
    def test_a_failed_transaction_is_recorded_as_failed(self, client, payment):
        response = deliver(client, paymob_payload(payment, success=False))

        assert response.data["status"] == "applied"
        payment.refresh_from_db()
        assert payment.status == TransactionStatus.FAILED

    def test_authorisation_without_capture_is_not_payment(self, client, payment):
        """
        ⚠️  الرصيد محجوز والمال لم ينتقل. تعليمه محصَّلًا ينتج
            إيرادًا وهميًا في كل تقرير مالي.
        """
        deliver(client, paymob_payload(payment, is_auth=True, is_capture=False))

        payment.refresh_from_db()
        assert payment.status == TransactionStatus.AUTHORIZED
        assert payment.captured_at is None

    def test_a_refunded_transaction_is_never_pulled_back(self, client, payment):
        """
        ⚠️  إعادة إرسال متأخرة لحدث نجاح قديم بعد ردّ المال كانت
            تُظهر المبلغ إيرادًا مرة ثانية.
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
#  الحدود
# ═══════════════════════════════════════════════════════════


class TestBoundaries:
    def test_a_disabled_provider_receives_nothing(self, client, payment, provider):
        """
        ⚠️  إيقاف بوابة يجب أن يكون إيقافًا كاملًا.

            بقاء نقطتها مفتوحة يعني أنها ما زالت تعلّم طلبات
            كمدفوعة بينما اختفت من خيارات العميل.
        """
        provider.is_active = False
        provider.save(update_fields=["is_active"])

        assert deliver(client, paymob_payload(payment)).status_code == 404

    def test_an_unknown_provider_code_is_not_found(self, client, payment):
        assert deliver(client, paymob_payload(payment), code="stripe").status_code == 404

    def test_an_unreadable_payload_is_refused(self, client, provider):
        """حمولة لا يفهمها المحوّل لا تُسجَّل ولا تُطبَّق."""
        response = client.post(f"{webhook_url()}?hmac=x", {"hello": "world"}, format="json")

        assert response.status_code == 400
        assert response.data["status"] == "unreadable"
        assert WebhookEvent.objects.count() == 0

    def test_an_event_without_a_matching_transaction_is_not_retried(self, client, provider):
        """
        ⚠️  ٢٠٠ لا خطأ: البوابة تعيد الإرسال على أي رد غير ناجح،
            وحدث بمرجع لا نعرفه سيصل كل بضع دقائق إلى الأبد.
            يُسجَّل بوضوح ولا يُطلَب تكراره بلا فائدة.
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
    ⚠️  Fawry لا ترسل معرّف حدث — ترسل رقم المرجع وحالته، والرقم
        ثابت عبر عمر الطلب. اتخاذه معرّفًا يجعل «دُفع» بعد «صدر
        الرقم» يبدو تكرارًا فيُهمَل، ويبقى الطلب غير مدفوع بينما
        المال قُبض في المنفذ.
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
        """`NEW` يعني «صدر الرقم» — والعميل أمامه مهلة ليدفع."""
        envelope = self._adapter().parse_webhook(payload=self._payload("NEW"), params={})
        assert envelope.outcome == "PENDING"

    def test_the_signature_comes_from_the_body_not_the_url(self):
        """بخلاف Paymob — قراءته من الرابط ترفض كل إشعار صحيح."""
        envelope = self._adapter().parse_webhook(payload=self._payload("PAID"), params={})
        assert envelope.signature == "sig"
        assert envelope.amount == Decimal("150.00")

    def test_a_payload_without_a_status_is_unreadable(self):
        assert self._adapter().parse_webhook(payload={"fawryRefNumber": "1"}, params={}) is None
