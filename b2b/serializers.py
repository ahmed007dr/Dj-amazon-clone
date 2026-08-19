"""B2B contracts — amounts as strings (ADR-31)."""

from decimal import Decimal

from rest_framework import serializers

from b2b.models import BusinessProfile, Invoice, LedgerEntry
from core.money import MONEY_DECIMAL_PLACES, MONEY_MAX_DIGITS


class MoneySerializerField(serializers.DecimalField):
    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", MONEY_MAX_DIGITS)
        kwargs.setdefault("decimal_places", MONEY_DECIMAL_PLACES)
        kwargs.setdefault("coerce_to_string", True)
        super().__init__(**kwargs)


class BusinessProfileSerializer(serializers.ModelSerializer):
    """
    ⚠️  The credit fields are **read-only here**.

        Accepting them on a profile update means the customer raises their own
        limit with a single request. Granting goes through a dedicated admin
        endpoint that records who granted it and when.
    """

    credit_limit = MoneySerializerField(read_only=True)
    customer_number = serializers.CharField(source="customer.customer_number", read_only=True)

    class Meta:
        model = BusinessProfile
        fields = [
            "id",
            "customer_number",
            "kind",
            "legal_name",
            "license_number",
            "license_expires_on",
            "credit_status",
            "credit_limit",
            "payment_terms_days",
            "credit_note",
        ]
        read_only_fields = [
            "id",
            "customer_number",
            "credit_status",
            "credit_limit",
            "payment_terms_days",
            "credit_note",
        ]


class AccountSummarySerializer(serializers.Serializer):
    """The account dashboard — what a business customer sees the moment they log in."""

    legal_name = serializers.CharField()
    credit_status = serializers.CharField()
    credit_limit = serializers.CharField()
    outstanding = serializers.CharField()
    available = serializers.CharField()
    payment_terms_days = serializers.IntegerField()
    license_expires_on = serializers.DateField(allow_null=True)
    license_is_valid = serializers.BooleanField()
    overdue_count = serializers.IntegerField()
    overdue_total = serializers.CharField()


class LedgerEntrySerializer(serializers.ModelSerializer):
    amount = MoneySerializerField(read_only=True)
    order_number = serializers.CharField(source="order.number", read_only=True, default=None)
    is_debit = serializers.BooleanField(read_only=True)

    class Meta:
        model = LedgerEntry
        fields = [
            "id",
            "kind",
            "amount",
            "is_debit",
            "order_number",
            "occurred_on",
            "due_on",
            "reference",
            "note",
        ]
        read_only_fields = fields


class InvoiceSerializer(serializers.ModelSerializer):
    subtotal = MoneySerializerField(read_only=True)
    discount_total = MoneySerializerField(read_only=True)
    tax_total = MoneySerializerField(read_only=True)
    total = MoneySerializerField(read_only=True)

    order_number = serializers.CharField(source="order.number", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    days_overdue = serializers.IntegerField(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "number",
            "order_number",
            "issued_on",
            "due_on",
            "subtotal",
            "discount_total",
            "tax_total",
            "total",
            "status",
            "is_overdue",
            "days_overdue",
        ]
        read_only_fields = fields


# ═══════════════════════════════════════════════════════════
#  Admin inputs
# ═══════════════════════════════════════════════════════════


class GrantCreditSerializer(serializers.Serializer):
    limit = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))
    terms_days = serializers.IntegerField(min_value=0, max_value=365)
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class SuspendCreditSerializer(serializers.Serializer):
    #: ⚠️  The reason is mandatory: a customer blocked with no written reason calls
    #:     support, who in turn do not know why they were blocked.
    reason = serializers.CharField(min_length=3, max_length=1000)


class RecordPaymentSerializer(serializers.Serializer):
    # ⚠️  `Decimal`, not `float`, in `min_value`.
    #
    #     A floating `0.01` compared against a decimal makes DRF warn, and the
    #     comparison itself passes through a conversion that loses precision — in a money field.
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    reference = serializers.CharField(required=False, allow_blank=True, max_length=64)
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class CreditCheckSerializer(serializers.Serializer):
    """A pre-check before checkout — so the customer knows before building a cart."""

    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))


class CreditCheckoutSerializer(serializers.Serializer):
    """
    ⚠️  **No `payment_method`** — the endpoint itself is the method.

        Accepting a payment-method field here opens a door to sending "card"
        down the credit path, charging to the account what was paid in cash.
    """

    address_id = serializers.UUIDField(required=False, allow_null=True)
    address = serializers.DictField(required=False)
    shipping_method_code = serializers.CharField(max_length=50, required=False, allow_blank=True)
    customer_note = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate(self, attrs):
        if not attrs.get("address_id") and not attrs.get("address"):
            raise serializers.ValidationError("أرسل `address_id` أو `address`")
        return attrs
