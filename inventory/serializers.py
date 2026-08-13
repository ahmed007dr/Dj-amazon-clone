"""عقود المخزون."""

from rest_framework import serializers

from inventory.models import (
    Batch,
    Stock,
    StockAlert,
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


class StockSerializer(serializers.ModelSerializer):
    """
    رصيد لموقع.

    ⚠️  `available` محسوب لا مُخزَّن — الفعلي ناقص المحجوز والتالف
        والمنتهي. تخزينه يعني رقمين قد يتباعدان.
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
    ⚠️  `unit_cost` **لا يُكشف للعامة**.

    تكلفة الشراء تكشف هامش الربح — تُعرض في واجهات الأدمن فقط.
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
#  الأوامر
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
    التوفر كما يراه المتجر.

    ⚠️  **لا يُكشف الرقم الدقيق للعامة.**

        كشف «متبقٍ ٣ قطع» مفيد تسويقيًا، لكن كشف «متبقٍ ٨٤٧» يعطي
        المنافس حجم مخزونك. العتبة تحسم: تحت الخمسة رقم، وفوقها
        «متوفر» فقط.
    """

    product_id = serializers.CharField(read_only=True)
    is_available = serializers.BooleanField(read_only=True)
    is_low = serializers.BooleanField(read_only=True)
    available = serializers.SerializerMethodField()

    def get_available(self, obj) -> int | None:
        return obj.available if obj.available <= 5 else None
