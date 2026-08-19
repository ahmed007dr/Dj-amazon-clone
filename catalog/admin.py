"""
Catalogue admin panel.

⚠️  Domain boundaries apply to the panel exactly as they apply to the models: no
    quantity here (inventory), no final price (pricing), no average rating
    (reviews). `base_price` is the base list price, not what the customer pays.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from catalog.models import Brand, Category, Manufacturer, Product, ProductImage, ProductVariant
from core.admin import DeletedListFilter, DomainModelAdmin, SlugAdminMixin


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0
    fields = ("image", "alt_text_ar", "alt_text_en", "display_order", "is_primary")


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 0
    fields = ("sku", "name_ar", "attributes", "price_adjustment", "display_order", "is_active")
    show_change_link = True


@admin.register(Category)
class CategoryAdmin(SlugAdminMixin, DomainModelAdmin):
    list_display = (
        "name_ar",
        "parent",
        "path",
        "depth",
        "display_order",
        "is_active",
        "show_in_menu",
        "is_deleted",
    )
    list_filter = ("is_active", "show_in_menu", "depth", DeletedListFilter)
    list_select_related = ("parent",)
    search_fields = ("name_ar", "name_en", "slug", "path")
    autocomplete_fields = ("parent",)

    # ⚠️  `path` and `depth` are derived from the parent — the service computes them on save.
    readonly_fields = ("id", "created_at", "updated_at", "deleted_at", "path", "depth")

    fieldsets = (
        (None, {"fields": ("id", "name_ar", "name_en", "slug", "parent")}),
        (_("الوصف والعرض"), {"fields": ("description_ar", "description_en", "image", "icon")}),
        (_("الشجرة"), {"fields": ("path", "depth", "display_order")}),
        (_("الحالة"), {"fields": ("is_active", "show_in_menu")}),
        (
            _("تحسين الظهور"),
            {
                "classes": ("collapse",),
                "fields": (
                    "meta_title_ar",
                    "meta_title_en",
                    "meta_description_ar",
                    "meta_description_en",
                ),
            },
        ),
        (_("تواريخ"), {"fields": ("created_at", "updated_at", "deleted_at")}),
    )


@admin.register(Manufacturer)
class ManufacturerAdmin(SlugAdminMixin, DomainModelAdmin):
    list_display = ("name_ar", "country", "registration_number", "is_active", "is_deleted")
    list_filter = ("country", "is_active", DeletedListFilter)
    search_fields = ("name_ar", "name_en", "registration_number", "slug")
    ordering = ("name_ar",)


@admin.register(Brand)
class BrandAdmin(SlugAdminMixin, DomainModelAdmin):
    list_display = (
        "name_ar",
        "manufacturer",
        "display_order",
        "is_featured",
        "is_active",
        "is_deleted",
    )
    list_filter = ("is_featured", "is_active", "manufacturer", DeletedListFilter)
    list_select_related = ("manufacturer",)
    search_fields = ("name_ar", "name_en", "slug", "manufacturer__name_ar")
    autocomplete_fields = ("manufacturer",)


@admin.register(Product)
class ProductAdmin(SlugAdminMixin, DomainModelAdmin):
    list_display = (
        "sku",
        "name_ar",
        "category",
        "brand",
        "kind",
        "base_price",
        "regulatory_class",
        "requires_prescription",
        "is_active",
        "is_deleted",
    )
    list_filter = (
        "kind",
        "regulatory_class",
        "requires_prescription",
        "is_active",
        "is_featured",
        "dosage_form",
        "storage_condition",
        "category",
        DeletedListFilter,
    )
    list_select_related = ("category", "brand", "manufacturer")
    search_fields = (
        "sku",
        "barcode",
        "name_ar",
        "name_en",
        "slug",
        "active_ingredient_ar",
        "active_ingredient_en",
        "registration_number",
    )
    autocomplete_fields = ("category", "brand", "manufacturer", "access_policy", "tax_class")
    date_hierarchy = "created_at"
    inlines = (ProductImageInline, ProductVariantInline)
    list_per_page = 50

    fieldsets = (
        (None, {"fields": ("id", "name_ar", "name_en", "slug", "sku", "barcode", "kind")}),
        (
            _("الوصف"),
            {
                "fields": (
                    "short_description_ar",
                    "short_description_en",
                    "description_ar",
                    "description_en",
                )
            },
        ),
        (
            _("التصنيف والانتماء"),
            {"fields": ("category", "brand", "manufacturer", "access_policy", "tax_class")},
        ),
        (_("السعر الأساس"), {"fields": ("base_price",)}),
        (
            _("الخصائص التنظيمية والدوائية"),
            {
                "fields": (
                    "regulatory_class",
                    "requires_prescription",
                    "registration_number",
                    "active_ingredient_ar",
                    "active_ingredient_en",
                    "strength",
                    "dosage_form",
                    "pack_size",
                    "storage_condition",
                    "weight_grams",
                )
            },
        ),
        (_("النشر"), {"fields": ("is_active", "is_featured", "published_at")}),
        (
            _("تحسين الظهور"),
            {
                "classes": ("collapse",),
                "fields": (
                    "meta_title_ar",
                    "meta_title_en",
                    "meta_description_ar",
                    "meta_description_en",
                ),
            },
        ),
        (_("تواريخ"), {"fields": ("created_at", "updated_at", "deleted_at")}),
    )


@admin.register(ProductImage)
class ProductImageAdmin(DomainModelAdmin):
    list_display = ("product", "image", "is_primary", "display_order", "is_deleted")
    list_filter = ("is_primary", DeletedListFilter)
    list_select_related = ("product",)
    search_fields = ("product__name_ar", "product__sku", "alt_text_ar")
    autocomplete_fields = ("product",)


@admin.register(ProductVariant)
class ProductVariantAdmin(DomainModelAdmin):
    list_display = ("sku", "product", "name_ar", "price_adjustment", "is_active", "is_deleted")
    list_filter = ("is_active", DeletedListFilter)
    list_select_related = ("product",)
    search_fields = ("sku", "barcode", "name_ar", "name_en", "product__name_ar", "product__sku")
    autocomplete_fields = ("product",)
