"""عقود الشحن."""

from rest_framework import serializers

from shipping.models import Shipment, ShipmentEvent, ShipmentStatus, ShippingMethod


class ShippingQuoteSerializer(serializers.Serializer):
    """
    عرض سعر شحن.

    ⚠️  يُحسب من المصدر عند كل استعلام.

        الواجهة لا ترسل الرسوم ولا يُصدَّق عليها — إرسالها من
        العميل يعني شحنًا مجانيًا بتعديل حقل في المتصفح.
    """

    method_code = serializers.CharField(read_only=True)
    method_name_ar = serializers.CharField(read_only=True)
    method_name_en = serializers.CharField(read_only=True)
    fee = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True, coerce_to_string=True
    )
    is_free = serializers.BooleanField(read_only=True)
    estimated_days_min = serializers.IntegerField(read_only=True)
    estimated_days_max = serializers.IntegerField(read_only=True)
    is_pickup = serializers.BooleanField(read_only=True)


class ShippingMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShippingMethod
        fields = [
            "id",
            "code",
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "estimated_days_min",
            "estimated_days_max",
            "is_pickup",
        ]


class ShipmentEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShipmentEvent
        fields = ["id", "status", "note", "location", "created_at"]
        read_only_fields = fields


class ShipmentSerializer(serializers.ModelSerializer):
    """
    ⚠️  العنوان الكامل والهاتف **لا يُكشفان في التتبع**.

        رقم التتبع يُشارَك مع من يستلم عن العميل؛ عنوانه لا.
        تُعرض المحافظة والمدينة فقط.
    """

    events = ShipmentEventSerializer(many=True, read_only=True)
    method_name = serializers.CharField(source="method.name_ar", read_only=True)

    class Meta:
        model = Shipment
        fields = [
            "id",
            "number",
            "status",
            "method_name",
            "governorate",
            "city",
            "shipping_fee",
            "carrier",
            "tracking_number",
            "shipped_at",
            "delivered_at",
            "events",
        ]
        read_only_fields = fields


class TransitionShipmentSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ShipmentStatus.choices)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)
    location = serializers.CharField(required=False, allow_blank=True, max_length=200)
    tracking_number = serializers.CharField(required=False, allow_blank=True, max_length=100)
