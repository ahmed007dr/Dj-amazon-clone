"""Notifications admin panel."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from core.admin import DeletedListFilter, DomainModelAdmin, LogAdmin
from notifications.models import Notification, NotificationLog, NotificationPreference
from notifications.services import mark_read


@admin.register(Notification)
class NotificationAdmin(DomainModelAdmin):
    list_display = ("created_at", "user", "category", "priority", "title", "is_read", "read_at")
    list_filter = ("category", "priority", "is_read", "created_at", DeletedListFilter)
    list_select_related = ("user",)
    search_fields = ("title", "body", "user__email", "reference_id")
    autocomplete_fields = ("user",)
    date_hierarchy = "created_at"
    actions = ["restore_selected", "mark_read_selected"]
    readonly_fields = ("id", "created_at", "updated_at", "deleted_at", "read_at")

    @admin.action(description=_("تعليم المحدد كمقروء"))
    def mark_read_selected(self, request, queryset):
        count = 0
        for notification in queryset.filter(is_read=False):
            mark_read(notification)
            count += 1
        self.message_user(request, _("تم تعليم %(count)d إشعارًا كمقروء.") % {"count": count})


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(DomainModelAdmin):
    list_display = ("user", "category", "channel", "is_enabled", "is_deleted")
    list_filter = ("category", "channel", "is_enabled", DeletedListFilter)
    list_select_related = ("user",)
    search_fields = ("user__email",)
    autocomplete_fields = ("user",)


@admin.register(NotificationLog)
class NotificationLogAdmin(LogAdmin):
    """The actual delivery attempts — why did the email not arrive?"""

    list_display = (
        "created_at",
        "user",
        "channel",
        "category",
        "template_key",
        "recipient",
        "status",
        "attempts",
    )
    list_filter = ("channel", "category", "status", "created_at")
    list_select_related = ("user",)
    search_fields = ("user__email", "recipient", "template_key", "error_message")
    date_hierarchy = "created_at"
