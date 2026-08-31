"""Inventory contracts."""

from rest_framework import serializers

from core.money import MONEY_DECIMAL_PLACES, MONEY_MAX_DIGITS
from inventory.models import (
    Batch,
    Stock,
    StockAlert,
    StockCount,
    StockCountLine,
    StockLocation,
    StockMovement,
    StockReservation,
)


class StockLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockLocation
        fields = [
            "id",
            "code",
            "name_ar",
            "name_en",
            "kind",
            "governorate",
            "phone",
            "is_default",
            "is_sellable",
            "is_active",
        ]


class UnstockedProductSerializer(serializers.Serializer):
    """
    A product that has **no stock row at all**.

    ⚠️  Not a `Stock` with zero in it — the absence of one.

        `StockSerializer` cannot express this: every field it carries belongs to a
        row that does not exist. Sending zeros in their place would say "received
        and sold out", which is a different fact with a different remedy — that
        one is reordered, this one has never been received.
    """

    id = serializers.UUIDField(read_only=True)
    sku = serializers.CharField(read_only=True)
    name_ar = serializers.CharField(read_only=True)
    name_en = serializers.CharField(read_only=True)
    base_price = serializers.DecimalField(
        max_digits=MONEY_MAX_DIGITS, decimal_places=MONEY_DECIMAL_PLACES, read_only=True
    )
    is_active = serializers.BooleanField(read_only=True)


class StockSerializer(serializers.ModelSerializer):
    """
    A balance for one location.

    ⚠️  `available` is computed, not stored — physical minus reserved, damaged
        and expired. Storing it means two numbers that may diverge.
    """

    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name_ar", read_only=True)
    location_code = serializers.CharField(source="location.code", read_only=True)
    available = serializers.IntegerField(read_only=True)
    needs_reorder = serializers.BooleanField(read_only=True)
    is_critical = serializers.BooleanField(read_only=True)

    class Meta:
        model = Stock
        fields = [
            "id",
            "product",
            "product_sku",
            "product_name",
            "variant",
            "location",
            "location_code",
            "quantity_physical",
            "quantity_reserved",
            "quantity_damaged",
            "quantity_expired",
            "available",
            "reorder_point",
            "critical_point",
            "needs_reorder",
            "is_critical",
            "last_counted_at",
        ]
        read_only_fields = [
            "id",
            "quantity_physical",
            "quantity_reserved",
            "quantity_damaged",
            "quantity_expired",
        ]


class BatchSerializer(serializers.ModelSerializer):
    """
    ⚠️  `unit_cost` is **never exposed publicly**.

    The purchase cost reveals the profit margin — it is shown in admin
    interfaces only.
    """

    product_sku = serializers.CharField(source="product.sku", read_only=True)
    location_code = serializers.CharField(source="location.code", read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    days_to_expiry = serializers.IntegerField(read_only=True)

    class Meta:
        model = Batch
        fields = [
            "id",
            "number",
            "supplier_batch_number",
            "product",
            "product_sku",
            "variant",
            "location",
            "location_code",
            "quantity_received",
            "quantity_remaining",
            "unit_cost",
            "manufactured_at",
            "expires_at",
            "received_at",
            "is_quarantined",
            "is_expired",
            "days_to_expiry",
        ]
        read_only_fields = ["id", "number", "quantity_remaining"]


class StockMovementSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    location_code = serializers.CharField(source="location.code", read_only=True)
    performed_by_email = serializers.EmailField(
        source="performed_by.email", read_only=True, default=None
    )

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "reference",
            "product",
            "product_sku",
            "variant",
            "location",
            "location_code",
            "batch",
            "movement_type",
            "quantity",
            "balance_after",
            "unit_cost",
            "reference_type",
            "reference_id",
            "note",
            "performed_by",
            "performed_by_email",
            "created_at",
        ]
        read_only_fields = fields


class StockAlertSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name_ar", read_only=True)
    location_code = serializers.CharField(source="location.code", read_only=True)

    class Meta:
        model = StockAlert
        fields = [
            "id",
            "alert_type",
            "product",
            "product_sku",
            "product_name",
            "location",
            "location_code",
            "batch",
            "current_value",
            "threshold_value",
            "is_resolved",
            "resolved_at",
            "created_at",
        ]
        read_only_fields = fields


class StockReservationSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)

    class Meta:
        model = StockReservation
        fields = [
            "id",
            "product",
            "product_sku",
            "variant",
            "location",
            "quantity",
            "status",
            "reference_type",
            "reference_id",
            "expires_at",
            "resolved_at",
            "created_at",
        ]
        read_only_fields = fields


