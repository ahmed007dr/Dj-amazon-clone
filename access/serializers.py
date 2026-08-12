"""عقود سياسات الوصول."""

from rest_framework import serializers

from access.models import AccessPolicy
from accounts.models import AccountType


class AccessPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = AccessPolicy
        fields = [
            "id",
            "code",
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "level",
            "allowed_account_types",
            "requires_verification",
            "required_permission",
            "denial_message_ar",
            "denial_message_en",
            "is_default",
            "is_active",
        ]
        read_only_fields = ["id"]

    def validate_allowed_account_types(self, value):
        """
        ⚠️  قيمة غير صالحة هنا تعني سياسة لا تنطبق على أحد —
            منتج يختفي عن الجميع بصمت بلا رسالة خطأ.
        """
        if not isinstance(value, list):
            raise serializers.ValidationError("يجب أن تكون قائمة")

        invalid = [item for item in value if item not in AccountType.values]
        if invalid:
            raise serializers.ValidationError(f"أنواع حسابات غير معروفة: {invalid}")

        return value

    def validate_required_permission(self, value):
        if not value:
            return value

        if "." not in value:
            raise serializers.ValidationError("الصيغة المطلوبة: app_label.codename")

        from django.contrib.auth.models import Permission

        app_label, codename = value.split(".", 1)
        if not Permission.objects.filter(
            content_type__app_label=app_label, codename=codename
        ).exists():
            raise serializers.ValidationError("هذه الصلاحية غير موجودة")

        return value
