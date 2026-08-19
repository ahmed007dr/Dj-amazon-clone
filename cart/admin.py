"""
Cart admin panel.

The cart is a transient entity — the panel here is for diagnosis ("why did this
customer not convert?"), not for editing. Any manual edit to the lines bypasses
`cart.services` and the availability and permission checks inside it.
"""

from django.contrib import admin

from cart.models import Cart, CartLine
from core.admin import DeletedListFilter, DomainModelAdmin, ReadOnlyDomainAdmin


class CartLineInline(admin.TabularInline):
    model = CartLine
    extra = 0
    fields = ("product", "variant", "quantity", "created_at")
    readonly_fields = ("product", "variant", "quantity", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Cart)
class CartAdmin(DomainModelAdmin):
    list_display = (
        "id",
        "user",
        "status",
        "coupon_code",
        "shipping_method_code",
        "last_activity_at",
        "converted_at",
    )
    list_filter = ("status", "last_activity_at", DeletedListFilter)
    list_select_related = ("user",)
    search_fields = ("id", "user__email", "session_key", "coupon_code")
    date_hierarchy = "last_activity_at"
    inlines = (CartLineInline,)
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "deleted_at",
        "user",
        "session_key",
        "last_activity_at",
        "converted_at",
    )


@admin.register(CartLine)
class CartLineAdmin(ReadOnlyDomainAdmin):
    list_display = ("cart", "product", "variant", "quantity", "created_at")
    list_select_related = ("cart", "product", "variant")
    search_fields = ("cart__id", "product__name_ar", "product__sku")
    date_hierarchy = "created_at"
