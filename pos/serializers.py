"""
Point-of-sale contracts.

⚠️  **No amounts come in from the frontend at all.**

    The cashier sends the product and the quantity; `pricing` computes the price
    and the server computes the total. Accepting a price from the terminal means
    a sale whose price is set by whoever holds the terminal — the first thing
    exploited in a physical shop.
"""

from decimal import Decimal

from rest_framework import serializers

from catalog.models import Product
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
    ⚠️  `expected_cash` and `variance` are **not shown before closing**.

        Showing the expected figure to the cashier before they count makes them
        count until it matches — so the reconciliation becomes a formality and
        the discrepancy is always zero.
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
#  Inputs
# ═══════════════════════════════════════════════════════════


class OpenSessionSerializer(serializers.Serializer):
    register = serializers.UUIDField()
    opening_float = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=Decimal("0"), default=Decimal("0")
    )


class CloseSessionSerializer(serializers.Serializer):
    """
    ⚠️  `counted_cash` is mandatory with no default.

        A default (zero or the expected figure) allows closing without counting
        — which is exactly what the reconciliation exists to prevent.
    """

    counted_cash = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))
    variance_note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class SaleLineSerializer(serializers.Serializer):
    product = serializers.UUIDField()
    variant = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1, max_value=9999)


class SplitPaymentSerializer(serializers.Serializer):
    method = serializers.CharField(max_length=16)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


class CheckoutSerializer(serializers.Serializer):
    """
    ⚠️  **No total field.** The server computes it and compares it against the sum of the payments.
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


class POSProductSerializer(serializers.ModelSerializer):
    """
    The item as the counter screen needs it.

    ⚠️  **A deliberately lighter payload than `ProductDetailSerializer`.**

        The cashier's screen shows twenty results with every character typed.
        Dragging the description, the images and the full classification into
        each of them makes the search stutter on a tablet — and the cashier
        types faster than it responds.

    ⚠️  And `base_price` is **indicative, not final.**

        The actual price is computed by `pricing` at quote time (tiers ·
        discounts · a tax that may be absent). Showing it here helps identify
        the item, not add up the invoice — and the `/quote/` endpoint is the
        source of the total.
    """

    base_price = MoneyField(read_only=True)

    class Meta:
        model = Product
        fields = ["id", "sku", "barcode", "name_ar", "name_en", "base_price", "kind"]
        read_only_fields = fields


class QuoteSerializer(serializers.Serializer):
    """
    ⚠️  No `payments` — pricing does not need to know how it will be paid.
    """

    lines = SaleLineSerializer(many=True)
    customer = serializers.UUIDField(required=False, allow_null=True)
    discount_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), default=Decimal("0")
    )

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("لا أصناف في البيعة")
        return value


class CashMovementInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["PAY_IN", "PAY_OUT"])
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    #: ⚠️  The reason is mandatory: cash leaving the drawer with no reason is exactly what
    #:     makes a closing discrepancy impossible to explain.
    reason = serializers.CharField(min_length=3, max_length=300)


class RefundSerializer(serializers.Serializer):
    order = serializers.UUIDField()
    reason = serializers.CharField(min_length=3, max_length=500)
    cash_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True, min_value=Decimal("0")
    )
