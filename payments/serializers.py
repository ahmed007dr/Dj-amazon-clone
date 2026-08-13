"""
عقود الدفع.

⚠️  **بيانات الاعتماد لا تُقرأ عبر أي API — حتى للأدمن.** (ADR-15)

    الحقل للكتابة فقط، والعرض يظهر آخر أربعة محارف مقنّعة. إرجاع
    المفتاح السري «للتأكد منه» يعني أن تسريب جلسة أدمن واحدة يسرّب
    حساب البوابة كله.
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
    ⚠️  `value` للكتابة فقط. `masked_value` هو التمثيل الوحيد المسموح.
    """

    value = serializers.CharField(write_only=True)
    masked_value = serializers.CharField(read_only=True)

    class Meta:
        model = ProviderCredential
        fields = ["id", "key", "value", "masked_value", "is_sandbox"]


class PaymentProviderSerializer(serializers.ModelSerializer):
    """
    بوابة دفع كما يراها الأدمن.

    ⚠️  `is_active` هو مفتاح التشغيل والإيقاف — تغييره يسري فورًا
        بلا إعادة نشر، وهو جوهر المتطلب.
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
        """أسماء المفاتيح المضبوطة — لا قيمها."""
        return list(obj.credentials.filter(is_sandbox=obj.is_sandbox).values_list("key", flat=True))

    def get_is_configured(self, obj) -> bool:
        return obj.credentials.filter(is_sandbox=obj.is_sandbox).exists()

    def get_adapter_exists(self, obj) -> bool:
        """
        ⚠️  بوابة بمحوّل غير موجود تفشل عند أول محاولة دفع.

            كشفها في الاستجابة يجعل الأدمن يرى الخطأ في الشاشة لا
            في شكوى عميل.
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
        ⚠️  بوابة مفعّلة بلا بيانات اعتماد تفشل عند أول عملية.

            المنع هنا يجعل الفشل ظاهرًا وقت الضبط لا وقت الشراء.
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


#: محوّلات لا تحتاج بيانات اعتماد — الدفع يتم خارج أي بوابة
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
    إعادة ترتيب الأولوية.

    ⚠️  الترتيب يحدد **أي بوابة تُجرَّب أولًا** حين تصلح أكثر من
        واحدة لنفس العملية.
    """

    order = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, max_length=50)


class PaymentMethodOptionSerializer(serializers.Serializer):
    """طريقة دفع متاحة — كما يراها العميل عند إتمام الشراء."""

    method = serializers.CharField(read_only=True)
    label_ar = serializers.CharField(read_only=True)
    label_en = serializers.CharField(read_only=True)
    provider_code = serializers.CharField(read_only=True)
    provider_name_ar = serializers.CharField(read_only=True)
    provider_name_en = serializers.CharField(read_only=True)
    requires_redirect = serializers.BooleanField(read_only=True)


class PaymentTransactionSerializer(serializers.ModelSerializer):
    """
    ⚠️  `provider_response` **مستبعد**.

        قد يحمل بيانات بطاقة جزئية أو رموز داخلية من البوابة —
        إرجاعه يسرّب ما لا لزوم له.
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
