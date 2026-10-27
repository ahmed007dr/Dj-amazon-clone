"""
Contracts for the guest order endpoints.

⚠️  The output side is **deliberately narrower than `OrderDetailSerializer`.**

    The page behind a tracking link is reachable by whoever holds the link — a
    forwarded email, a screenshot, a browser history on a shared machine. So it
    shows what the person needs to follow the parcel and nothing that would
    help someone else: no email, no full address, no customer note, no staff
    names in the timeline, and the phone masked.
"""

from rest_framework import serializers

from orders import guest
from orders.models import Order, OrderLine, OrderStatusHistory
from shipping.governorates import EGYPT_GOVERNORATES


class MoneyField(serializers.DecimalField):
    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 12)
        kwargs.setdefault("decimal_places", 2)
        kwargs.setdefault("read_only", True)
        kwargs.setdefault("coerce_to_string", True)
        super().__init__(**kwargs)


# ═══════════════════════════════════════════════════════════
#  Input
# ═══════════════════════════════════════════════════════════


class GuestCheckoutSerializer(serializers.Serializer):
    """
    What a visitor types: who, where, how to reach them.

    ⚠️  **There is no payment, coupon or address-book field to send.**

        Payment is cash on delivery and is not a choice; coupons and saved
        addresses belong to accounts. Fields that must not be sent are rejected
        rather than silently ignored, so a client that thinks it applied a
        coupon finds out instead of finding a missing discount on the invoice.
    """

    recipient_name = serializers.CharField(min_length=2, max_length=200)
    phone = serializers.CharField(max_length=32)
    email = serializers.EmailField(max_length=254)
    governorate = serializers.ChoiceField(choices=list(EGYPT_GOVERNORATES))
    city = serializers.CharField(max_length=100)
    street = serializers.CharField(max_length=500)
    shipping_method_code = serializers.CharField(max_length=50)
    customer_note = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    language = serializers.ChoiceField(choices=guest.SUPPORTED_LANGUAGES, required=False)

    #: Only cash on delivery exists for guests; accepted so a client may say so.
    payment_method = serializers.ChoiceField(choices=["COD"], required=False)

    #: The client's retry key. Also read from the `Idempotency-Key` header — the
    #: header wins. A body field exists because the shared HTTP client does not
    #: forward arbitrary headers.
    idempotency_key = serializers.CharField(
        max_length=128, required=False, allow_blank=True, write_only=True
    )

    #: ⚠️  The honeypot. Hidden from people by CSS; a script that fills in every
    #:     input fills this one too. Any value at all means "not a person".
    website = serializers.CharField(required=False, allow_blank=True, write_only=True)

    #: The seam for a captcha provider (`GUEST_CHECKOUT_CAPTCHA_VERIFIER`).
    captcha_token = serializers.CharField(
        max_length=4096, required=False, allow_blank=True, write_only=True
    )

    #: Fields an account has and a guest does not.
    FORBIDDEN = ("address_id", "address", "coupon", "coupon_code", "credit")

    def to_internal_value(self, data):
        present = [name for name in self.FORBIDDEN if hasattr(data, "get") and name in data]
        if present:
            raise serializers.ValidationError(
                {name: "غير متاح للشراء كزائر — سجّل الدخول لاستخدامه" for name in present}
            )
        return super().to_internal_value(data)

    def validate_recipient_name(self, value):
        value = " ".join(value.split())
        if len(value) < 2:
            raise serializers.ValidationError("أدخل الاسم الكامل")
        return value

    def validate_phone(self, value):
        canonical = guest.normalise_phone(value)
        if not canonical:
            raise serializers.ValidationError("أدخل رقم موبايل مصري صحيحًا (مثل 01012345678)")
        return canonical

    def validate_email(self, value):
        return value.strip().lower()

    def validate_city(self, value):
        return " ".join(value.split())

    def validate_street(self, value):
        value = " ".join(value.split())
        if len(value) < 5:
            raise serializers.ValidationError("اكتب العنوان بالتفصيل (الشارع ورقم المبنى)")
        return value


class GuestLookupSerializer(serializers.Serializer):
    order_number = serializers.CharField(max_length=32)
    phone = serializers.CharField(max_length=32)


class GuestCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


# ═══════════════════════════════════════════════════════════
#  Output
# ═══════════════════════════════════════════════════════════


class GuestOrderLineSerializer(serializers.ModelSerializer):
    net = MoneyField()
    total = MoneyField()

    class Meta:
        model = OrderLine
        fields = [
            "id",
            "product_name_ar",
            "product_name_en",
            # The colour / variant the buyer chose — snapshots, so they read the
            # same whatever happens to the live variant afterwards.
            "variant_name_ar",
            "variant_name_en",
            "color_name_ar",
            "color_name_en",
            "color_hex",
            "quantity",
            "unit_price",
            "net",
            "total",
        ]
        read_only_fields = fields


class GuestTimelineSerializer(serializers.ModelSerializer):
    """⚠️  Status and time only — the staff name and the internal note stay inside."""

    class Meta:
        model = OrderStatusHistory
        fields = ["to_status", "created_at"]
        read_only_fields = fields


class GuestOrderSerializer(serializers.ModelSerializer):
    """What the tracking page shows."""

    lines = GuestOrderLineSerializer(many=True, read_only=True)
    timeline = serializers.SerializerMethodField()
    can_cancel = serializers.SerializerMethodField()
    phone_masked = serializers.SerializerMethodField()
    email_masked = serializers.SerializerMethodField()
    payment_method = serializers.SerializerMethodField()
    item_count = serializers.IntegerField(read_only=True)
    subtotal = MoneyField()
    discount_total = MoneyField()
    tax_total = MoneyField()
    shipping_total = MoneyField()
    grand_total = MoneyField()

    class Meta:
        model = Order
        fields = [
            "number",
            "status",
            "payment_status",
            "payment_method",
            "created_at",
            "confirmed_at",
            "cancelled_at",
            "cancellation_reason",
            "currency",
            "item_count",
            "subtotal",
            "discount_total",
            "tax_total",
            "shipping_total",
            "grand_total",
            "recipient_name",
            "governorate",
            "city",
            "phone_masked",
            "email_masked",
            "lines",
            "timeline",
            "can_cancel",
        ]
        read_only_fields = fields

    def get_timeline(self, obj) -> list:
        # Oldest first: a timeline reads forward
        history = sorted(obj.status_history.all(), key=lambda row: (row.created_at, row.pk))
        return GuestTimelineSerializer(history, many=True).data

    def get_can_cancel(self, obj) -> bool:
        """⚠️  Only while PENDING — see `guest.cancel_with_token`."""
        from orders.models import OrderStatus

        return obj.status == OrderStatus.PENDING

    def get_phone_masked(self, obj) -> str:
        return guest.mask_phone(obj.recipient_phone)

    def get_email_masked(self, obj) -> str:
        return guest.mask_email(obj.contact_email)

    def get_payment_method(self, obj) -> str:
        # Guests only ever pay on delivery
        return "COD"


def placed_payload(result: "guest.GuestOrderResult") -> dict:
    """The checkout response: enough to show a confirmation and open the tracking page."""
    order = result.order
    return {
        "order_number": order.number,
        "status": order.status,
        "payment_status": order.payment_status,
        "totals": {
            "subtotal": str(order.subtotal),
            "discount_total": str(order.discount_total),
            "tax_total": str(order.tax_total),
            "shipping_total": str(order.shipping_total),
            "grand_total": str(order.grand_total),
            "currency": order.currency,
        },
        "tracking_token": result.token,
        "replayed": result.replayed,
    }
