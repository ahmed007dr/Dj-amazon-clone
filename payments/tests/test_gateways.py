"""
اختبارات محوّلَي Paymob و Fawry.

⚠️  **ما يمكن اختباره بلا حساب حقيقي هو ما يهم فعلًا:**

        · التوقيعات   ⟵ خطأ فيها يقبل حدثًا مزوَّرًا أو يرفض صحيحًا
        · حساب المبالغ ⟵ خطأ فيه يحصّل مبلغًا خاطئًا
        · سلوك الفشل  ⟵ النجاح الصامت يعلّم طلبًا كمدفوع بلا مال

    أما المسار السعيد فيحتاج البيئة التجريبية، وهو مذكور صراحةً في
    `payments/gateways/__init__.py` ولا يُدّعى أنه مُختبَر.
"""

import hashlib
import hmac
from decimal import Decimal
from unittest.mock import patch

import pytest

from payments.adapters import available_adapters, get_adapter_class
from payments.gateways.fawry import FawryAdapter, _money
from payments.gateways.paymob import HMAC_FIELDS, PaymobAdapter, _lookup
from payments.gateways.transport import GatewayResponse


def test_both_gateways_are_registered():
    assert "paymob" in available_adapters()
    assert "fawry" in available_adapters()
    assert get_adapter_class("paymob") is PaymobAdapter
    assert get_adapter_class("fawry") is FawryAdapter


# ═══════════════════════════════════════════════════════════
#  بيانات الاعتماد الناقصة
# ═══════════════════════════════════════════════════════════


class TestMissingCredentials:
    """
    ⚠️  الفشل يسمّي المفتاح الناقص.

        «فشل الدفع» وحدها تجعل الأدمن يبحث في البوابة بينما المشكلة
        حقل لم يُملأ في لوحته.
    """

    def test_paymob_names_the_missing_key(self):
        result = PaymobAdapter({}, sandbox=True).charge(
            amount=Decimal("100.00"), currency="EGP", reference="R1", metadata={}
        )
        assert not result.success
        assert result.failure_code == "MISSING_CREDENTIAL"
        assert "iframe_id" in result.failure_message

    def test_fawry_names_the_missing_key(self):
        result = FawryAdapter({}, sandbox=True).charge(
            amount=Decimal("100.00"), currency="EGP", reference="R1", metadata={}
        )
        assert not result.success
        assert "merchant_code" in result.failure_message

    def test_webhooks_are_rejected_without_a_secret(self):
        """بلا مفتاح لا تحقّق — والقبول الافتراضي يعني تعليم أي طلب كمدفوع."""
        assert PaymobAdapter({}, sandbox=True).verify_webhook({}, "anything") is False
        assert FawryAdapter({}, sandbox=True).verify_webhook({}, "anything") is False


# ═══════════════════════════════════════════════════════════
#  Paymob — التوقيع والمبالغ
# ═══════════════════════════════════════════════════════════


