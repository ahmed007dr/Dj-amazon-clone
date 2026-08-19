"""Loyalty contracts — amounts as strings (ADR-31), and content in both languages (ADR-34)."""

from __future__ import annotations

from rest_framework import serializers

from core.money import MONEY_DECIMAL_PLACES, MONEY_MAX_DIGITS
from loyalty.models import (
    LoyaltyProgram,
    PointsEntry,
    Referral,
    ReferralProgram,
    TierLevel,
)


class MoneySerializerField(serializers.DecimalField):
    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", MONEY_MAX_DIGITS)
        kwargs.setdefault("decimal_places", MONEY_DECIMAL_PLACES)
        kwargs.setdefault("coerce_to_string", True)
        super().__init__(**kwargs)


# ═══════════════════════════════════════════════════════════
#  Admin — configuration
# ═══════════════════════════════════════════════════════════


class TierLevelSerializer(serializers.ModelSerializer):
    threshold = MoneySerializerField()

    class Meta:
        model = TierLevel
        fields = [
            "id",
            "program",
            "code",
            "name_ar",
            "name_en",
            "threshold",
            "multiplier",
            "display_order",
        ]
        read_only_fields = ["id"]


class LoyaltyProgramSerializer(serializers.ModelSerializer):
    tiers = TierLevelSerializer(many=True, read_only=True)

    currency_per_point = MoneySerializerField()
    point_value = MoneySerializerField(max_digits=8, decimal_places=4)
    min_order_amount = MoneySerializerField(required=False)

    class Meta:
        model = LoyaltyProgram
        fields = [
            "id",
            "code",
            "name_ar",
            "name_en",
            # ── The switch and targeting ───────────────────
            "is_active",
            "redemption_enabled",
            "account_types",
            "customer_segments",
            # ── Earning rules ──────────────────────────────
            "currency_per_point",
            "point_value",
            "earns_on_tax",
            "earns_on_shipping",
            "min_order_amount",
            "expiry_months",
            "reverse_on_refund",
            "max_redemption_percent",
            "note",
            "tiers",
        ]
        read_only_fields = ["id", "tiers"]

    def validate_account_types(self, value):
        """
        ⚠️  Targeting is validated here, not in the frontend alone.

            A mistyped value (`"student"` instead of `"STUDENT"`) matches
            nobody, so the programme appears enabled and **nobody earns from it**
            — a silent fault that takes days to notice.
        """
        from accounts.models import AccountType

        return _validate_choices(value, AccountType, "نوع حساب")

    def validate_customer_segments(self, value):
        from customers.models import CustomerSegment

        return _validate_choices(value, CustomerSegment, "تصنيف عميل")


def _validate_choices(value, enum, label: str) -> list:
    if not isinstance(value, list):
        raise serializers.ValidationError("القيمة يجب أن تكون قائمة")

    valid = set(enum.values)
    unknown = [item for item in value if item not in valid]
    if unknown:
        raise serializers.ValidationError(f"{label} غير معروف: {'، '.join(map(str, unknown))}")

    # ⚠️  Deduplication preserving order — duplicates do not harm the logic
    #     but they appear twice on screen and look like a fault.
    return list(dict.fromkeys(value))


class ReferralProgramSerializer(serializers.ModelSerializer):
    min_order_amount = MoneySerializerField(required=False)

    class Meta:
        model = ReferralProgram
        fields = [
            "id",
            "code",
            "name_ar",
            "name_en",
            "is_active",
            "account_types",
            "referrer_points",
            "referee_points",
            "max_referrals_per_user",
            "min_order_amount",
        ]
        read_only_fields = ["id"]

    def validate_account_types(self, value):
        from accounts.models import AccountType

        return _validate_choices(value, AccountType, "نوع حساب")


# ═══════════════════════════════════════════════════════════
#  The ledger
# ═══════════════════════════════════════════════════════════


class PointsEntrySerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    signed_points = serializers.IntegerField(read_only=True)
    order_number = serializers.CharField(source="order.number", read_only=True, default=None)

    class Meta:
        model = PointsEntry
        fields = [
            "id",
            "kind",
            "kind_display",
            "points",
            "signed_points",
            "points_remaining",
            "expires_on",
            "reference",
            "note",
            "order_number",
            "created_at",
        ]
        read_only_fields = fields


class AdminPointsEntrySerializer(PointsEntrySerializer):
    """⚠️  The name of whoever recorded the adjustment is shown to the admin alone — never to the customer."""

    customer_name = serializers.CharField(source="customer.display_name_ar", read_only=True)
    recorded_by_name = serializers.CharField(
        source="recorded_by.get_full_name", read_only=True, default=""
    )

    class Meta(PointsEntrySerializer.Meta):
        fields = [*PointsEntrySerializer.Meta.fields, "customer_name", "recorded_by_name"]
        read_only_fields = fields


class ReferralSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    referrer_name = serializers.CharField(source="referrer.get_full_name", read_only=True)
    referee_name = serializers.CharField(source="referee.get_full_name", read_only=True)

    class Meta:
        model = Referral
        fields = [
            "id",
            "status",
            "status_display",
            "referrer_name",
            "referee_name",
            "rewarded_at",
            "rejection_reason",
            "created_at",
        ]
        read_only_fields = fields


# ═══════════════════════════════════════════════════════════
#  Inputs
# ═══════════════════════════════════════════════════════════


class RedemptionInputSerializer(serializers.Serializer):
    points = serializers.IntegerField(min_value=1)
    order_total = MoneySerializerField(min_value=0)


class AdjustmentInputSerializer(serializers.Serializer):
    """⚠️  `points` accepts a negative: a manual withdrawal is a deliberate path."""

    points = serializers.IntegerField()
    reason = serializers.CharField(max_length=500, allow_blank=False)


class ReferralCodeInputSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=16)
