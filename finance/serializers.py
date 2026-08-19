"""
Finance contracts.

⚠️  Amounts are sent **as strings**, not numbers (ADR-31) — `JSON.parse`
    converts the number to a `double`, so precision is lost at the first addition.
"""

from rest_framework import serializers

from core.money import MONEY_DECIMAL_PLACES, MONEY_MAX_DIGITS
from finance.models import Expense, ExpenseCategory, ExpenseStatus, FiscalPeriod


class MoneySerializerField(serializers.DecimalField):
    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", MONEY_MAX_DIGITS)
        kwargs.setdefault("decimal_places", MONEY_DECIMAL_PLACES)
        kwargs.setdefault("coerce_to_string", True)
        super().__init__(**kwargs)


class ExpenseCategorySerializer(serializers.ModelSerializer):
    expense_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ExpenseCategory
        fields = [
            "id",
            "code",
            "parent",
            "name_ar",
            "name_en",
            "is_active",
            "display_order",
            "expense_count",
        ]
        read_only_fields = ["id", "expense_count"]


class ExpenseSerializer(serializers.ModelSerializer):
    amount = MoneySerializerField()

    category_name_ar = serializers.CharField(source="category.name_ar", read_only=True)
    category_name_en = serializers.CharField(source="category.name_en", read_only=True)
    entered_by_email = serializers.EmailField(source="entered_by.email", read_only=True)
    approved_by_email = serializers.EmailField(
        source="approved_by.email", read_only=True, default=None
    )

    class Meta:
        model = Expense
        fields = [
            "id",
            "category",
            "category_name_ar",
            "category_name_en",
            "amount",
            "incurred_on",
            "vendor_name",
            "reference",
            "attachment",
            "payment_mean",
            "status",
            "entered_by_email",
            "approved_by_email",
            "approved_at",
            "rejection_reason",
            "note",
            "created_at",
        ]
        # ⚠️  The status and the approver are **read-only**.
        #
        #     Accepting them at creation lets whoever enters an expense send
        #     `status="APPROVED"` and approve their own — which drops the entire
        #     meaning of the approval step with no error showing.
        read_only_fields = [
            "id",
            "status",
            "entered_by_email",
            "approved_by_email",
            "approved_at",
            "rejection_reason",
            "created_at",
        ]

    def validate_category(self, value):
        if not value.is_active:
            raise serializers.ValidationError("بند غير مفعّل")
        return value


class ExpenseDecisionSerializer(serializers.Serializer):
    """Approve or reject."""

    decision = serializers.ChoiceField(choices=["APPROVE", "REJECT"])
    #: ⚠️  The reason is mandatory on rejection — checked in `validate` rather than
    #:     on the field, because it is not required on approval.
    reason = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate(self, attrs):
        if attrs["decision"] == "REJECT" and not attrs.get("reason", "").strip():
            raise serializers.ValidationError({"reason": ["سبب الرفض إلزامي"]})
        return attrs


class FiscalPeriodSerializer(serializers.ModelSerializer):
    closed_by_email = serializers.EmailField(source="closed_by.email", read_only=True, default=None)

    class Meta:
        model = FiscalPeriod
        fields = ["year", "month", "is_closed", "closed_at", "closed_by_email", "note"]
        read_only_fields = ["is_closed", "closed_at", "closed_by_email"]


class ClosePeriodSerializer(serializers.Serializer):
    year = serializers.IntegerField(min_value=2020, max_value=2100)
    month = serializers.IntegerField(min_value=1, max_value=12)
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class PendingExpenseFilter(serializers.Serializer):
    """Expense list filters."""

    status = serializers.ChoiceField(choices=ExpenseStatus.choices, required=False)
    category = serializers.UUIDField(required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
