"""
Tests for the Paymob and Fawry adapters.

⚠️  **What can be tested without a real account is what actually matters:**

        · the signatures    ⟵ an error there accepts a forged event or refuses a valid one
        · amount arithmetic ⟵ an error there collects the wrong amount
        · failure behaviour ⟵ silent success marks an order paid with no money

    The happy path needs the sandbox, and that is stated explicitly in
    `payments/gateways/__init__.py` and is not claimed to be tested.
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
#  Missing credentials
# ═══════════════════════════════════════════════════════════


class TestMissingCredentials:
    """
    ⚠️  The failure names the missing key.

        "Payment failed" alone makes the admin hunt through the gateway while
        the problem is a field left blank in their own panel.
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
        """With no key there is no verification — and accepting by default means marking any order
        paid."""
        assert PaymobAdapter({}, sandbox=True).verify_webhook({}, "anything") is False
        assert FawryAdapter({}, sandbox=True).verify_webhook({}, "anything") is False


# ═══════════════════════════════════════════════════════════
#  Paymob — signature and amounts
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
        ⚠️  **The real attack**: altering the amount while keeping the signature.

            Without verification, any party can mark a hundred-thousand order paid with one pound.
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
        ⚠️  `str(True)` produces `True` with a capital letter and breaks every signature silently.
        """
        assert _lookup({"success": True}, "success") == "true"
        assert _lookup({"success": False}, "success") == "false"

    def test_nested_paths_are_read(self):
        assert _lookup({"source_data": {"pan": "1234"}}, "source_data.pan") == "1234"
        assert _lookup({"source_data": {}}, "source_data.pan") == ""
        assert _lookup({}, "order.id") == ""

    def test_field_order_is_part_of_the_contract(self):
        """Reordering the fields produces a different signature — which is why the order is
        fixed."""
        payload = self._payload()
        forward = "".join(_lookup(payload["obj"], f) for f in HMAC_FIELDS)
        reversed_order = "".join(_lookup(payload["obj"], f) for f in reversed(HMAC_FIELDS))
        assert forward != reversed_order


class TestPaymobAmounts:
    def test_amount_is_converted_to_piastres(self):
        """
        ⚠️  Sending 150.00 instead of 15000 collects one and a half pounds instead of a hundred and
            fifty.
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
        ⚠️  Three consecutive steps: a partial success produces a link with an
            incomplete key that fails at the customer's end rather than at ours.
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
#  Fawry — signature and amounts
# ═══════════════════════════════════════════════════════════


class TestFawry:
    def test_amount_always_has_two_decimals(self):
        """
        ⚠️  `150` instead of `150.00` in the signature string makes the server
            compute a different signature — and it fails with no useful message.
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
        ⚠️  **The most dangerous trap**: Fawry returns 200 with the failure code in the body.

            Inferring from the HTTP code alone marks an order paid while the
            body says "invalid data".
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
        ⚠️  `PAYATFAWRY` gives a **reference number** the customer pays with later.

            The money has not been taken yet; the capture is confirmed by the
            webhook alone.
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
        ⚠️  A production host in test mode collects real money during a test.
        """
        assert FawryAdapter({}, sandbox=True).base_url != FawryAdapter({}, sandbox=False).base_url
        assert "staging" in FawryAdapter({}, sandbox=True).base_url


# ═══════════════════════════════════════════════════════════
#  Transport
# ═══════════════════════════════════════════════════════════


class TestTransport:
    def test_network_failure_never_raises(self):
        """
        ⚠️  Raising leaves the order suspended between "paid" and "not paid".
        """
        import requests

        from payments.gateways.transport import post_json

        with patch("requests.post", side_effect=requests.Timeout()):
            response = post_json("https://example.test/x", {})

        assert not response.ok
        assert response.status == 0

    def test_html_response_is_captured_not_crashed(self):
        """A gateway in maintenance returns HTML — crashing on it hides the cause."""
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
    ⚠️  An external gateway enabled with no keys fails on the first purchase.

        The cash and transfer adapters are exempt because the payment happens
        outside any gateway.
    """
    from payments.serializers import _CREDENTIAL_FREE_ADAPTERS

    assert "paymob" not in _CREDENTIAL_FREE_ADAPTERS
    assert "fawry" not in _CREDENTIAL_FREE_ADAPTERS
