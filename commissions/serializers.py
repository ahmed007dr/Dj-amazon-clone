"""Commission contracts."""

from rest_framework import serializers

from commissions.models import CommissionRecord, CommissionScheme, CommissionTier


class CommissionTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommissionTier
        fields = ["id", "from_percent", "to_percent", "rate"]


class CommissionSchemeSerializer(serializers.ModelSerializer):
    tiers = CommissionTierSerializer(many=True, read_only=True)
    role_name = serializers.CharField(source="role.name_ar", read_only=True, default=None)

    class Meta:
        model = CommissionScheme
        fields = [
            "id",
            "code",
            "name_ar",
            "name_en",
            "base",
            "role",
            "role_name",
            "is_active",
            "note",
            "tiers",
        ]
        read_only_fields = ["id", "role_name", "tiers"]


class CommissionRecordSerializer(serializers.ModelSerializer):
    """
    ⚠️  **Every field is read-only.**

        The record is a snapshot a payment is built on; accepting an edit to any
        number in it means a commission changed after it was approved.
    """

    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)
    employee_name = serializers.CharField(source="employee.user.full_name", read_only=True)
    scheme_code = serializers.CharField(source="scheme.code", read_only=True)

    class Meta:
        model = CommissionRecord
        fields = [
            "id",
            "employee",
            "employee_number",
            "employee_name",
            "year",
            "month",
            "orders_count",
            "gross_sales",
            "returns_total",
            "net_sales",
            "cost_total",
            "gross_profit",
            "target_value",
            "achieved_value",
            "achievement_percent",
            "scheme_code",
            "base",
            "base_amount",
            "tier_label",
            "rate",
            "amount",
            "status",
            "note",
            "calculated_at",
            "approved_at",
        ]
        read_only_fields = fields


class CommissionDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["APPROVE", "PAY", "REJECT"])
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate(self, attrs):
        if attrs["decision"] == "REJECT" and not attrs.get("reason", "").strip():
            raise serializers.ValidationError({"reason": ["سبب الرفض إلزامي"]})
        return attrs


class CalculateMonthSerializer(serializers.Serializer):
    year = serializers.IntegerField(min_value=2020, max_value=2100)
    month = serializers.IntegerField(min_value=1, max_value=12)
