"""
Orders admin panel.

⚠️  **The status is never edited from the change form.**

    `orders.services.transition` is what checks the permitted transition, writes
    `OrderStatusHistory`, fulfils or releases the reservations, and emits the
    signals. Flipping the field in the panel does one thing: it lies to the rest
    of the system. So the status and the amounts are read-only, and changes go
    through the actions below.

⚠️  Order lines are a historical snapshot (name · price · tax at the time of
    purchase). Editing them rewrites the past and breaks invoice reconciliation.
"""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from core.admin import DomainModelAdmin, LogAdmin, ReadOnlyDomainAdmin
from orders.models import Order, OrderLine, OrderStatusHistory
from orders.services import cancel, complete, mark_paid


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    fields = (
        "product_sku",
        "product_name_ar",
        "quantity",
        "unit_price",
        "discount_amount",
        "tax_amount",
    )
    readonly_fields = fields
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    fields = ("created_at", "from_status", "to_status", "changed_by", "note")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(DomainModelAdmin):
    list_display = (
        "number",
        "created_at",
        "customer",
        "status",
        "payment_status",
        "channel",
        "grand_total",
        "currency",
    )
    list_filter = ("status", "payment_status", "channel", "currency", "created_at", "governorate")
    list_select_related = ("customer", "location")
    search_fields = (
        "number",
        "customer__customer_number",
        "customer__user__email",
        "recipient_name",
        "recipient_phone",
        "coupon_code",
    )
    autocomplete_fields = ("customer", "location", "owner_employee", "commission_employee")
    date_hierarchy = "created_at"
    inlines = (OrderLineInline, OrderStatusHistoryInline)
    list_per_page = 50
    actions = ["restore_selected", "mark_paid_selected", "complete_selected", "cancel_selected"]

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "deleted_at",
        "number",
        "status",
        "payment_status",
        "channel",
        "customer",
        "created_by",
        "currency",
        "subtotal",
        "discount_total",
        "coupon_discount",
        "tax_total",
        "shipping_total",
        "grand_total",
        "coupon_code",
        "shipping_method_code",
        "confirmed_at",
        "completed_at",
        "cancelled_at",
        "cancellation_reason",
    )

    fieldsets = (
        (None, {"fields": ("id", "number", "customer", "status", "payment_status", "channel")}),
        (
            _("الإسناد"),
            {"fields": ("location", "created_by", "owner_employee", "commission_employee")},
        ),
        (
            _("المبالغ"),
            {
                "fields": (
                    "currency",
                    "subtotal",
                    "discount_total",
                    "coupon_discount",
                    "coupon_code",
                    "tax_total",
                    "shipping_total",
                    "grand_total",
                )
            },
        ),
        (
            _("الشحن والمستلم"),
            {
                "fields": (
                    "shipping_method_code",
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
        (_("ملاحظات"), {"fields": ("customer_note", "internal_note")}),
        (
            _("تواريخ الدورة"),
            {
                "fields": (
                    "confirmed_at",
                    "completed_at",
                    "cancelled_at",
                    "cancellation_reason",
                    "created_at",
                    "updated_at",
                    "deleted_at",
                )
            },
        ),
    )

    @admin.action(description=_("تعليم المحدد كمدفوع"))
    def mark_paid_selected(self, request, queryset):
        self._run(request, queryset, lambda order: mark_paid(order, actor=request.user))

    @admin.action(description=_("إكمال المحدد"))
    def complete_selected(self, request, queryset):
        self._run(request, queryset, lambda order: complete(order, actor=request.user))

    @admin.action(description=_("إلغاء المحدد"))
    def cancel_selected(self, request, queryset):
        self._run(
            request,
            queryset,
            lambda order: cancel(order, reason=str(_("أُلغي من لوحة التشغيل")), actor=request.user),
        )

    def _run(self, request, queryset, action):
        """
        Each order separately: a refused transition on one must not stop the
        rest, and the reason is shown exactly as the service raised it.
        """
        done, failed = 0, []
        for order in queryset:
            try:
                action(order)
                done += 1
            # ⚠️  The broad catch is deliberate: we show the refusal reason as it is
            #     rather than dropping the whole bulk action on the first order that refuses.
            except Exception as exc:
                failed.append(f"{order.number}: {exc}")

        if done:
            self.message_user(request, _("تم تنفيذ %(count)d طلبًا.") % {"count": done})
        for line in failed:
            self.message_user(request, line, level="ERROR")


@admin.register(OrderLine)
class OrderLineAdmin(ReadOnlyDomainAdmin):
    list_display = (
        "order",
        "product_sku",
        "product_name_ar",
        "quantity",
        "unit_price",
        "discount_amount",
        "tax_amount",
    )
    list_select_related = ("order", "product", "variant")
    search_fields = ("order__number", "product_sku", "product_name_ar")
    date_hierarchy = "created_at"


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(LogAdmin):
    list_display = ("created_at", "order", "from_status", "to_status", "changed_by")
    list_filter = ("to_status", "created_at")
    list_select_related = ("order", "changed_by")
    search_fields = ("order__number", "note")
    date_hierarchy = "created_at"
