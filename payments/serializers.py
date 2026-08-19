"""
Payment contracts.

⚠️  **Credentials are never read through any API — not even by the admin.** (ADR-15)

    The field is write-only, and the display shows the last four characters
    masked. Returning the secret key "to check it" means one leaked admin
    session leaks the entire gateway account.
"""

from rest_framework import serializers

from payments.adapters import available_adapters
from payments.models import (
    PaymentMethodKind,
    PaymentProvider,
    PaymentTransaction,
    ProviderCredential,
    Refund,
)


class MoneyField(serializers.DecimalField):
    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 12)
        kwargs.setdefault("decimal_places", 2)
        kwargs.setdefault("coerce_to_string", True)
        super().__init__(**kwargs)


class ProviderCredentialSerializer(serializers.ModelSerializer):
    """
    ⚠️  `value` is write-only. `masked_value` is the only permitted representation.
    """

    value = serializers.CharField(write_only=True)
    masked_value = serializers.CharField(read_only=True)

    class Meta:
        model = ProviderCredential
        fields = ["id", "key", "value", "masked_value", "is_sandbox"]


class PaymentProviderSerializer(serializers.ModelSerializer):
    """
    A payment gateway as the admin sees it.

    ⚠️  `is_active` is the on/off switch — changing it takes effect immediately
        with no redeployment, and that is the heart of the requirement.
    """

    credential_keys = serializers.SerializerMethodField()
    is_configured = serializers.SerializerMethodField()
    adapter_exists = serializers.SerializerMethodField()

    class Meta:
        model = PaymentProvider
        fields = [
            "id",
            "code",
            "name_ar",
            "name_en",
            "adapter_key",
            "adapter_exists",
            "supported_methods",
            "supported_currencies",
            "supported_channels",
            "min_amount",
            "max_amount",
            "priority",
            "is_sandbox",
            "is_active",
            "is_configured",
            "credential_keys",
        ]
        read_only_fields = ["id"]

    def get_credential_keys(self, obj) -> list:
        """The names of the configured keys — not their values."""
        return list(obj.credentials.filter(is_sandbox=obj.is_sandbox).values_list("key", flat=True))

    def get_is_configured(self, obj) -> bool:
        return obj.credentials.filter(is_sandbox=obj.is_sandbox).exists()

    def get_adapter_exists(self, obj) -> bool:
        """
        ⚠️  A gateway with a nonexistent adapter fails on the first payment attempt.

            Surfacing it in the response makes the admin see the error on the
            screen rather than in a customer complaint.
        """
        return obj.adapter_key in available_adapters()

    def validate_adapter_key(self, value):
        if value not in available_adapters():
            raise serializers.ValidationError(
                f"محوّل غير معروف. المتاح: {', '.join(available_adapters())}"
            )
        return value

    def validate_supported_methods(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("يجب أن تكون قائمة")

        invalid = [m for m in value if m not in PaymentMethodKind.values]
        if invalid:
            raise serializers.ValidationError(f"طرق دفع غير معروفة: {invalid}")
        return value

    def validate(self, attrs):
        """
        ⚠️  A gateway enabled with no credentials fails on the first operation.

            Blocking it here makes the failure visible at configuration time
            rather than at purchase time.
        """
        instance = self.instance
        is_active = attrs.get("is_active", getattr(instance, "is_active", False))
        is_sandbox = attrs.get("is_sandbox", getattr(instance, "is_sandbox", True))

        if is_active and instance is not None:
            adapter_key = attrs.get("adapter_key", instance.adapter_key)
            needs_credentials = adapter_key not in _CREDENTIAL_FREE_ADAPTERS

            if (
                needs_credentials
                and not instance.credentials.filter(is_sandbox=is_sandbox).exists()
            ):
                raise serializers.ValidationError(
                    {
                        "is_active": (
                            "لا يمكن تفعيل بوابة بلا بيانات اعتماد — "
                            f"أضِفها أولًا لوضع {'التجريب' if is_sandbox else 'الإنتاج'}"
                        )
                    }
                )

        return attrs


#: Adapters needing no credentials — the payment happens outside any gateway
_CREDENTIAL_FREE_ADAPTERS = {"cash_on_delivery", "cash", "bank_transfer"}


class ToggleProviderSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=300,
        help_text="يُسجَّل في سجل التدقيق",
    )


class ReorderProvidersSerializer(serializers.Serializer):
    """
    Reordering the priority.

    ⚠️  The order determines **which gateway is tried first** when more than one
        suits the same operation.
    """

    order = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, max_length=50)


class PaymentMethodOptionSerializer(serializers.Serializer):
    """An available payment method — as the customer sees it at checkout."""

    method = serializers.CharField(read_only=True)
    label_ar = serializers.CharField(read_only=True)
    label_en = serializers.CharField(read_only=True)
    provider_code = serializers.CharField(read_only=True)
    provider_name_ar = serializers.CharField(read_only=True)
    provider_name_en = serializers.CharField(read_only=True)
    requires_redirect = serializers.BooleanField(read_only=True)


class PaymentTransactionSerializer(serializers.ModelSerializer):
    """
    ⚠️  `provider_response` is **excluded**.

        It may carry partial card data or internal gateway codes — returning it
        leaks what serves no purpose.
    """

    provider_code = serializers.CharField(source="provider.code", read_only=True)
    refunded_amount = MoneyField(read_only=True)
    refundable_amount = MoneyField(read_only=True)

    class Meta:
        model = PaymentTransaction
        fields = [
            "id",
            "reference",
            "provider",
            "provider_code",
            "method",
            "amount",
            "currency",
            "status",
            "reference_type",
            "reference_id",
            "provider_reference",
            "failure_code",
            "failure_message",
            "refunded_amount",
            "refundable_amount",
            "authorized_at",
            "captured_at",
            "created_at",
        ]
        read_only_fields = fields


class RefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = Refund
        fields = [
            "id",
            "reference",
            "transaction",
            "amount",
            "reason",
            "status",
            "provider_reference",
            "completed_at",
            "created_at",
        ]
        read_only_fields = fields


class CreateRefundSerializer(serializers.Serializer):
    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        allow_null=True,
        help_text="فارغ = استرداد كامل المتبقي",
    )
    reason = serializers.CharField(min_length=3, max_length=500)