# ═══════════════════════════════════════════════════════════
#  Commands
# ═══════════════════════════════════════════════════════════


class ReceiveStockSerializer(serializers.Serializer):
    product = serializers.UUIDField()
    variant = serializers.UUIDField(required=False, allow_null=True)
    location = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)
    unit_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0,
        help_text="إلزامية — بدونها يستحيل حساب الربح لاحقًا",
    )
    expires_at = serializers.DateField(required=False, allow_null=True)
    supplier_batch_number = serializers.CharField(required=False, allow_blank=True, max_length=64)


class AdjustStockSerializer(serializers.Serializer):
    product = serializers.UUIDField()
    variant = serializers.UUIDField(required=False, allow_null=True)
    location = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.IntegerField(help_text="موجب للزيادة · سالب للنقص")
    reason = serializers.CharField(
        min_length=3, max_length=500, help_text="إلزامي — تسوية بلا سبب ثغرة في الجرد"
    )

    def validate_quantity(self, value):
        if value == 0:
            raise serializers.ValidationError("التسوية بصفر بلا معنى")
        return value


class TransferStockSerializer(serializers.Serializer):
    product = serializers.UUIDField()
    variant = serializers.UUIDField(required=False, allow_null=True)
    from_location = serializers.UUIDField()
    to_location = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)

    def validate(self, attrs):
        if attrs["from_location"] == attrs["to_location"]:
            raise serializers.ValidationError({"to_location": "الموقعان متطابقان"})
        return attrs


class MarkDamagedSerializer(serializers.Serializer):
    product = serializers.UUIDField()
    variant = serializers.UUIDField(required=False, allow_null=True)
    location = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(min_length=3, max_length=500)


class AvailabilitySerializer(serializers.Serializer):
    """
    Availability as the store sees it.

    ⚠️  **The exact number is never exposed publicly.**

        Revealing "3 left" is useful commercially, but revealing "847 left"
        gives a competitor your stock volume. The threshold settles it: below
        five, a number; above it, just "in stock".
    """

    product_id = serializers.CharField(read_only=True)
    is_available = serializers.BooleanField(read_only=True)
    is_low = serializers.BooleanField(read_only=True)
    available = serializers.SerializerMethodField()

    def get_available(self, obj) -> int | None:
        return obj.available if obj.available <= 5 else None


# ═══════════════════════════════════════════════════════════
#  Stock counting
# ═══════════════════════════════════════════════════════════


class StockCountLineSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name_ar = serializers.CharField(source="product.name_ar", read_only=True)
    product_name_en = serializers.CharField(source="product.name_en", read_only=True)
    variant_name = serializers.CharField(source="variant.name_ar", read_only=True, default=None)
    #: ⚠️  Computed, not entered — entering it by hand allows a shortfall to be hidden.
    variance = serializers.IntegerField(read_only=True)

    class Meta:
        model = StockCountLine
        fields = [
            "id",
            "product",
            "product_sku",
            "product_name_ar",
            "product_name_en",
            "variant",
            "variant_name",
            "expected_quantity",
            "counted_quantity",
            "variance",
            "note",
        ]
        read_only_fields = [
            "id",
            "product",
            "product_sku",
            "product_name_ar",
            "product_name_en",
            "variant",
            "variant_name",
            # ⚠️  The expected figure is a snapshot from the start time — accepting it
            #     from the frontend lets the counter write whatever balances their discrepancy.
            "expected_quantity",
            "variance",
        ]


class StockCountSerializer(serializers.ModelSerializer):
    location_code = serializers.CharField(source="location.code", read_only=True)
    line_count = serializers.IntegerField(read_only=True, default=0)
    variance_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = StockCount
        fields = [
            "id",
            "reference",
            "location",
            "location_code",
            "status",
            "started_at",
            "completed_at",
            "note",
            "line_count",
            "variance_count",
        ]
        read_only_fields = [
            "id",
            "reference",
            "location_code",
            "status",
            "started_at",
            "completed_at",
            "line_count",
            "variance_count",
        ]


class StockCountDetailSerializer(StockCountSerializer):
    lines = StockCountLineSerializer(many=True, read_only=True)

    class Meta(StockCountSerializer.Meta):
        fields = [*StockCountSerializer.Meta.fields, "lines"]


class OpenCountSerializer(serializers.Serializer):
    location = serializers.UUIDField()
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class RecordCountedSerializer(serializers.Serializer):
    line = serializers.UUIDField()
    counted_quantity = serializers.IntegerField(min_value=0)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class CancelCountSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=3, max_length=500)
