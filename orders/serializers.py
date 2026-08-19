"""
Order contracts.

⚠️  Amounts are **computed outputs** — all of them `read_only`.

    Any totals the client sends are ignored: the order is priced from the source
    when it is created. Accepting the figure from the frontend means a customer
    setting what they pay.
"""

from rest_framework import serializers

from orders.models import Order, OrderLine, OrderStatusHistory


class MoneyField(serializers.DecimalField):
    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 12)
        kwargs.setdefault("decimal_places", 2)
        kwargs.setdefault("read_only", True)
        kwargs.setdefault("coerce_to_string", True)
        super().__init__(**kwargs)


class OrderLineSerializer(serializers.ModelSerializer):
    """
    An order line — every field **a snapshot at the time of sale**.

    The name, the price and the tax rate are copied, so the invoice stays
    readable and correct after the catalogue or the tax changes.
    """

    product_slug = serializers.CharField(source="product.slug", read_only=True)
    net = MoneyField()
    total = MoneyField()

    class Meta:
        model = OrderLine
        fields = [
            "id",
            "product",
            "product_slug",
            "product_sku",
            "product_name_ar",
            "product_name_en",
            "variant",
            "quantity",
            "unit_price",
            "list_price",
            "discount_amount",
            "tax_rate",
            "tax_amount",
            "tax_class_code",
            "net",
            "total",
        ]
        read_only_fields = fields


class OrderStatusHistorySerializer(serializers.ModelSerializer):
    changed_by_email = serializers.EmailField(
        source="changed_by.email", read_only=True, default=None
    )

    class Meta:
        model = OrderStatusHistory
        fields = ["id", "from_status", "to_status", "note", "changed_by_email", "created_at"]
        read_only_fields = fields


class OrderListSerializer(serializers.ModelSerializer):
    """A row in "my orders"."""

    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "number",
            "status",
            "payment_status",
            "channel",
            "grand_total",
            "currency",
            "item_count",
            "created_at",
        ]
        read_only_fields = fields


class OrderDetailSerializer(OrderListSerializer):
    lines = OrderLineSerializer(many=True, read_only=True)
    status_history = OrderStatusHistorySerializer(many=True, read_only=True)
    can_cancel = serializers.SerializerMethodField()

    class Meta(OrderListSerializer.Meta):
        fields = [
            *OrderListSerializer.Meta.fields,
            "subtotal",
            "discount_total",
            "coupon_discount",
            "coupon_code",
            "tax_total",
            "shipping_total",
            "shipping_method_code",
            "recipient_name",
            "recipient_phone",
            "governorate",
            "city",
            "street",
            "building",
            "landmark",
            "customer_note",
            "confirmed_at",
            "completed_at",
            "cancelled_at",
            "cancellation_reason",
            "lines",
            "status_history",
            "can_cancel",
        ]
        read_only_fields = fields

    def get_can_cancel(self, obj) -> bool:
        """
        ⚠️  Computed from the state machine itself, not from a parallel list.

            A second list in the frontend diverges from the real rules, so a
            cancel button appears and fails when pressed.
        """
        from orders import services

        return services.can_cancel(obj)


class AdminOrderSerializer(OrderDetailSerializer):
    """The admin version — it exposes the attribution and the internal notes."""

    customer_email = serializers.EmailField(source="customer.user.email", read_only=True)
    customer_number = serializers.CharField(source="customer.customer_number", read_only=True)

    class Meta(OrderDetailSerializer.Meta):
        fields = [
            *OrderDetailSerializer.Meta.fields,
            "customer",
            "customer_email",
            "customer_number",
            "location",
            "created_by",
            "owner_employee",
            "commission_employee",
            "internal_note",
        ]
        read_only_fields = fields


# ═══════════════════════════════════════════════════════════
#  Inputs
# ═══════════════════════════════════════════════════════════


class AddressSerializer(serializers.Serializer):
    recipient_name = serializers.CharField(max_length=200)
    phone = serializers.CharField(max_length=20)
    governorate = serializers.CharField(max_length=100)
    city = serializers.CharField(max_length=100)
    street = serializers.CharField()
    building = serializers.CharField(max_length=50, required=False, allow_blank=True)
    landmark = serializers.CharField(max_length=200, required=False, allow_blank=True)


class CheckoutSerializer(serializers.Serializer):
    """
    ⚠️  **No amount fields here at all.**

        The order is priced from the source when it is created. Accepting
        `total` from the customer means the browser sets the invoice.
    """

    address_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="عنوان محفوظ — أو أرسل `address` صراحةً",
    )
    address = AddressSerializer(required=False)
    shipping_method_code = serializers.CharField(max_length=50, required=False, allow_blank=True)
    payment_method = serializers.CharField(max_length=16)
    customer_note = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate(self, attrs):
        if not attrs.get("address_id") and not attrs.get("address"):
            raise serializers.ValidationError(
                {"address": "أرسل `address_id` لعنوان محفوظ أو `address` كاملًا"}
            )
        return attrs


class CancelOrderSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=3, max_length=500)


class TransitionOrderSerializer(serializers.Serializer):
    from orders.models import OrderStatus

    status = serializers.ChoiceField(choices=OrderStatus.choices)
    note = serializers.CharField(required=False, allow_blank=True, max_length=500)
