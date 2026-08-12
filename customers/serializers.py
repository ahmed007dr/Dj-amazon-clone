"""عقود الـ API لنطاق العملاء."""

from rest_framework import serializers

from customers.models import (
    CustomerAddress,
    CustomerDocument,
    CustomerProfile,
)


class CustomerAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerAddress
        fields = [
            "id",
            "label",
            "recipient_name",
            "phone",
            "governorate",
            "city",
            "street",
            "building",
            "landmark",
            "is_default",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class CustomerDocumentSerializer(serializers.ModelSerializer):
    """
    ⚠️  `file` للكتابة فقط.

    المسار المباشر لا يُرجَع أبدًا — التقديم عبر رابط موقّع
    بصلاحية زمنية من `download_url`.
    """

    file = serializers.FileField(write_only=True)
    signed_url_endpoint = serializers.SerializerMethodField()

    class Meta:
        model = CustomerDocument
        fields = [
            "id",
            "document_type",
            "file",
            "signed_url_endpoint",
            "status",
            "rejection_reason",
            "expires_at",
            "created_at",
        ]
        read_only_fields = ["id", "status", "rejection_reason", "created_at"]

    def validate_file(self, value):
        from django.core.exceptions import ValidationError as DjangoValidationError

        from core.files import validate_upload

        try:
            validate_upload(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return value

    def get_signed_url_endpoint(self, obj) -> str | None:
        """
        ⚠️  لا يُرجَع رابط التحميل مباشرةً.

        الرابط الموقّع يُطلب عند الحاجة فقط — إدراجه في كل استجابة
        قائمة يعني توليد توقيعات لملفات قد لا تُفتح، وتسريبها في
        سجلات وتخزين مؤقت بلا داعٍ.
        """
        request = self.context.get("request")
        if request is None:
            return None
        from django.urls import reverse

        return request.build_absolute_uri(
            reverse("v1:customers:document-signed-url", args=[obj.pk])
        )


class CustomerProfileSerializer(serializers.ModelSerializer):
    """
    ⚠️  `notes` مستبعد — ملاحظات داخلية لا يراها العميل.
        و`segment` للقراءة: تصنيف تجاري يحدده النظام لا العميل.
    """

    email = serializers.EmailField(source="user.email", read_only=True)
    display_name = serializers.CharField(read_only=True)

    class Meta:
        model = CustomerProfile
        fields = [
            "id",
            "customer_number",
            "email",
            "display_name",
            "display_name_ar",
            "display_name_en",
            "segment",
            "tax_number",
            "commercial_register",
            "accepts_marketing",
            "total_orders",
            "total_spent",
            "first_order_at",
            "last_order_at",
        ]
        read_only_fields = [
            "id",
            "customer_number",
            "segment",
            "total_orders",
            "total_spent",
            "first_order_at",
            "last_order_at",
        ]


class AdminCustomerProfileSerializer(CustomerProfileSerializer):
    """نسخة الأدمن — تُضيف الحقول الداخلية."""

    account_status = serializers.CharField(source="user.status", read_only=True)
    verification_status = serializers.CharField(source="user.verification_status", read_only=True)

    class Meta(CustomerProfileSerializer.Meta):
        fields = [
            *CustomerProfileSerializer.Meta.fields,
            "notes",
            "tax_exempt",
            "account_status",
            "verification_status",
        ]
