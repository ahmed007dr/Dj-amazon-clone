"""Shipping contracts."""

from rest_framework import serializers

from shipping.models import Shipment, ShipmentEvent, ShipmentStatus, ShippingMethod


class ShippingQuoteSerializer(serializers.Serializer):
    """
    A shipping quote.

    ⚠️  Computed from the source on every request.

        The frontend does not send the fee and is not trusted for it — sending
        it from the client means free shipping by editing a field in the browser.
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
    ⚠️  The full address and the phone number are **not exposed in tracking**.

        The tracking number is shared with whoever receives on the customer's
        behalf; their address is not. Only the governorate and the city are shown.
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
