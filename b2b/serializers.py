"""عقود B2B — المبالغ نصًا (ADR-31)."""

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
    ⚠️  حقول الائتمان **للقراءة فقط هنا**.

        قبولها في تحديث الملف يعني أن العميل يرفع حدّه بنفسه
        بطلب واحد. المنح يمرّ بنقطة أدمن مخصّصة تُسجّل من منح ومتى.
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
    """لوحة الحساب — ما يراه العميل التجاري أول ما يدخل."""

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
#  مدخلات الأدمن
# ═══════════════════════════════════════════════════════════


class GrantCreditSerializer(serializers.Serializer):
    limit = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))
    terms_days = serializers.IntegerField(min_value=0, max_value=365)
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class SuspendCreditSerializer(serializers.Serializer):
    #: ⚠️  السبب إلزامي: عميل يُمنَع بلا سبب مكتوب يتصل بالدعم
    #:     الذي لا يعرف بدوره لماذا مُنع.
    reason = serializers.CharField(min_length=3, max_length=1000)


class RecordPaymentSerializer(serializers.Serializer):
    # ⚠️  `Decimal` لا `float` في `min_value`.
    #
    #     `0.01` العائم يُقارَن بقيمة عشرية فيحذّر DRF، والمقارنة
    #     نفسها تمرّ عبر تحويل يفقد الدقة — في حقل مالي.
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    reference = serializers.CharField(required=False, allow_blank=True, max_length=64)
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class CreditCheckSerializer(serializers.Serializer):
    """فحص مسبق قبل الإتمام — ليعرف العميل قبل أن يبني سلة."""

    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))


class CreditCheckoutSerializer(serializers.Serializer):
    """
    ⚠️  **بلا `payment_method`** — النقطة نفسها هي الطريقة.

        قبول حقل طريقة دفع هنا يفتح بابًا لإرسال «بطاقة» إلى مسار
        الآجل، فيُقيَّد على الحساب ما دُفع نقدًا.
    """

    address_id = serializers.UUIDField(required=False, allow_null=True)
    address = serializers.DictField(required=False)
    shipping_method_code = serializers.CharField(max_length=50, required=False, allow_blank=True)
    customer_note = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate(self, attrs):
        if not attrs.get("address_id") and not attrs.get("address"):
            raise serializers.ValidationError("أرسل `address_id` أو `address`")
        return attrs
