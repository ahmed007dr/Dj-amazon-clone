"""
Coupon contracts.
"""

from rest_framework import serializers

from promotions.models import Coupon, CouponRedemption


class CouponSerializer(serializers.ModelSerializer):
    """
    ⚠️  `usage_count` is **read-only**.

        The server increments the usage counter on every redemption. Allowing it
        to be written means an edit in the panel reopens an exhausted coupon —
        or closes a running one — with no trace in any redemption record.
    """

    usage_count = serializers.IntegerField(read_only=True)
    is_running = serializers.BooleanField(read_only=True)
    is_expired = serializers.BooleanField(read_only=True)
    is_exhausted = serializers.BooleanField(read_only=True)

    class Meta:
        model = Coupon
        fields = [
            "id",
            "code",
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "kind",
            "value",
            "max_discount_amount",
            "min_order_amount",
            "account_types",
            "first_order_only",
            "owner",
            "products",
            "categories",
            "usage_limit",
            "usage_limit_per_user",
            "usage_count",
            "starts_at",
            "ends_at",
            "is_active",
            "is_running",
            "is_expired",
            "is_exhausted",
        ]
        read_only_fields = ["id", "usage_count"]

    def validate_code(self, value: str) -> str:
        """
        ⚠️  Upper-casing happens in the model, and the duplicate check must run
            **on the normalised form**.

            Without that, `summer10` passes alongside `SUMMER10` in validation
            and they then collide on save with a database error rather than a
            field message.
        """
        normalised = value.strip().upper()

        existing = Coupon.objects.filter(code=normalised)
        if self.instance is not None:
            existing = existing.exclude(pk=self.instance.pk)

        if existing.exists():
            raise serializers.ValidationError("هذا الكود مستخدم بالفعل")

        return normalised

    def validate(self, attrs):
        instance = self.instance
        kind = attrs.get("kind", getattr(instance, "kind", None))
        value = attrs.get("value", getattr(instance, "value", None))
        start = attrs.get("starts_at", getattr(instance, "starts_at", None))
        end = attrs.get("ends_at", getattr(instance, "ends_at", None))

        # ⚠️  A rate above 100% makes the order negative — the store pays the customer.
        if kind == "PERCENTAGE" and value is not None and value > 100:
            raise serializers.ValidationError({"value": "النسبة لا تتجاوز ١٠٠٪"})

        # ⚠️  A zero-value discount is not a technical error but a coupon with no effect:
        #     the customer enters it, sees "applied", and nothing changes.
        if kind in ("PERCENTAGE", "FIXED") and value is not None and value <= 0:
            raise serializers.ValidationError({"value": "قيمة الخصم يجب أن تكون أكبر من صفر"})

        if start and end and end <= start:
            raise serializers.ValidationError(
                {"ends_at": "تاريخ الانتهاء قبل البداية — الكوبون لن يعمل أبدًا"}
            )

        return attrs


class CouponRedemptionSerializer(serializers.ModelSerializer):
    """
    ⚠️  A permanent record that survives the order's cancellation — auditing
        needs to know who used what and when.
    """

    coupon_code = serializers.CharField(source="coupon.code", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = CouponRedemption
        fields = [
            "id",
            "coupon",
            "coupon_code",
            "user",
            "user_email",
            "reference_type",
            "reference_id",
            "discount_amount",
            # ⚠️  A cancelled one stays in the log and is marked: the statistics need to
            #     separate a real use from the use of an order that was cancelled.
            "is_cancelled",
            "cancelled_at",
            "created_at",
        ]
        read_only_fields = fields
