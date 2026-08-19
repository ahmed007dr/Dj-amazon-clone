"""
The Django admin — an internal operational window, not the product interface.

⚠️  The real admin interface is the SPA on top of `/api/v1/administration/` (ADR-03).
    This panel is a tool for the internal team: diagnosis · auditing · rare manual repair.
    Three rules therefore apply to every `admin.py` file in the project:

      1. **Logs are read-only.** The audit log, stock movements and webhook
         events are written by services, never by hand; allowing them to be
         edited from the panel makes the log itself untrustworthy.

      2. **Soft deletes are shown, not hidden.** The default manager excludes
         `deleted_at` — so if the panel used it, the row would vanish from the
         screen while remaining in the database, the worst possible diagnostic
         state. We therefore read from `all_objects` and add a "Deleted" column and filter.

      3. **Secrets are never displayed.** Gateway credentials and token
         fingerprints are write-only — see `payments/admin.py`.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from core.models import AuditLog, SystemSetting, TaxClass

# ═══════════════════════════════════════════════════════════
#  Panel identity
# ═══════════════════════════════════════════════════════════

admin.site.site_header = _("منصة التجارة الطبية")
admin.site.site_title = _("لوحة التشغيل")
admin.site.index_title = _("النطاقات")


# ═══════════════════════════════════════════════════════════
#  Shared foundations
# ═══════════════════════════════════════════════════════════


class DeletedListFilter(admin.SimpleListFilter):
    """Soft-delete filter — the default shows everything."""

    title = _("الحذف الناعم")
    parameter_name = "deleted"

    def lookups(self, request, model_admin):
        return (("0", _("الحيّ فقط")), ("1", _("المحذوف فقط")))

    def queryset(self, request, queryset):
        if self.value() == "0":
            return queryset.filter(deleted_at__isnull=True)
        if self.value() == "1":
            return queryset.filter(deleted_at__isnull=False)
        return queryset


class SoftDeleteAdminMixin:
    """
    Reads from `all_objects` instead of the default manager.

    ⚠️  A class that adds its own actions must repeat `restore_selected` in
        `actions` — the list is replaced, not merged.
    """

    actions = ["restore_selected"]

    def get_queryset(self, request):
        queryset = self.model.all_objects.get_queryset()
        ordering = self.get_ordering(request)
        if ordering:
            queryset = queryset.order_by(*ordering)
        return queryset

    @admin.display(description=_("محذوف"), boolean=True, ordering="deleted_at")
    def is_deleted(self, obj):
        return obj.deleted_at is not None

    @admin.action(description=_("استرجاع المحذوف ناعمًا"))
    def restore_selected(self, request, queryset):
        count = queryset.filter(deleted_at__isnull=False).update(deleted_at=None)
        self.message_user(request, _("تم استرجاع %(count)d سجلًا.") % {"count": count})


class SlugAdminMixin:
    """
    The slug is generated on creation and then locked.

    Leaving it editable in the panel contradicts `SlugMixin` itself: changing it
    breaks every external link pointing at the entity, which is exactly what the
    mixin was built to prevent.
    """

    def get_readonly_fields(self, request, obj=None):
        fields = tuple(super().get_readonly_fields(request, obj))
        return (*fields, "slug") if obj is not None else fields


class ReadOnlyAdminMixin:
    """View and search only — no add, no change, no delete."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]


class TimeStampedAdmin(admin.ModelAdmin):
    """For `TimeStampedModel` models — no soft delete."""

    readonly_fields = ("created_at", "updated_at")


class DomainModelAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    """The usual base for a `BaseModel` entity."""

    readonly_fields = ("id", "created_at", "updated_at", "deleted_at")


class LogAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    """A log written by services and read here."""

    show_full_result_count = False


class ReadOnlyDomainAdmin(SoftDeleteAdminMixin, ReadOnlyAdminMixin, admin.ModelAdmin):
    """A `BaseModel` entity written by its service alone — shown in full, never edited."""

    actions = []
    show_full_result_count = False


# ═══════════════════════════════════════════════════════════
#  Infrastructure
# ═══════════════════════════════════════════════════════════


@admin.register(AuditLog)
class AuditLogAdmin(LogAdmin):
    list_display = ("created_at", "action", "actor", "object_repr", "content_type", "ip_address")
    list_filter = ("action", "content_type", "created_at")
    list_select_related = ("actor", "content_type")
    search_fields = ("object_repr", "object_id", "actor__email")
    date_hierarchy = "created_at"
    autocomplete_fields = ("actor",)


@admin.register(SystemSetting)
class SystemSettingAdmin(TimeStampedAdmin):
    list_display = ("key", "group", "value_type", "label_ar", "is_editable", "updated_at")
    list_filter = ("group", "value_type", "is_editable")
    search_fields = ("key", "label_ar", "label_en")
    ordering = ("group", "key")

    def has_delete_permission(self, request, obj=None):
        """The keys are read by name from code — deleting one breaks its consumer."""
        return False


@admin.register(TaxClass)
class TaxClassAdmin(DomainModelAdmin):
    list_display = (
        "code",
        "name_ar",
        "rate",
        "is_default",
        "is_active",
        "valid_from",
        "is_deleted",
    )
    list_filter = ("is_active", "is_default", DeletedListFilter)
    search_fields = ("code", "name_ar", "name_en")
    ordering = ("code",)
