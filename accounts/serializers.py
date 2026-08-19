"""
API contracts for the identity domain.

⚠️  Input validation and output representation only.
    Business logic lives in `services.py`. (docs/backend/01-ARCHITECTURE.md)
"""

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.models import AccountType, Language, User, UserSession


class UserSerializer(serializers.ModelSerializer):
    """User representation — without any internal or sensitive field."""

    full_name = serializers.CharField(read_only=True)
    is_email_verified = serializers.BooleanField(read_only=True)

    # ── What the user owns ─────────────────────────────────
    #
    # ⚠️  **Without these fields the frontend cannot hide anything.**
    #
    #     It used to know the account type alone, so everyone who entered the panel
    #     saw every link in it — including what they do not own.
    #     Hiding without knowing is impossible.
    #
    # ⚠️  And they are **for display, not for guarding**: the server refuses
    #     regardless of what the screen shows. Hiding a button is not security, and
    #     showing a button that fails when pressed is a bad experience — both are needed together.
    permissions = serializers.SerializerMethodField()
    is_owner = serializers.SerializerMethodField()
    has_admin_profile = serializers.SerializerMethodField()
    has_employee_profile = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "phone",
            "first_name",
            "last_name",
            "full_name",
            "account_type",
            "status",
            "verification_status",
            "preferred_language",
            "is_email_verified",
            "date_joined",
            "permissions",
            "is_owner",
            "has_admin_profile",
            "has_employee_profile",
        ]
        read_only_fields = [
            "id",
            "email",
            "account_type",
            "status",
            "verification_status",
            "date_joined",
            "permissions",
            "is_owner",
            "has_admin_profile",
            "has_employee_profile",
        ]

    def get_permissions(self, obj) -> list[str]:
        """
        ⚠️  `get_all_permissions`, not a read of the role table.

            A role stores its permissions in its own table **and its group**
            together (ADR-53), and `has_perm` reads the group alone. Reading
            from the table would have shown the frontend things the server
            refuses — which is worse than hiding: a button that appears and
            then fails.

        ⚠️  And the owner is returned with no list: their permissions are
            "everything", and sending thousands of strings on every startup
            serves no purpose — `is_owner` is enough.
        """
        if not obj.is_authenticated or obj.is_superuser:
            return []
        return sorted(obj.get_all_permissions())

    def get_is_owner(self, obj) -> bool:
        if obj.is_superuser:
            return True
        profile = getattr(obj, "admin_profile", None)
        return bool(profile and profile.is_owner)

    def get_has_admin_profile(self, obj) -> bool:
        return hasattr(obj, "admin_profile")

    def get_has_employee_profile(self, obj) -> bool:
        profile = getattr(obj, "employee_profile", None)
        return bool(profile and profile.is_active)


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    account_type = serializers.ChoiceField(
        choices=[
            AccountType.STUDENT,
            AccountType.DOCTOR,
            AccountType.PHARMACIST,
        ],
        default=AccountType.STUDENT,
    )
    preferred_language = serializers.ChoiceField(choices=Language.choices, default=Language.AR)

    def validate_email(self, value: str) -> str:
        value = value.lower().strip()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("هذا البريد مسجل بالفعل", code="unique")
        return value

    def validate_password(self, value: str) -> str:
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value

    def validate_phone(self, value: str) -> str:
        value = (value or "").strip()
        if value and User.objects.filter(phone=value).exists():
            raise serializers.ValidationError("هذا الرقم مسجل بالفعل", code="unique")
        return value


class LoginSerializer(serializers.Serializer):
    """
    ⚠️  One failure message for every case.

    Distinguishing "email not registered" from "wrong password" turns the login
    screen into a tool for discovering registered accounts.
    """

    identifier = serializers.CharField(help_text="البريد الإلكتروني أو رقم الهاتف")
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["identifier"],
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError("بيانات الدخول غير صحيحة", code="invalid_credentials")
        attrs["user"] = user
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_new_password(self, value: str) -> str:
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_current_password(self, value: str) -> str:
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("كلمة المرور الحالية غير صحيحة")
        return value

    def validate_new_password(self, value: str) -> str:
        try:
            validate_password(value, self.context["request"].user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages)) from exc
        return value


class VerifyEmailSerializer(serializers.Serializer):
    token = serializers.CharField()


class EmailChangeRequestSerializer(serializers.Serializer):
    """
    ⚠️  The password is required.

    An unattended unlocked device is enough to change the email and then take
    over the account through "forgot password". Requiring it closes that route.
    """

    new_email = serializers.EmailField()
    current_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value: str) -> str:
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("كلمة المرور غير صحيحة")
        return value

    def validate_new_email(self, value: str) -> str:
        value = value.lower().strip()
        user = self.context["request"].user

        if value == user.email.lower():
            raise serializers.ValidationError("هذا هو بريدك الحالي")
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("هذا البريد مسجل بالفعل", code="unique")
        return value


class EmailChangeConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()


class UserSessionSerializer(serializers.ModelSerializer):
    """
    The user's sessions — shown to them so they can end any they do not recognise.

    `session_key` is **never exposed** — anyone who knows it can hijack the session.
    """

    is_current = serializers.SerializerMethodField()

    class Meta:
        model = UserSession
        fields = [
            "id",
            "login_at",
            "last_activity",
            "ip_address",
            "device_type",
            "is_current",
        ]

    def get_is_current(self, obj) -> bool:
        return obj.session_key == self.context.get("current_session_key")


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    user = UserSerializer(read_only=True)
