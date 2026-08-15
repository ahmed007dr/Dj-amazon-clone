"""
عقود نقطة البيع.

⚠️  **لا مبالغ تدخل من الواجهة إطلاقًا.**

    الكاشير يرسل المنتج والكمية؛ السعر يحسبه `pricing` والإجمالي
    يحسبه الخادم. قبول سعر من الجهاز يعني بيعة يحدّد سعرها من
    يملك الجهاز — وهو أول ما يُستغَل في متجر فعلي.
"""

from decimal import Decimal

from rest_framework import serializers

from pos.models import CashMovement, POSSession, Register


class MoneyField(serializers.DecimalField):
    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 12)
        kwargs.setdefault("decimal_places", 2)
        kwargs.setdefault("coerce_to_string", True)
        super().__init__(**kwargs)


class RegisterSerializer(serializers.ModelSerializer):
    location_code = serializers.CharField(source="location.code", read_only=True)
    has_open_session = serializers.SerializerMethodField()

    class Meta:
        model = Register
        fields = [
            "id",
            "code",
            "name_ar",
            "name_en",
            "location",
            "location_code",
            "is_active",
            "has_open_session",
        ]
        read_only_fields = ["id", "location_code", "has_open_session"]

    def get_has_open_session(self, obj) -> bool:
        return obj.open_session is not None


class CashMovementSerializer(serializers.ModelSerializer):
    amount = MoneyField(read_only=True)

    class Meta:
        model = CashMovement
        fields = [
            "id",
            "kind",
            "amount",
            "reason",
            "reference_type",
            "reference_id",
            "created_at",
        ]
        read_only_fields = fields


class SessionSerializer(serializers.ModelSerializer):
    """
    ⚠️  `expected_cash` و`variance` **لا يُعرضان قبل الإغلاق**.

        عرض المتوقَّع للكاشير قبل أن يعدّ يجعله يعدّ حتى يطابقه —
        فتصير التسوية شكلية والفرق صفرًا دائمًا.
    """

    register_code = serializers.CharField(source="register.code", read_only=True)
    cashier_name = serializers.CharField(source="cashier.full_name", read_only=True)

    opening_float = MoneyField(read_only=True)
    counted_cash = MoneyField(read_only=True)
    expected_cash = serializers.SerializerMethodField()
    variance = serializers.SerializerMethodField()

    class Meta:
        model = POSSession
        fields = [
            "id",
            "number",
            "register",
            "register_code",
            "cashier",
            "cashier_name",
            "status",
            "opened_at",
            "closed_at",
            "opening_float",
            "counted_cash",
            "expected_cash",
            "variance",
            "variance_note",
            "note",
        ]
        read_only_fields = fields

    def get_expected_cash(self, obj) -> str | None:
        return str(obj.expected_cash) if obj.expected_cash is not None else None

    def get_variance(self, obj) -> str | None:
        variance = obj.variance
        return str(variance) if variance is not None else None


# ═══════════════════════════════════════════════════════════
#  المدخلات
# ═══════════════════════════════════════════════════════════


class OpenSessionSerializer(serializers.Serializer):
    register = serializers.UUIDField()
    opening_float = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), default=Decimal("0")
    )


class CloseSessionSerializer(serializers.Serializer):
    """
    ⚠️  `counted_cash` إلزامي بلا قيمة افتراضية.

        الافتراضي (صفر أو المتوقَّع) يسمح بإغلاق بلا عدّ — وهو
        بالضبط ما تمنعه التسوية.
    """

    counted_cash = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0")
    )
    variance_note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class SaleLineSerializer(serializers.Serializer):
    product = serializers.UUIDField()
    variant = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1, max_value=9999)


class SplitPaymentSerializer(serializers.Serializer):
    method = serializers.CharField(max_length=16)
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )


class CheckoutSerializer(serializers.Serializer):
    """
    ⚠️  **بلا حقل إجمالي.** يحسبه الخادم ويقارنه بمجموع الدفعات.
    """

    lines = SaleLineSerializer(many=True)
    payments = SplitPaymentSerializer(many=True)
    customer = serializers.UUIDField(required=False, allow_null=True)
    discount_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), default=Decimal("0")
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("لا أصناف في البيعة")
        return value

    def validate_payments(self, value):
        if not value:
            raise serializers.ValidationError("لا دفعات — البيعة غير مسدَّدة")
        return value


class CashMovementInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["PAY_IN", "PAY_OUT"])
    amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0.01")
    )
    #: ⚠️  السبب إلزامي: نقد يخرج من الدرج بلا سبب هو بالضبط ما
    #:     يجعل فرق الإغلاق غير قابل للتفسير.
    reason = serializers.CharField(min_length=3, max_length=300)


class RefundSerializer(serializers.Serializer):
    order = serializers.UUIDField()
    reason = serializers.CharField(min_length=3, max_length=500)
    cash_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True, min_value=Decimal("0")
    )
