"""
محوّلات بوابات الدفع.

⚠️  **إضافة بوابة = محوّل هنا + تفعيلها من لوحة الأدمن.**

    لا تعديل في `orders` ولا في `cart` ولا في أي نطاق آخر — كلها
    تعرف `payments.services` فقط، لا أي بوابة بعينها. (ADR-15)

⚠️  ولا بوابة **مثبتة في الكود**: السجل يُملأ وقت التشغيل، فبوابة
    معطّلة تختفي من الخيارات بلا إعادة نشر.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChargeResult:
    """نتيجة محاولة تحصيل."""

    success: bool
    provider_reference: str = ""
    requires_redirect: bool = False
    redirect_url: str = ""
    failure_code: str = ""
    failure_message: str = ""
    raw_response: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RefundResult:
    success: bool
    provider_reference: str = ""
    failure_message: str = ""
    raw_response: dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════
#  الأحداث الواردة
# ═══════════════════════════════════════════════════════════

#: النتائج التي يترجم إليها المحوّل حدثَ بوابته.
#:
#: ⚠️  نصوص مجرّدة لا `TransactionStatus`: الطبقة هنا **لا تستورد
#:     النماذج**. المحوّل يعرف عقد بوابته ولا يعرف كيف نخزّن الحالة،
#:     والترجمة تقع في `payments.services` وحدها.
AUTHORIZED = "AUTHORIZED"
CAPTURED = "CAPTURED"
FAILED = "FAILED"
PENDING = "PENDING"
REFUNDED = "REFUNDED"

OUTCOMES = frozenset({AUTHORIZED, CAPTURED, FAILED, PENDING, REFUNDED})


@dataclass(frozen=True)
class WebhookEnvelope:
    """
    حدث وارد بعد ترجمته من لهجة البوابة إلى لغتنا.

    ⚠️  `event_id` **يجب أن يكون فريدًا لكل تغيّر حالة** لا لكل
        معاملة.

        بوابة ترسل «صدر الرقم» ثم «دُفع» بنفس المعرّف تجعل الحدث
        الثاني يبدو تكرارًا للأول — فيُهمَل، ويبقى الطلب غير مدفوع
        بينما المال في الحساب.

    ⚠️  و`amount` ليس للعرض: يُقارَن بمبلغ معاملتنا قبل تعليمها
        مدفوعة. توقيع صحيح على مبلغ مختلف يعني بوابة حصّلت غير ما
        طلبناه — وهو ما لا يكشفه التحقّق من التوقيع وحده.
    """

    event_id: str
    event_type: str
    outcome: str
    signature: str = ""
    #: مرجعنا نحن — `PaymentTransaction.reference`
    merchant_reference: str = ""
    #: مرجع البوابة — يُستخدم حين يغيب مرجعنا
    provider_reference: str = ""
    amount: Decimal | None = None


class PaymentAdapter(ABC):
    """
    عقد المحوّل.

    ⚠️  كل محوّل مسؤول عن **ألا يرفع استثناءً**.

        فشل البوابة حالة عمل متوقعة لا خطأ برمجي — رفع الاستثناء
        يترك الطلب في حالة غامضة بين «دُفع» و«لم يُدفع».
    """

    #: يُسجَّل به في `PaymentProvider.adapter_key`
    key: str = ""

    def __init__(self, credentials: dict, *, sandbox: bool = True):
        self.credentials = credentials
        self.sandbox = sandbox

    @abstractmethod
    def charge(
        self, *, amount: Decimal, currency: str, reference: str, metadata: dict
    ) -> ChargeResult: ...

    @abstractmethod
    def refund(self, *, provider_reference: str, amount: Decimal, reason: str) -> RefundResult: ...

    def verify_webhook(self, payload: dict, signature: str) -> bool:
        """
        التحقق من توقيع الحدث الوارد.

        ⚠️  الافتراضي `False` عمدًا.

            محوّل لم ينفّذ التحقق يجب ألا يقبل أحداثًا — القبول
            الافتراضي يعني أن أي طرف يستطيع تعليم طلب كمدفوع
            بنداء واحد.
        """
        return False

    def parse_webhook(self, *, payload: dict, params: dict) -> WebhookEnvelope | None:
        """
        حمولة البوابة ← ظرف موحّد. `None` = لا يفهمها هذا المحوّل.

        ⚠️  `params` معاملات الرابط لا الجسم — وليست ترفًا:

            Paymob ترسل التوقيع في **معامل رابط** (`?hmac=…`) بينما
            Fawry ترسله داخل الجسم. محوّل يقرأ الجسم وحده يرفض كل
            حدث من الأولى وهو صحيح.

        ⚠️  والافتراضي `None` كنظيره في `verify_webhook`: محوّل لم
            ينفّذ القراءة لا يستقبل شيئًا.
        """
        return None


# ═══════════════════════════════════════════════════════════
#  الدفع عند الاستلام
# ═══════════════════════════════════════════════════════════


class CashOnDeliveryAdapter(PaymentAdapter):
    """
    دفع عند الاستلام.

    ⚠️  لا تحصيل الآن — المال يُقبض عند التسليم.

        المعاملة تُسجَّل بحالة `PENDING` وتُحصَّل يدويًا عند
        التسليم. تعليمها `CAPTURED` فورًا يعني إيرادًا وهميًا في
        كل تقرير مالي.
    """

    key = "cash_on_delivery"

    def charge(self, *, amount, currency, reference, metadata):
        return ChargeResult(
            success=True,
            provider_reference=f"COD-{reference}",
            raw_response={"mode": "cash_on_delivery", "collected": False},
        )

    def refund(self, *, provider_reference, amount, reason):
        # لم يُقبض مال — لا استرداد فعلي
        return RefundResult(
            success=True,
            provider_reference=f"COD-REFUND-{provider_reference}",
            raw_response={"mode": "cash_on_delivery", "note": "لم يُقبض مبلغ"},
        )


class CashAdapter(PaymentAdapter):
    """نقدي على الكاونتر — لنقطة البيع. التحصيل فوري وحقيقي."""

    key = "cash"

    def charge(self, *, amount, currency, reference, metadata):
        return ChargeResult(
            success=True,
            provider_reference=f"CASH-{reference}",
            raw_response={"mode": "cash", "collected": True},
        )

    def refund(self, *, provider_reference, amount, reason):
        return RefundResult(
            success=True,
            provider_reference=f"CASH-REFUND-{provider_reference}",
            raw_response={"mode": "cash"},
        )


class BankTransferAdapter(PaymentAdapter):
    """تحويل بنكي — يُؤكَّد يدويًا بعد مراجعة الحساب."""

    key = "bank_transfer"

    def charge(self, *, amount, currency, reference, metadata):
        return ChargeResult(
            success=True,
            provider_reference=f"BANK-{reference}",
            raw_response={"mode": "bank_transfer", "awaiting_confirmation": True},
        )

    def refund(self, *, provider_reference, amount, reason):
        return RefundResult(
            success=True,
            provider_reference=f"BANK-REFUND-{provider_reference}",
            raw_response={"mode": "bank_transfer", "manual": True},
        )


# ═══════════════════════════════════════════════════════════
#  السجل
# ═══════════════════════════════════════════════════════════

_REGISTRY: dict[str, type[PaymentAdapter]] = {}


def register(adapter_class: type[PaymentAdapter]) -> type[PaymentAdapter]:
    if not adapter_class.key:
        raise ValueError(f"{adapter_class.__name__} بلا `key`")
    _REGISTRY[adapter_class.key] = adapter_class
    return adapter_class


def get_adapter_class(key: str) -> type[PaymentAdapter] | None:
    return _REGISTRY.get(key)


def available_adapters() -> list[str]:
    return sorted(_REGISTRY)


register(CashOnDeliveryAdapter)
register(CashAdapter)
register(BankTransferAdapter)

# ═══════════════════════════════════════════════════════════
#  البوابات الخارجية — Paymob · Fawry  (قاعدة العمل ٦، 2026-08-14)
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  الاستيراد **في آخر الملف** لا في رأسه.
#
#      المحوّلان يستوردان `register` و`PaymentAdapter` من هنا؛
#      استيرادهما في الأعلى قبل تعريفهما يرفع `ImportError` عند
#      إقلاع Django — وهو فشل يظهر كخطأ استيراد غامض لا كسبب حقيقي.
#
#  ⚠️  ولم يُختبرا مقابل حساب حقيقي بعد.
#      انظر التحذير الكامل في `payments/gateways/__init__.py`.

from payments.gateways import fawry, paymob  # noqa: E402,F401  (تسجيل ذاتي)
