"""
Inventory admin panel.

⚠️  Quantities are **read and never written** from here.

    Every balance in `Stock` is the result of `StockMovement` movements and
    `StockReservation` reservations. Editing the number directly severs it from
    its movement log, so the stock count becomes inexplicable. Adjustment
    happens through a stock count (`StockCount`) or an explicit movement via
    `inventory.services`.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from core.admin import DeletedListFilter, DomainModelAdmin, LogAdmin, TimeStampedAdmin
from inventory.models import (
    Batch,
    Stock,
    StockAlert,
    StockCount,
    StockCountLine,
    StockLocation,
    StockMovement,
    StockReservation,
)


class StockCountLineInline(admin.TabularInline):
    model = StockCountLine
    extra = 0
    fields = ("product", "variant", "expected_quantity", "counted_quantity", "note")
    readonly_fields = ("expected_quantity",)
    autocomplete_fields = ("product", "variant")


@admin.register(StockLocation)
class StockLocationAdmin(DomainModelAdmin):
    list_display = (
        "code",
        "name_ar",
        "kind",
        "governorate",
        "is_default",
        "is_sellable",
        "is_active",
        "is_deleted",
    )
    list_filter = ("kind", "is_sellable", "is_active", "governorate", DeletedListFilter)
    search_fields = ("code", "name_ar", "name_en", "governorate")
    ordering = ("code",)


@admin.register(Batch)
class BatchAdmin(DomainModelAdmin):
    list_display = (
        "number",
        "product",
        "location",
        "quantity_remaining",
        "quantity_received",
        "expires_at",
        "is_quarantined",
        "is_deleted",
    )
    list_filter = ("is_quarantined", "location", "expires_at", DeletedListFilter)
    list_select_related = ("product", "variant", "location")
    search_fields = ("number", "supplier_batch_number", "product__name_ar", "product__sku")
    autocomplete_fields = ("product", "variant", "location")
    date_hierarchy = "expires_at"


@admin.register(Stock)
class StockAdmin(TimeStampedAdmin):
    list_display = (
        "product",
        "variant",
        "location",
        "quantity_physical",
        "quantity_reserved",
        "quantity_damaged",
        "quantity_expired",
        "reorder_point",
        "critical_point",
        "last_counted_at",
    )
    list_filter = ("location",)
    list_select_related = ("product", "variant", "location")
    search_fields = ("product__name_ar", "product__sku", "location__code")
    autocomplete_fields = ("product", "variant", "location")

    # Thresholds are a reorder policy — set by hand. Balances are the result of movement.
    readonly_fields = (
        "created_at",
        "updated_at",
        "product",
        "variant",
        "location",
        "quantity_physical",
        "quantity_reserved",
        "quantity_damaged",
        "quantity_expired",
        "last_counted_at",
    )

    def has_add_permission(self, request):
        """The balance row is created by the first movement on the product at that location."""
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockMovement)
class StockMovementAdmin(LogAdmin):
    list_display = (
        "created_at",
        "reference",
        "movement_type",
        "product",
        "location",
        "quantity",
        "balance_after",
        "performed_by",
    )
    list_filter = ("movement_type", "location", "created_at")
    list_select_related = ("product", "variant", "location", "batch", "performed_by")
    search_fields = ("reference", "reference_id", "product__name_ar", "product__sku")
    date_hierarchy = "created_at"


@admin.register(StockReservation)
class StockReservationAdmin(DomainModelAdmin):
    list_display = (
        "product",
        "location",
        "quantity",
        "status",
        "reference_type",
        "reference_id",
        "expires_at",
        "resolved_at",
    )
    list_filter = ("status", "location", "expires_at", DeletedListFilter)
    list_select_related = ("product", "variant", "location")
    search_fields = ("product__name_ar", "product__sku", "reference_id")
    autocomplete_fields = ("product", "variant", "location")
    date_hierarchy = "created_at"


@admin.register(StockCount)
class StockCountAdmin(DomainModelAdmin):
    list_display = ("reference", "location", "status", "started_at", "completed_at", "is_deleted")
    list_filter = ("status", "location", DeletedListFilter)
    list_select_related = ("location",)
    search_fields = ("reference", "location__code")
    autocomplete_fields = ("location",)
    inlines = (StockCountLineInline,)
    date_hierarchy = "created_at"


@admin.register(StockCountLine)
class StockCountLineAdmin(TimeStampedAdmin):
    list_display = ("count", "product", "variant", "expected_quantity", "counted_quantity")
    list_filter = ("count__location", "count__status")
    list_select_related = ("count", "product", "variant")
    search_fields = ("count__reference", "product__name_ar", "product__sku")
    autocomplete_fields = ("count", "product", "variant")


@admin.register(StockAlert)
class StockAlertAdmin(DomainModelAdmin):
    list_display = (
        "created_at",
        "alert_type",
        "product",
        "location",
        "current_value",
        "threshold_value",
        "is_resolved",
    )
    list_filter = ("alert_type", "is_resolved", "location", "created_at", DeletedListFilter)
    list_select_related = ("product", "location", "batch")
    search_fields = ("product__name_ar", "product__sku", "location__code")
    autocomplete_fields = ("product", "location", "batch")
    date_hierarchy = "created_at"
    actions = ["restore_selected", "mark_resolved"]

    @admin.action(description=_("تعليم المحدد كمعالَج"))
    def mark_resolved(self, request, queryset):
        from django.utils import timezone

        count = queryset.filter(is_resolved=False).update(
            is_resolved=True, resolved_at=timezone.now()
        )
        self.message_user(request, _("تم إغلاق %(count)d تنبيهًا.") % {"count": count})