class TestPaymobSignature:
    SECRET = "test-hmac-secret"

    def _payload(self, **overrides):
        base = {field.replace(".", "_"): "x" for field in HMAC_FIELDS}
        return {
            "obj": {
                "amount_cents": 15000,
                "created_at": "2026-08-14T10:00:00",
                "currency": "EGP",
                "error_occured": False,
                "has_parent_transaction": False,
                "id": 123456,
                "integration_id": 999,
                "is_3d_secure": True,
                "is_auth": False,
                "is_capture": False,
                "is_refunded": False,
                "is_standalone_payment": True,
                "is_voided": False,
                "order": {"id": 7777},
                "owner": 42,
                "pending": False,
                "source_data": {"pan": "2346", "sub_type": "MasterCard", "type": "card"},
                "success": True,
                **base,
                **overrides,
            }
        }

    def _sign(self, payload):
        message = "".join(_lookup(payload["obj"], field) for field in HMAC_FIELDS)
        return hmac.new(self.SECRET.encode(), message.encode(), hashlib.sha512).hexdigest()

    def test_valid_signature_is_accepted(self):
        adapter = PaymobAdapter({"hmac_secret": self.SECRET}, sandbox=True)
        payload = self._payload()
        assert adapter.verify_webhook(payload, self._sign(payload)) is True

    def test_tampered_amount_is_rejected(self):
        """
        ⚠️  **الهجوم الحقيقي**: تعديل المبلغ مع إبقاء التوقيع.

            بلا تحقّق يستطيع أي طرف تعليم طلب بمئة ألف كمدفوع بجنيه.
        """
        adapter = PaymobAdapter({"hmac_secret": self.SECRET}, sandbox=True)
        payload = self._payload()
        signature = self._sign(payload)

        payload["obj"]["amount_cents"] = 1
        assert adapter.verify_webhook(payload, signature) is False

    def test_wrong_secret_is_rejected(self):
        payload = self._payload()
        signature = self._sign(payload)

        other = PaymobAdapter({"hmac_secret": "different"}, sandbox=True)
        assert other.verify_webhook(payload, signature) is False

    def test_booleans_serialise_lowercase(self):
        """
        ⚠️  `str(True)` ينتج `True` بحرف كبير فيكسر كل توقيع بصمت.
        """
        assert _lookup({"success": True}, "success") == "true"
        assert _lookup({"success": False}, "success") == "false"

    def test_nested_paths_are_read(self):
        assert _lookup({"source_data": {"pan": "1234"}}, "source_data.pan") == "1234"
        assert _lookup({"source_data": {}}, "source_data.pan") == ""
        assert _lookup({}, "order.id") == ""

    def test_field_order_is_part_of_the_contract(self):
        """إعادة ترتيب الحقول تنتج توقيعًا مختلفًا — ولذلك الترتيب ثابت."""
        payload = self._payload()
        forward = "".join(_lookup(payload["obj"], f) for f in HMAC_FIELDS)
        reversed_order = "".join(_lookup(payload["obj"], f) for f in reversed(HMAC_FIELDS))
        assert forward != reversed_order


class TestPaymobAmounts:
    def test_amount_is_converted_to_piastres(self):
        """
        ⚠️  إرسال ١٥٠.٠٠ بدل ١٥٠٠٠ يحصّل جنيهًا ونصفًا بدل مئة وخمسين.
        """
        captured = {}

        def fake_post(url, payload, headers=None):
            captured[url.rsplit("/", 1)[-1]] = payload
            if url.endswith("/tokens"):
                return GatewayResponse(True, 200, {"token": "auth-token"})
            if url.endswith("/orders"):
                return GatewayResponse(True, 200, {"id": 555})
            return GatewayResponse(True, 200, {"token": "pay-token"})

        adapter = PaymobAdapter(
            {"api_key": "k", "integration_id": "1", "iframe_id": "9"}, sandbox=True
        )

        with patch("payments.gateways.paymob.post_json", side_effect=fake_post):
            result = adapter.charge(
                amount=Decimal("150.00"), currency="EGP", reference="ORD-1", metadata={}
            )

        assert captured["orders"]["amount_cents"] == 15000
        assert result.success
        assert result.requires_redirect, "الدفع لم يتم بعد — العميل يُحوَّل"

    def test_failure_at_any_step_fails_the_whole_charge(self):
        """
        ⚠️  ثلاث خطوات متتابعة: نجاح جزئي ينتج رابطًا بمفتاح ناقص
            يفشل عند العميل لا عندنا.
        """
        adapter = PaymobAdapter(
            {"api_key": "k", "integration_id": "1", "iframe_id": "9"}, sandbox=True
        )

        def fail_at_order(url, payload, headers=None):
            if url.endswith("/tokens"):
                return GatewayResponse(True, 200, {"token": "auth"})
            return GatewayResponse(False, 500, {}, "خطأ")

        with patch("payments.gateways.paymob.post_json", side_effect=fail_at_order):
            result = adapter.charge(
                amount=Decimal("10.00"), currency="EGP", reference="R", metadata={}
            )

        assert not result.success
        assert result.failure_code == "ORDER_FAILED"


# ═══════════════════════════════════════════════════════════
#  Fawry — التوقيع والمبالغ
# ═══════════════════════════════════════════════════════════


