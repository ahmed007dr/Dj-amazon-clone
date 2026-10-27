"""
Employees admin panel.

⚠️  Saving an `EmployeeProfile` here fires the same `post_save` signal as the API,
    so choosing a role in this form puts the user in that role's Django group — the
    panel is a second door to the same service, not a way around it.

⚠️  `EmployeeRole.permissions` is edited here too, and saving the role re-synchronises
    its Django group (`services.sync_role_permissions`) — the group is what actually
    confers the permissions, so a role saved without that step would look configured
    while every `has_perm` check still failed.
"""

from django.contrib import admin

from core.admin import DeletedListFilter, DomainModelAdmin
from employees import services
from employees.models import EmployeeProfile, EmployeeRole


@admin.register(EmployeeRole)
class EmployeeRoleAdmin(DomainModelAdmin):
    list_display = ("code", "name_ar", "name_en", "kind", "is_active", "is_deleted")
    list_filter = ("kind", "is_active", DeletedListFilter)
    search_fields = ("code", "name_ar", "name_en")
    filter_horizontal = ("permissions",)
    readonly_fields = (*DomainModelAdmin.readonly_fields, "group")
    ordering = ("name_ar",)

    def save_related(self, request, form, formsets, change):
        # ⚠️  After the many-to-many is saved, not in `save_model`: the permissions
        #     are written by `super().save_related`, and syncing earlier copies the
        #     previous set into the group.
        super().save_related(request, form, formsets, change)
        services.sync_role_permissions(form.instance)


@admin.register(EmployeeProfile)
class EmployeeProfileAdmin(DomainModelAdmin):
    list_display = (
        "employee_number",
        "user",
        "role",
        "manager",
        "phone_extension",
        "is_active",
        "is_deleted",
    )
    list_filter = ("role", "is_active", DeletedListFilter)
    list_select_related = ("user", "role", "manager__user")
    search_fields = ("employee_number", "user__email", "user__first_name", "user__last_name")
    autocomplete_fields = ("user", "manager")

