"""
عقود الـ API لنطاق الهوية.

⚠️  تحقق المدخلات وتمثيل المخرجات فقط.
    منطق العمل في `services.py`. (docs/backend/01-ARCHITECTURE.md)
"""

from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from accounts.models import AccountType, Language, User, UserSession


class UserSerializer(serializers.ModelSerializer):
    """تمثيل المستخدم — بلا أي حقل داخلي أو حساس."""

    full_name = serializers.CharField(read_only=True)
    is_email_verified = serializers.BooleanField(read_only=True)

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
        ]
        read_only_fields = [
            "id",
            "email",
            "account_type",
            "status",
            "verification_status",
            "date_joined",
        ]


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
    ⚠️  رسالة فشل واحدة لكل الحالات.

    التمييز بين «بريد غير مسجل» و«كلمة مرور خاطئة» يحوّل شاشة
    الدخول إلى أداة لكشف الحسابات المسجلة.
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
    ⚠️  كلمة المرور مطلوبة.

    جهاز مفتوح بلا صاحبه يكفي لتغيير البريد ثم الاستيلاء على
    الحساب عبر «نسيت كلمة المرور». طلبها يقطع هذا الطريق.
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
    جلسات المستخدم — يراها هو ليُنهي ما لا يعرفه.

    `session_key` **لا يُكشف** — من يعرفه يستطيع انتحال الجلسة.
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
