"""
Shipping admin panel.

⚠️  `Shipment.reference_*` is a string reference, not a foreign key — shipping
    does not know about orders. So there is no `autocomplete` on it, and the
    search is textual.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from core.admin import DeletedListFilter, DomainModelAdmin, LogAdmin
from shipping.models import (
    Shipment,
    ShipmentEvent,
    ShippingMethod,
    ShippingRate,
    ShippingZone,
)


class ShippingRateInline(admin.TabularInline):
    model = ShippingRate
    extra = 0
    fields = ("method", "base_fee", "free_above", "per_kg_fee", "is_active")
    autocomplete_fields = ("method",)


class ShipmentEventInline(admin.TabularInline):
    model = ShipmentEvent
    extra = 0
    fields = ("created_at", "status", "location", "note")
    readonly_fields = ("created_at", "status", "location", "note")
    can_delete = False
    show_change_link = False

    def has_add_permission(self, request, obj=None):
        """The timeline is written by the shipping service — it is never fabricated by hand."""
        return False


@admin.register(ShippingZone)
class ShippingZoneAdmin(DomainModelAdmin):
    list_display = ("code", "name_ar", "is_default", "is_active", "is_deleted")
    list_filter = ("is_default", "is_active", DeletedListFilter)
    search_fields = ("code", "name_ar", "name_en")
    ordering = ("code",)
    inlines = (ShippingRateInline,)


@admin.register(ShippingMethod)
class ShippingMethodAdmin(DomainModelAdmin):
    list_display = (
        "code",
        "name_ar",
        "estimated_days_min",
        "estimated_days_max",
        "is_pickup",
        "is_active",
        "is_deleted",
    )
    list_filter = ("is_pickup", "is_active", DeletedListFilter)
    search_fields = ("code", "name_ar", "name_en")


@admin.register(ShippingRate)
class ShippingRateAdmin(DomainModelAdmin):
    list_display = (
        "zone",
        "method",
        "base_fee",
        "free_above",
        "per_kg_fee",
        "is_active",
        "is_deleted",
    )
    list_filter = ("zone", "method", "is_active", DeletedListFilter)
    list_select_related = ("zone", "method")
    search_fields = ("zone__code", "method__code")
    autocomplete_fields = ("zone", "method")


@admin.register(Shipment)
class ShipmentAdmin(DomainModelAdmin):
    list_display = (
        "number",
        "status",
        "method",
        "zone",
        "recipient_name",
        "governorate",
        "shipping_fee",
        "tracking_number",
        "created_at",
    )
    list_filter = ("status", "method", "zone", "governorate", "carrier", "created_at")
    list_select_related = ("method", "zone")
    search_fields = (
        "number",
        "tracking_number",
        "recipient_name",
        "recipient_phone",
        "reference_id",
    )
    autocomplete_fields = ("method", "zone")
    date_hierarchy = "created_at"
    inlines = (ShipmentEventInline,)
    readonly_fields = ("id", "created_at", "updated_at", "deleted_at", "number")

    fieldsets = (
        (None, {"fields": ("id", "number", "status", "method", "zone")}),
        (_("المرجع"), {"fields": ("reference_type", "reference_id")}),
        (
            _("المستلم والعنوان"),
            {
                "fields": (
                    "recipient_name",
                    "recipient_phone",
                    "governorate",
                    "city",
                    "street",
                    "building",
                    "landmark",
                )
            },
        ),
        (_("التكلفة والوزن"), {"fields": ("shipping_fee", "weight_grams")}),
        (
            _("التتبع"),
            {
                "fields": (
                    "carrier",
                    "tracking_number",
                    "shipped_at",
                    "delivered_at",
                    "failure_reason",
                )
            },
        ),
        (_("تواريخ"), {"fields": ("created_at", "updated_at", "deleted_at")}),
    )


@admin.register(ShipmentEvent)
class ShipmentEventAdmin(LogAdmin):
    list_display = ("created_at", "shipment", "status", "location")
    list_filter = ("status", "created_at")
    list_select_related = ("shipment",)
    search_fields = ("shipment__number", "location", "note")
    date_hierarchy = "created_at"
