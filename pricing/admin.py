"""
لوحة التسعير.

⚠️  ما يظهر هنا مدخلات التسعير لا نتيجته. السعر النهائي يحسبه
    `pricing.services` وقت الطلب من القائمة والقاعدة والتجاوز معًا.
"""

from django.contrib import admin

from core.admin import DeletedListFilter, DomainModelAdmin
from pricing.models import PriceList, PriceOverride, PriceRule


class PriceRuleInline(admin.TabularInline):
    model = PriceRule
    extra = 0
    fields = ("product", "variant", "min_quantity", "unit_price", "is_active")
    autocomplete_fields = ("product", "variant")
    show_change_link = True


@admin.register(PriceList)
class PriceListAdmin(DomainModelAdmin):
    list_display = (
        "code",
        "name_ar",
        "kind",
        "priority",
        "is_default",
        "is_active",
        "valid_from",
        "valid_to",
        "is_deleted",
    )
    list_filter = ("kind", "is_default", "is_active", DeletedListFilter)
    search_fields = ("code", "name_ar", "name_en")
    ordering = ("-priority", "code")
    inlines = (PriceRuleInline,)


@admin.register(PriceRule)
class PriceRuleAdmin(DomainModelAdmin):
    list_display = ("price_list", "product", "variant", "min_quantity", "unit_price", "is_active")
    list_filter = ("price_list", "is_active", DeletedListFilter)
    list_select_related = ("price_list", "product", "variant")
    search_fields = ("product__name_ar", "product__sku", "price_list__code")
    autocomplete_fields = ("price_list", "product", "variant")


@admin.register(PriceOverride)
class PriceOverrideAdmin(DomainModelAdmin):
    list_display = (
        "product",
        "variant",
        "price_list",
        "discount_kind",
        "discount_value",
        "starts_at",
        "ends_at",
        "is_active",
    )
    list_filter = ("discount_kind", "is_active", "starts_at", DeletedListFilter)
    list_select_related = ("product", "variant", "price_list")
    search_fields = ("product__name_ar", "product__sku")
    autocomplete_fields = ("product", "variant", "price_list")
    date_hierarchy = "starts_at"
