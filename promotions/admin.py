"""لوحة الكوبونات."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from core.admin import DeletedListFilter, DomainModelAdmin, LogAdmin
from promotions.models import Coupon, CouponRedemption


@admin.register(Coupon)
class CouponAdmin(DomainModelAdmin):
    list_display = (
        "code",
        "name_ar",
        "kind",
        "value",
        "usage_count",
        "usage_limit",
        "starts_at",
        "ends_at",
        "is_active",
    )
    list_filter = ("kind", "is_active", "first_order_only", "starts_at", DeletedListFilter)
    search_fields = ("code", "name_ar", "name_en")
    filter_horizontal = ("products", "categories")
    date_hierarchy = "starts_at"

    # ⚠️  العدّاد يزيده الاستهلاك داخل معاملة الطلب — تعديله يدويًا
    #     يفتح الكوبون لاستعمال زائد عن حده.
    readonly_fields = ("id", "created_at", "updated_at", "deleted_at", "usage_count")

    fieldsets = (
        (None, {"fields": ("id", "code", "name_ar", "name_en", "is_active")}),
        (_("الوصف"), {"fields": ("description_ar", "description_en")}),
        (_("قيمة الخصم"), {"fields": ("kind", "value", "max_discount_amount")}),
        (
            _("شروط الاستحقاق"),
            {"fields": ("min_order_amount", "account_types", "first_order_only")},
        ),
        (
            _("حدود الاستعمال"),
            {"fields": ("usage_limit", "usage_limit_per_user", "usage_count")},
        ),
        (_("النطاق"), {"fields": ("products", "categories")}),
        (_("الصلاحية"), {"fields": ("starts_at", "ends_at")}),
        (_("تواريخ"), {"fields": ("created_at", "updated_at", "deleted_at")}),
    )


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(LogAdmin):
    list_display = (
        "created_at",
        "coupon",
        "user",
        "discount_amount",
        "order_amount",
        "is_cancelled",
    )
    list_filter = ("is_cancelled", "coupon", "created_at")
    list_select_related = ("coupon", "user")
    search_fields = ("coupon__code", "user__email", "reference_id")
    date_hierarchy = "created_at"
