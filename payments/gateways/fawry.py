"""
محوّل Fawry.

⚠️  التوقيع **SHA-256 على سلسلة مرتَّبة** — والترتيب جزء من العقد.

        merchantCode + merchantRefNum + customerProfileId +
        paymentMethod + amount + secureKey

    المبلغ في السلسلة برقمين عشريين دائمًا (`150.00` لا `150`)
    وإلا فشل التحقق بلا رسالة مفيدة.

⚠️  Fawry ليست بطاقة فقط: `PAYATFAWRY` يولّد **رقم مرجعي** يدفع به
    العميل في أي منفذ فوري خلال مهلة.

    وهذا يعني أن `charge` الناجح **لا يعني أن المال قُبض** — يعني
    أن رقم الدفع صدر. التحصيل يتأكد بالويب‌هوك وحده، وتعليمه
    مدفوعًا هنا ينتج إيرادًا وهميًا عن كل من طلب رقمًا ولم يدفع.

⚠️  لم يُختبر مقابل حساب حقيقي — انظر `payments/gateways/__init__.py`.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from decimal import ROUND_HALF_UP, Decimal

from payments.adapters import ChargeResult, PaymentAdapter, RefundResult, register

from .transport import post_json

logger = logging.getLogger(__name__)

LIVE_BASE = "https://www.atfawry.com"
SANDBOX_BASE = "https://atfawry.fawrystaging.com"

CHARGE_PATH = "/ECommerceWeb/Fawry/payments/charge"
REFUND_PATH = "/ECommerceWeb/Fawry/payments/refund"


def _money(amount: Decimal) -> str:
    """
    ⚠️  رقمان عشريان **دائمًا** — في التوقيع وفي الحمولة معًا.

        `Decimal("150")` تُسلسَل `150` فيُحسب التوقيع على سلسلة
        مختلفة عمّا يحسبه الخادم، ويفشل بلا سبب مفهوم.
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

    # ── الواجهة ────────────────────────────────────────────

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

        # ⚠️  `200 OK` **ليس نجاحًا**: Fawry تعيد رمز الحالة في الجسم.
        #
        #     الاستنتاج من رمز HTTP وحده يعلّم طلبًا كمدفوع بينما
        #     الجسم يقول «بيانات غير صالحة».
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
            # ⚠️  البطاقة تحتاج تحويلًا؛ الدفع في المنفذ لا يحتاجه
            #     لأن العميل يحمل الرقم إلى الفرع.
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

    # ── الويب‌هوك ──────────────────────────────────────────

    def verify_webhook(self, payload: dict, signature: str) -> bool:
        """
        ⚠️  توقيع الإشعار يُحسب على حقول **مختلفة** عن توقيع الطلب.

            استخدام صيغة الطلب هنا يرفض كل إشعار صحيح — فيبقى كل
            طلب «قيد المعالجة» بينما المال محصَّل فعلًا.
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

        # مقارنة ثابتة الزمن — انظر نظيرتها في محوّل Paymob
        return hmac.compare_digest(expected, (signature or "").lower())
