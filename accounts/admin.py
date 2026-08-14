"""
لوحة الهوية.

⚠️  لا نضيف هنا `inline` لملفات الشخصيات (عميل · مدير · طالب).
    `accounts` تحت `customers` و`administration` و`academic` في مخطط
    الطبقات — واستيرادها من هنا يقلب الاتجاه ويوقفه import-linter.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.utils.translation import gettext_lazy as _

from accounts.models import AccountStatusChange, SecurityToken, User, UserSession
from core.admin import LogAdmin


class UserCreateForm(UserCreationForm):
    """البريد هو المعرّف — لا حقل `username` أصلًا."""

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("email",)
        field_classes = {}


class UserEditForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"
        field_classes = {}


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    add_form = UserCreateForm
    form = UserEditForm

    list_display = (
        "email",
        "phone",
        "first_name",
        "last_name",
        "account_type",
        "status",
        "verification_status",
        "is_staff",
        "date_joined",
    )
    list_filter = (
        "account_type",
        "status",
        "verification_status",
        "is_active",
        "is_staff",
        "is_superuser",
        "preferred_language",
        "date_joined",
    )
    search_fields = ("email", "phone", "first_name", "last_name")
    ordering = ("-date_joined",)
    date_hierarchy = "date_joined"
    filter_horizontal = ("groups", "user_permissions")
    readonly_fields = ("id", "date_joined", "last_login", "last_login_at")

    fieldsets = (
        (None, {"fields": ("id", "email", "phone", "password")}),
        (_("البيانات الشخصية"), {"fields": ("first_name", "last_name", "avatar")}),
        (
            _("التصنيف والحالة"),
            {
                "fields": (
                    "account_type",
                    "status",
                    "verification_status",
                    "preferred_language",
                    "email_verified_at",
                    "phone_verified_at",
                )
            },
        ),
        (
            _("الصلاحيات"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("تواريخ"), {"fields": ("last_login", "last_login_at", "date_joined")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "phone", "account_type", "password1", "password2"),
            },
        ),
    )


@admin.register(AccountStatusChange)
class AccountStatusChangeAdmin(LogAdmin):
    list_display = ("changed_at", "user", "from_status", "to_status", "changed_by")
    list_filter = ("from_status", "to_status", "changed_at")
    list_select_related = ("user", "changed_by")
    search_fields = ("user__email", "reason")
    date_hierarchy = "changed_at"


@admin.register(UserSession)
class UserSessionAdmin(LogAdmin):
    list_display = (
        "user",
        "login_at",
        "last_activity",
        "logout_at",
        "revoked_at",
        "device_type",
        "ip_address",
    )
    list_filter = ("device_type", "login_at", "revoked_at")
    list_select_related = ("user",)
    search_fields = ("user__email", "ip_address", "session_key")
    date_hierarchy = "login_at"


@admin.register(SecurityToken)
class SecurityTokenAdmin(LogAdmin):
    """
    ⚠️  `token_hash` غير معروض ولا مبحوث فيه.

        البصمة تكفي لانتحال إعادة تعيين كلمة مرور لو تسرّبت لقطة شاشة —
        ولا حاجة تشغيلية لرؤيتها. المطلوب تشخيصيًا هو الصلاحية والاستهلاك.
    """

    fields = ("user", "purpose", "expires_at", "used_at", "requested_ip", "new_email", "created_at")
    list_display = ("user", "purpose", "created_at", "expires_at", "used_at")
    list_filter = ("purpose", "created_at", "used_at")
    list_select_related = ("user",)
    search_fields = ("user__email",)
    date_hierarchy = "created_at"

    def get_readonly_fields(self, request, obj=None):
        return self.fields
