"""عقود الموردين — المبالغ نصًا (ADR-31)."""

from decimal import Decimal

from rest_framework import serializers

from core.money import MONEY_DECIMAL_PLACES, MONEY_MAX_DIGITS
from suppliers.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierLedgerEntry,
    SupplierProduct,
)


class MoneySerializerField(serializers.DecimalField):
    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", MONEY_MAX_DIGITS)
        kwargs.setdefault("decimal_places", MONEY_DECIMAL_PLACES)
        kwargs.setdefault("coerce_to_string", True)
        super().__init__(**kwargs)


class SupplierSerializer(serializers.ModelSerializer):
    offer_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Supplier
        fields = [
            "id",
            "code",
            "name_ar",
            "name_en",
            "contact_person",
            "phone",
            "email",
            "address",
            "tax_number",
            "commercial_register",
            "payment_terms_days",
            "lead_time_days",
            "is_active",
            "note",
            "offer_count",
        ]
        read_only_fields = ["id", "offer_count"]


class SupplierProductSerializer(serializers.ModelSerializer):
    unit_cost = MoneySerializerField()
    supplier_name = serializers.CharField(source="supplier.name_ar", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name_ar = serializers.CharField(source="product.name_ar", read_only=True)
    product_name_en = serializers.CharField(source="product.name_en", read_only=True)

    class Meta:
        model = SupplierProduct
        fields = [
            "id",
            "supplier",
            "supplier_name",
            "product",
            "product_sku",
            "product_name_ar",
            "product_name_en",
            "supplier_sku",
            "unit_cost",
            "minimum_order_quantity",
            "lead_time_days",
            "is_preferred",
            "is_active",
        ]
        read_only_fields = [
            "id",
            "supplier_name",
            "product_sku",
            "product_name_ar",
            "product_name_en",
        ]


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    unit_cost = MoneySerializerField(read_only=True)
    total = MoneySerializerField(read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name_ar = serializers.CharField(source="product.name_ar", read_only=True)
    product_name_en = serializers.CharField(source="product.name_en", read_only=True)
    outstanding = serializers.IntegerField(read_only=True)

    class Meta:
        model = PurchaseOrderLine
        fields = [
            "id",
            "product",
            "product_sku",
            "product_name_ar",
            "product_name_en",
            "quantity_ordered",
            "quantity_received",
            "outstanding",
            "unit_cost",
            "total",
        ]
        read_only_fields = fields


class PurchaseOrderSerializer(serializers.ModelSerializer):
    subtotal = MoneySerializerField(read_only=True)
    supplier_name = serializers.CharField(source="supplier.name_ar", read_only=True)
    location_code = serializers.CharField(source="location.code", read_only=True)
    lines = PurchaseOrderLineSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id",
            "number",
            "supplier",
            "supplier_name",
            "location",
            "location_code",
            "status",
            "expected_on",
            "sent_at",
            "received_at",
            "subtotal",
            "note",
            "lines",
        ]
        # ⚠️  الحالة والإجمالي يُشتقّان من الخدمة لا من الواجهة:
        #     أمر «مستلَم» يُرسله العميل كان يُخفي بضاعة لم تصل.
        read_only_fields = [
            "id",
            "number",
            "supplier_name",
            "location_code",
            "status",
            "sent_at",
            "received_at",
            "subtotal",
            "lines",
        ]


class PurchaseOrderLineInputSerializer(serializers.Serializer):
    product = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=999999)


class CreatePurchaseOrderSerializer(serializers.Serializer):
    """⚠️  **بلا سعر** — يُؤخذ من عرض المورّد لا من الواجهة."""

    supplier = serializers.UUIDField()
    location = serializers.UUIDField()
    lines = PurchaseOrderLineInputSerializer(many=True, allow_empty=False)
    expected_on = serializers.DateField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class ReceiveLineSerializer(serializers.Serializer):
    line = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    expires_at = serializers.DateField(required=False, allow_null=True)
    batch_number = serializers.CharField(required=False, allow_blank=True, max_length=64)


class CancelOrderSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=3, max_length=500)


class SupplierLedgerEntrySerializer(serializers.ModelSerializer):
    amount = MoneySerializerField(read_only=True)
    order_number = serializers.CharField(
        source="purchase_order.number", read_only=True, default=None
    )
    increases_debt = serializers.BooleanField(read_only=True)

    class Meta:
        model = SupplierLedgerEntry
        fields = [
            "id",
            "kind",
            "amount",
            "increases_debt",
            "order_number",
            "occurred_on",
            "due_on",
            "reference",
            "note",
        ]
        read_only_fields = fields


class SupplierPaymentSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    reference = serializers.CharField(required=False, allow_blank=True, max_length=64)
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)
