"""API contracts for the customer domain."""

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
    ⚠️  `file` is write-only.

    The direct path is never returned — serving happens through a time-limited
    signed URL from `download_url`.
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
        ⚠️  The download URL is not returned directly.

        The signed URL is requested only when needed — including it in every
        list response means generating signatures for files that may never be
        opened, and leaking them into logs and caches for no reason.
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
    ⚠️  `notes` is excluded — internal notes the customer never sees.
        And `segment` is read-only: a commercial classification the system sets, not the customer.
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
    """The admin version — it adds the internal fields."""

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