class TestFawry:
    def test_amount_always_has_two_decimals(self):
        """
        ⚠️  `150` بدل `150.00` في سلسلة التوقيع يجعل الخادم يحسب
            توقيعًا مختلفًا — ويفشل بلا رسالة مفيدة.
        """
        assert _money(Decimal("150")) == "150.00"
        assert _money(Decimal("150.5")) == "150.50"
        assert _money(Decimal("150.005")) == "150.01"

    def test_signature_matches_documented_order(self):
        adapter = FawryAdapter({"merchant_code": "MC", "secure_key": "SK"}, sandbox=True)
        expected = hashlib.sha256(b"MCREF1CUSTPAYATFAWRY100.00SK").hexdigest()

        assert adapter._signature("MC", "REF1", "CUST", "PAYATFAWRY", "100.00", "SK") == expected

    def test_http_200_with_error_body_is_a_failure(self):
        """
        ⚠️  **الفخّ الأخطر**: Fawry تعيد ٢٠٠ ورمز الفشل في الجسم.

            الاستنتاج من رمز HTTP وحده يعلّم طلبًا كمدفوع بينما
            الجسم يقول «بيانات غير صالحة».
        """
        adapter = FawryAdapter({"merchant_code": "MC", "secure_key": "SK"}, sandbox=True)

        with patch(
            "payments.gateways.fawry.post_json",
            return_value=GatewayResponse(
                True, 200, {"statusCode": "9901", "statusDescription": "بيانات غير صالحة"}
            ),
        ):
            result = adapter.charge(
                amount=Decimal("100.00"), currency="EGP", reference="R", metadata={}
            )

        assert not result.success
        assert result.failure_code == "FAWRY_9901"
        assert result.raw_response["statusCode"] == "9901"

    def test_successful_charge_is_not_payment(self):
        """
        ⚠️  `PAYATFAWRY` يعطي **رقمًا مرجعيًا** يدفع به العميل لاحقًا.

            المال لم يُقبض بعد؛ التحصيل يتأكد بالويب‌هوك وحده.
        """
        adapter = FawryAdapter({"merchant_code": "MC", "secure_key": "SK"}, sandbox=True)

        with patch(
            "payments.gateways.fawry.post_json",
            return_value=GatewayResponse(
                True, 200, {"statusCode": "200", "referenceNumber": "9988776655"}
            ),
        ):
            result = adapter.charge(
                amount=Decimal("100.00"), currency="EGP", reference="R", metadata={}
            )

        assert result.success
        assert result.provider_reference == "9988776655"

    def test_sandbox_and_live_use_different_hosts(self):
        """
        ⚠️  مضيف الإنتاج في وضع التجريب يحصّل مالًا حقيقيًا في اختبار.
        """
        assert FawryAdapter({}, sandbox=True).base_url != FawryAdapter({}, sandbox=False).base_url
        assert "staging" in FawryAdapter({}, sandbox=True).base_url


# ═══════════════════════════════════════════════════════════
#  النقل
# ═══════════════════════════════════════════════════════════


class TestTransport:
    def test_network_failure_never_raises(self):
        """
        ⚠️  رفع الاستثناء يترك الطلب معلّقًا بين «دُفع» و«لم يُدفع».
        """
        import requests

        from payments.gateways.transport import post_json

        with patch("requests.post", side_effect=requests.Timeout()):
            response = post_json("https://example.test/x", {})

        assert not response.ok
        assert response.status == 0

    def test_html_response_is_captured_not_crashed(self):
        """بوابة في وضع صيانة تعيد HTML — الانهيار عليه يخفي السبب."""
        from payments.gateways.transport import post_json

        class FakeResponse:
            ok = True
            status_code = 200
            text = "<html>maintenance</html>"

            def json(self):
                raise ValueError

        with patch("requests.post", return_value=FakeResponse()):
            response = post_json("https://example.test/x", {})

        assert not response.ok
        assert "maintenance" in response.data["raw"]


@pytest.mark.django_db
def test_gateways_need_credentials_before_activation():
    """
    ⚠️  بوابة خارجية مفعّلة بلا مفاتيح تفشل عند أول عملية شراء.

        محوّلات النقد والتحويل معفاة لأن الدفع يتم خارج أي بوابة.
    """
    from payments.serializers import _CREDENTIAL_FREE_ADAPTERS

    assert "paymob" not in _CREDENTIAL_FREE_ADAPTERS
    assert "fawry" not in _CREDENTIAL_FREE_ADAPTERS
