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
#  البوابات الخارجية
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  Paymob و Fawry مؤجّلتان حتى حسم قاعدة العمل ٦.
#
#      بناء محوّل لبوابة قبل معرفة أيها ستُستخدم فعلًا يعني كودًا
#      مبنيًا على وثائق لم تُقرأ وحسابًا لم يُفتح. البنية جاهزة
#      لاستقبالهما: محوّل جديد + صف في `PaymentProvider` — بلا مساس
#      بأي نطاق آخر.
