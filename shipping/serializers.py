"""Shipping contracts."""

from django.db import transaction
from rest_framework import serializers

from shipping import services
from shipping.governorates import GOVERNORATE_SET, normalize
from shipping.models import (
    Shipment,
    ShipmentEvent,
    ShipmentStatus,
    ShippingMethod,
    ShippingRate,
    ShippingZone,
)


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


# ═══════════════════════════════════════════════════════════
#  Configuration — the admin contracts
# ═══════════════════════════════════════════════════════════
#
# ⚠️  These edit the fee table the checkout quotes from. Every rule below exists
#     because breaking it is silent: the quote keeps answering and the order
#     keeps completing — the wrong fee only surfaces in the margin at the end of
#     the month.


class AdminShippingZoneSerializer(serializers.ModelSerializer):
    """
    A shipping zone, as the admin edits it.

    ⚠️  `code` is **write-once**.

        It is what the seeds, the reports and every operational note refer to.
        Renaming `cairo-giza` after the fact detaches the zone from everything
        that names it — and the row keeps working, so nothing signals the break.
    """

    rate_count = serializers.SerializerMethodField()

    # ⚠️  Declared by hand to **drop the unique validator DRF derives** from the
    #     model's `unique_default_shipping_zone` constraint.
    #
    #     That validator refuses the promotion outright — "a default zone already
    #     exists" — which turns the only thing anyone ever does with this switch
    #     (move the default from one zone to another) into a dead end: the admin
    #     has to find the current default and unset it first, and between the two
    #     saves there is no default at all, so every unassigned governorate
    #     quotes nothing.
    #
    #     The database constraint stays. `create` and `update` below stand the
    #     previous default down inside the same transaction, so two defaults
    #     remain impossible — the check moved, it did not disappear.
    is_default = serializers.BooleanField(required=False)

    class Meta:
        model = ShippingZone
        fields = [
            "id",
            "code",
            "name_ar",
            "name_en",
            "governorates",
            "is_default",
            "is_active",
            "rate_count",
        ]

    def get_rate_count(self, zone) -> int:
        """⚠️  Zero means a zone that quotes nothing at all — visible on the row."""
        return zone.rates.filter(is_active=True).count()

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is not None:
            fields["code"].read_only = True
        return fields

    def validate_governorates(self, value):
        """
        ⚠️  Checked against the reference list **and** against the other zones.

            Free text here is what lands an address in the default zone at the
            highest fee: the match is literal, so "الاسكندرية" and "الإسكندرية"
            are two different governorates as far as the quote is concerned —
            and only one of them appears in anybody's address.
        """
        if not isinstance(value, list):
            raise serializers.ValidationError("المحافظات يجب أن تكون قائمة")

        names = [normalize(str(name)) for name in value]
        names = [name for name in names if name]

        unknown = [name for name in names if name not in GOVERNORATE_SET]
        if unknown:
            joined = "، ".join(unknown)
            raise serializers.ValidationError(
                f"محافظات غير معروفة: {joined} — اختر من القائمة المرجعية"
            )

        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise serializers.ValidationError(f"محافظات مكرّرة: {'، '.join(duplicates)}")

        conflicts = services.zone_conflicts(names, exclude_zone=self.instance)
        if conflicts:
            detail = "، ".join(f"{name} ({code})" for name, code in sorted(conflicts.items()))
            raise serializers.ValidationError(
                f"محافظات مُسندة لمنطقة أخرى: {detail} — "
                "المحافظة في منطقتين تجعل الرسم المحسوب عشوائيًا"
            )

        return names

    def validate(self, attrs):
        """
        ⚠️  The default zone carries **no governorate list of its own**.

            It answers for whatever is not listed elsewhere, so naming
            governorates on it puts them in two places at once — matched by name
            here and by fallback there, at whichever fee happens to be read first.
        """
        current = self.instance
        is_default = attrs.get("is_default", current.is_default if current else False)
        governorates = attrs.get("governorates", current.governorates if current else [])

        if is_default and governorates:
            raise serializers.ValidationError(
                {
                    "governorates": (
                        "المنطقة الافتراضية تغطّي كل محافظة غير مُسندة — "
                        "لا تُسند إليها محافظات بالاسم"
                    )
                }
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        if validated_data.get("is_default"):
            services.stand_down_default_zone()
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        if validated_data.get("is_default"):
            services.stand_down_default_zone(exclude_pk=instance.pk)
        return super().update(instance, validated_data)


class AdminShippingMethodSerializer(serializers.ModelSerializer):
    """
    A shipping method, as the admin edits it.

    ⚠️  `is_pickup` is not a label: `services.quote` forces the fee to zero for
        it and the checkout asks for no address at all. Flipping it on a method
        already in use changes how the orders carrying it behave.
    """

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
            "display_order",
            "is_active",
        ]

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is not None:
            fields["code"].read_only = True
        return fields

    def validate(self, attrs):
        current = self.instance
        minimum = attrs.get("estimated_days_min", current.estimated_days_min if current else 0)
        maximum = attrs.get("estimated_days_max", current.estimated_days_max if current else 0)

        # ⚠️  "من ٤ إلى ٢ أيام" reads as a mistake to the customer — because it is one.
        if maximum < minimum:
            raise serializers.ValidationError({"estimated_days_max": "أكثر مدة لا تقل عن أقل مدة"})
        return attrs


class AdminShippingRateSerializer(serializers.ModelSerializer):
    """
    The fee for a zone × method.

    ⚠️  `free_above` is **per row**, and that is deliberate (see the model).

        A single global "free above 500" imposes Cairo's economics on Upper
        Egypt, where the delivery genuinely costs more — so every free order
        there ships at a loss.
    """

    zone_code = serializers.CharField(source="zone.code", read_only=True)
    zone_name = serializers.CharField(source="zone.name_ar", read_only=True)
    method_code = serializers.CharField(source="method.code", read_only=True)
    method_name = serializers.CharField(source="method.name_ar", read_only=True)
    method_is_pickup = serializers.BooleanField(source="method.is_pickup", read_only=True)

    class Meta:
        model = ShippingRate
        fields = [
            "id",
            "zone",
            "zone_code",
            "zone_name",
            "method",
            "method_code",
            "method_name",
            "method_is_pickup",
            "base_fee",
            "free_above",
            "per_kg_fee",
            "is_active",
        ]

    def validate(self, attrs):
        """
        ⚠️  The pair is unique in the database — but the constraint speaks as a
            500 the admin reads as a broken panel. Naming the existing row turns
            it into "you already priced this; edit that one".
        """
        current = self.instance
        zone = attrs.get("zone", current.zone if current else None)
        method = attrs.get("method", current.method if current else None)

        if zone and method:
            clash = ShippingRate.objects.filter(zone=zone, method=method)
            if current:
                clash = clash.exclude(pk=current.pk)
            if clash.exists():
                raise serializers.ValidationError(
                    {"method": f"توجد تعريفة لـ {zone.code} × {method.code} بالفعل — عدّلها"}
                )

        free_above = attrs.get("free_above", current.free_above if current else None)

        # ⚠️  A threshold at or below zero makes every order free — a real thing
        #     to want, and never a thing to type by accident.
        if free_above is not None and free_above <= 0:
            raise serializers.ValidationError(
                {"free_above": "حدّ الشحن المجاني أكبر من صفر — اتركه فارغًا لإلغاء المجانية"}
            )

        return attrs
