"""API contracts for the customer domain."""

from rest_framework import serializers

from customers.models import (
    CustomerAddress,
    CustomerDocument,
    CustomerProfile,
    DocumentStatus,
    DocumentType,
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


# ═══════════════════════════════════════════════════════════
#  Admin — reviewing verification documents
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  Everything above is owner-only. These contracts are served to the reviewer
#      alone (`CanManageAcademic`) and are the only place a document is shown
#      next to the person it belongs to.


class AdminDocumentSerializer(serializers.ModelSerializer):
    """
    A document in the review queue — with **who** and **where they study**.

    ⚠️  No file path and no URL.

        The file is fetched through the audited `…/file/` endpoint with the
        reviewer's own token; a link in the list would be a link anyone with the
        response could reuse.

    ⚠️  The student's academic details are read through the account's reverse
        `student_profile` and **not imported**: `customers` and `academic` are
        independent siblings. The view's `select_related` keeps it to one query.
    """

    user = serializers.SerializerMethodField()
    student = serializers.SerializerMethodField()
    reviewed_by_name = serializers.CharField(
        source="reviewed_by.full_name", read_only=True, default=None
    )

    class Meta:
        model = CustomerDocument
        fields = [
            "id",
            "document_type",
            "status",
            "rejection_reason",
            "expires_at",
            "created_at",
            "reviewed_at",
            "reviewed_by_name",
            "user",
            "student",
        ]
        read_only_fields = fields

    def get_user(self, obj) -> dict:
        user = obj.customer.user
        return {
            "id": str(user.pk),
            "name": user.full_name,
            "email": user.email,
            "phone": user.phone,
            "account_type": user.account_type,
            "verification_status": user.verification_status,
        }

    def get_student(self, obj) -> dict | None:
        profile = getattr(obj.customer.user, "student_profile", None)
        if profile is None:
            return None

        department = profile.department
        return {
            "university_name_ar": profile.university.name_ar,
            "university_name_en": profile.university.name_en,
            "faculty_name_ar": profile.faculty.name_ar,
            "faculty_name_en": profile.faculty.name_en,
            "department_name_ar": department.name_ar if department else None,
            "department_name_en": department.name_en if department else None,
            "academic_year": profile.academic_year,
            "student_number": profile.student_number,
            "is_verified": profile.is_verified,
        }


class AdminDocumentFilterSerializer(serializers.Serializer):
    """The queue filters — validated, so a typo is a `400` and not an empty page."""

    status = serializers.ChoiceField(required=False, choices=DocumentStatus.choices)
    document_type = serializers.ChoiceField(required=False, choices=DocumentType.choices)
    search = serializers.CharField(required=False, max_length=100)


class RejectDocumentSerializer(serializers.Serializer):
    """
    ⚠️  The reason is mandatory — the student reads it.

        A rejection with no explanation leaves them re-uploading the same photo.
    """

    reason = serializers.CharField(min_length=3, max_length=1000, trim_whitespace=True)


class BulkApproveDocumentsSerializer(serializers.Serializer):
    #: ⚠️  Capped: one request is one transaction and one email per student.
    ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, max_length=100)
