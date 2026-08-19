"""System administrators and their roles admin panel."""

from django.contrib import admin

from administration.models import AdminProfile, AdminRole, AdminRoleAssignment
from core.admin import DeletedListFilter, DomainModelAdmin


class AdminRoleAssignmentInline(admin.TabularInline):
    model = AdminRoleAssignment
    fk_name = "admin"
    extra = 0
    fields = ("role", "from_date", "to_date", "assigned_by")
    readonly_fields = ("from_date",)  # Fixed at assignment time
    autocomplete_fields = ("role", "assigned_by")
    show_change_link = True


@admin.register(AdminProfile)
class AdminProfileAdmin(DomainModelAdmin):
    list_display = ("admin_number", "user", "department", "job_title", "is_owner", "is_deleted")
    list_filter = ("is_owner", "department", DeletedListFilter)
    list_select_related = ("user",)
    search_fields = ("admin_number", "user__email", "department", "job_title")
    autocomplete_fields = ("user",)
    inlines = (AdminRoleAssignmentInline,)


@admin.register(AdminRole)
class AdminRoleAdmin(DomainModelAdmin):
    list_display = ("code", "name_ar", "is_system", "is_active", "is_deleted")
    list_filter = ("is_system", "is_active", DeletedListFilter)
    search_fields = ("code", "name_ar", "name_en")
    filter_horizontal = ("permissions",)
    ordering = ("code",)

    def has_delete_permission(self, request, obj=None):
        """System roles are referenced by code — delete a role and its consumer breaks."""
        if obj is not None and obj.is_system:
            return False
        return super().has_delete_permission(request, obj)


@admin.register(AdminRoleAssignment)
class AdminRoleAssignmentAdmin(DomainModelAdmin):
    list_display = ("admin", "role", "from_date", "to_date", "assigned_by", "is_deleted")
    list_filter = ("role", "from_date", DeletedListFilter)
    list_select_related = ("admin", "role", "assigned_by")
    search_fields = ("admin__admin_number", "admin__user__email", "role__code")
    autocomplete_fields = ("admin", "role", "assigned_by")
