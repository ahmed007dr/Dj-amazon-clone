from django.contrib import admin

from analytics.models import TrafficBucket


@admin.register(TrafficBucket)
class TrafficBucketAdmin(admin.ModelAdmin):
    """⚠️  للقراءة وحدها — رقم مجمَّع يُحرَّر بيدٍ يفقد معناه."""

    list_display = ("bucket_start", "device_type", "requests", "guest_visitors", "known_visitors")
    list_filter = ("device_type",)
    date_hierarchy = "bucket_start"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
