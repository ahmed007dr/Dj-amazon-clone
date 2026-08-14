"""لوحة سياسات الوصول."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from access.models import AccessPolicy
from core.admin import DeletedListFilter, DomainModelAdmin


@admin.register(AccessPolicy)
class AccessPolicyAdmin(DomainModelAdmin):
    list_display = (
        "code",
        "name_ar",
        "level",
        "requires_verification",
        "is_default",
        "is_active",
        "is_deleted",
    )
    list_filter = ("level", "requires_verification", "is_default", "is_active", DeletedListFilter)
    search_fields = ("code", "name_ar", "name_en", "required_permission")
    ordering = ("level", "code")

    fieldsets = (
        (None, {"fields": ("id", "code", "name_ar", "name_en", "level")}),
        (_("الوصف"), {"fields": ("description_ar", "description_en")}),
        (
            _("الشروط"),
            {
                "fields": (
                    "allowed_account_types",
                    "requires_verification",
                    "required_permission",
                )
            },
        ),
        (_("رسالة المنع"), {"fields": ("denial_message_ar", "denial_message_en")}),
        (_("الحالة"), {"fields": ("is_default", "is_active")}),
        (_("تواريخ"), {"fields": ("created_at", "updated_at", "deleted_at")}),
    )
