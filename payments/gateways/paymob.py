"""
محوّل Paymob.

⚠️  التحصيل **ثلاث خطوات** لا واحدة:

        ١. مصادقة   ⟵ api_key            →  auth_token
        ٢. تسجيل طلب ⟵ auth_token         →  order_id
        ٣. مفتاح دفع ⟵ order_id + بيانات  →  payment_token
                                             →  رابط الـ iframe

    الثلاثة نداءات متتابعة، وفشل أيٍّ منها فشل للعملية كلها. تجاهل
    ذلك ينتج رابط دفع بمفتاح منتهٍ يفشل عند العميل لا عندنا.

⚠️  **المبالغ بالقروش** (`amount_cents`).

    إرسال ١٥٠.٠٠ بدل ١٥٠٠٠ يحصّل جنيهًا ونصفًا بدل مئة وخمسين.
    التحويل يقع هنا مرة واحدة وبـ `Decimal`.

⚠️  التحقق من الويب‌هوك **HMAC-SHA512 على حقول بترتيب محدَّد**.

    الترتيب جزء من العقد لا تفصيل تنفيذي: تغييره يجعل كل توقيع
    صحيح يبدو مزوَّرًا، والعكس أخطر.

⚠️  لم يُختبر مقابل حساب حقيقي — انظر `payments/gateways/__init__.py`.
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

#: ⚠️  ترتيب حقول توقيع الويب‌هوك — **جزء من العقد**.
#:     أبجدي كما توثّقه Paymob؛ أي إعادة ترتيب تكسر كل تحقّق.
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

#: بيانات فوترة إلزامية عند Paymob — الفراغ يُرفَض، و`NA` هو البديل
#: المتفق عليه للحقل غير المتوفر.
BILLING_PLACEHOLDER = "NA"


@register
class PaymobAdapter(PaymentAdapter):
    key = "paymob"

    # ── بيانات الاعتماد ────────────────────────────────────

    def _credential(self, name: str) -> str:
        value = self.credentials.get(name, "")
        if not value:
            # ⚠️  الفشل صريح باسم المفتاح الناقص.
            #
            #     «فشل الدفع» وحدها تجعل الأدمن يبحث في البوابة
            #     بينما المشكلة حقل لم يُملأ في لوحته.
            raise KeyError(name)
        return value

    # ── الخطوات الثلاث ─────────────────────────────────────

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
                # ⚠️  الطلب يُنشأ مرة واحدة لكل مرجع؛ التكرار يُرفض
                #     من Paymob وهو السلوك المطلوب لا خطأ.
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
        ⚠️  كل الحقول إلزامية عند Paymob.

            الحقل الفارغ يُرفَض الطلب كله برسالة غامضة، ولذلك
            `NA` لما لا نملكه فعلًا بدل تركه فارغًا.
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

    # ── الواجهة ────────────────────────────────────────────

    def charge(self, *, amount: Decimal, currency: str, reference: str, metadata: dict):
        try:
            iframe_id = self._credential("iframe_id")
        except KeyError as exc:
            return ChargeResult(
                success=False,
                failure_code="MISSING_CREDENTIAL",
                failure_message=f"بيانات اعتماد ناقصة: {exc.args[0]}",
            )

        # ⚠️  القروش عدد صحيح — التقريب قبل التحويل لا بعده.
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
            # ⚠️  **لم يُدفع بعد.** العميل يُحوَّل إلى صفحة البوابة،
            #     والتحصيل يتأكد بالويب‌هوك وحده. تعليمه مدفوعًا هنا
            #     يعني إيرادًا وهميًا عن كل من فتح الصفحة وأغلقها.
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

    # ── الويب‌هوك ──────────────────────────────────────────

    def verify_webhook(self, payload: dict, signature: str) -> bool:
        """
        ⚠️  `compare_digest` لا `==`.

            المقارنة العادية تنتهي عند أول محرف مختلف، فيسرّب زمنُها
            التوقيعَ الصحيح محرفًا محرفًا لمن يقيسه.
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
        ⚠️  التوقيع في **معامل الرابط** `hmac` لا في الجسم.

            قراءته من الجسم ترفض كل حدث صحيح، فيبقى كل طلب بطاقة
            «قيد المعالجة» بينما المال محصَّل.

        ⚠️  و`merchant_order_id` هو مرجعنا نحن — أُرسل في `charge`
            وتُعيده البوابة كما هو. المطابقة به أوثق من المطابقة
            بمعرّف الطلب لدى Paymob.
        """
        obj = payload.get("obj")
        if not isinstance(obj, dict) or not obj.get("id"):
            return None

        order = obj.get("order") if isinstance(obj.get("order"), dict) else {}

        return WebhookEnvelope(
            # ⚠️  معرّف المعاملة لا معرّف الطلب: محاولة الدفع الفاشلة
            #     ثم الناجحة على نفس الطلب حدثان مختلفان، ودمجهما
            #     تحت معرّف واحد يجعل الثاني يبدو تكرارًا فيُهمَل.
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
        ⚠️  الترتيب مقصود: الاسترداد والإلغاء يسبقان `success`.

            المعاملة المستردة تصل بـ `success=true` أيضًا — فقراءة
            `success` أولًا تعيد تعليمها مدفوعة بعد ردّ المال.
        """
        if obj.get("is_refunded"):
            return REFUNDED
        if obj.get("is_voided") or obj.get("error_occured") or not obj.get("success"):
            return FAILED
        if obj.get("pending"):
            return PENDING
        # ⚠️  التصريح بلا تحصيل ليس قبضًا: الرصيد محجوز والمال لم
        #     ينتقل بعد. تعليمه محصَّلًا ينتج إيرادًا وهميًا.
        if obj.get("is_auth") and not obj.get("is_capture"):
            return AUTHORIZED
        return CAPTURED


def _piastres_to_pounds(amount_cents) -> Decimal | None:
    """⚠️  قسمة `Decimal` لا `float` — نفس قاعدة `core.money`."""
    if amount_cents in (None, ""):
        return None
    try:
        return Decimal(str(amount_cents)) / Decimal("100")
    except (ArithmeticError, ValueError):
        return None


def _lookup(payload: dict, path: str) -> str:
    """
    قراءة `source_data.pan` من حمولة متداخلة.

    ⚠️  القيم المنطقية تُرسَل نصًّا بأحرف صغيرة (`true`/`false`).
        استخدام `str(True)` ينتج `True` فيكسر التوقيع بصمت.
    """
    value: object = payload
    for part in path.split("."):
        if not isinstance(value, dict):
            return ""
        value = value.get(part, "")

    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value)
