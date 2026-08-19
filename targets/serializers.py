"""Target contracts."""

from rest_framework import serializers

from targets.models import MonthlyTarget


class MonthlyTargetSerializer(serializers.ModelSerializer):
    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)
    employee_name = serializers.CharField(source="employee.user.full_name", read_only=True)

    class Meta:
        model = MonthlyTarget
        fields = [
            "id",
            "employee",
            "employee_number",
            "employee_name",
            "year",
            "month",
            "target_type",
            "target_value",
            "minimum_achievement_percent",
            "status",
            "note",
            "achieved_value",
            "achievement_percent",
            "closed_at",
        ]
        # ⚠️  The snapshot is read-only: writing it from the frontend means an
        #     achievement declared with no measurement — and a commission built on it.
        read_only_fields = [
            "id",
            "employee_number",
            "employee_name",
            "status",
            "achieved_value",
            "achievement_percent",
            "closed_at",
        ]


class BulkTargetRowSerializer(serializers.Serializer):
    employee = serializers.UUIDField()
    target_value = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=0)
    target_type = serializers.CharField(required=False, max_length=24)
    minimum_achievement_percent = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False
    )
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)


class BulkTargetSerializer(serializers.Serializer):
    year = serializers.IntegerField(min_value=2020, max_value=2100)
    month = serializers.IntegerField(min_value=1, max_value=12)
    rows = BulkTargetRowSerializer(many=True, allow_empty=False)
