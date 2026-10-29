"""
Cart contracts.

⚠️  Prices are **computed outputs, not inputs**.

    Any prices or totals the client sends are ignored entirely — all of them are
    `read_only`. Accepting them means a cart whose price the customer sets by
    editing a field in the browser.
"""

from rest_framework import serializers

from catalog import compare_at
from catalog.selectors import image_for
from shipping.serializers import FreeShippingStatusSerializer


class MoneyField(serializers.DecimalField):
    """
    An amount serialised **as a string**. (ADR-31)

    `JSON.parse` converts numbers to `double`, so precision is lost:
    `450.00` becomes `450`.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 12)
        kwargs.setdefault("decimal_places", 2)
        kwargs.setdefault("read_only", True)
        kwargs.setdefault("coerce_to_string", True)
        super().__init__(**kwargs)


class PricedLineSerializer(serializers.Serializer):
    """A priced line — output throughout."""

    quantity = serializers.IntegerField(read_only=True)
    unit_price = MoneyField()
    list_price = MoneyField()
    discount_amount = MoneyField()
    tax_rate = MoneyField(max_digits=5)
    tax_amount = MoneyField()
    subtotal = MoneyField()
    net = MoneyField()
    total = MoneyField()
    has_discount = serializers.BooleanField(read_only=True)


class CartLineSerializer(serializers.Serializer):
    """
    A cart line with its live pricing.

    It combines the stored line data (product and quantity) with the price
    computed from `pricing` — and the price is never stored.
    """

    id = serializers.UUIDField(read_only=True)
    product_id = serializers.UUIDField(read_only=True)
    product_slug = serializers.CharField(read_only=True)
    product_sku = serializers.CharField(read_only=True)
    product_name_ar = serializers.CharField(read_only=True)
    product_name_en = serializers.CharField(read_only=True)
    variant_id = serializers.UUIDField(read_only=True, allow_null=True)
    variant_sku = serializers.CharField(read_only=True, allow_null=True)
    variant_name_ar = serializers.CharField(read_only=True, allow_null=True)
    variant_name_en = serializers.CharField(read_only=True, allow_null=True)
    #: `{id, name_ar, name_en, hex}` when the variant belongs to a colour, else null
    color = serializers.DictField(read_only=True, allow_null=True)
    image = serializers.CharField(read_only=True, allow_null=True)
    pricing = PricedLineSerializer(read_only=True)
    #: The "price before discount" — present only while it is above this line's `unit_price`
    compare_at_price = MoneyField(allow_null=True)
    #: The saving as a whole percentage, rounded down; `null` with no compare-at price
    discount_percent = serializers.IntegerField(read_only=True, allow_null=True)


class LineIssueSerializer(serializers.Serializer):
    """
    A problem on a line.

    ⚠️  Shown to the customer to correct — never hidden.

        A cart that blocks checkout with no explanation loses the sale; a line
        silently removed loses trust.
    """

    line_id = serializers.CharField(read_only=True)
    product_sku = serializers.CharField(read_only=True)
    product_name = serializers.CharField(read_only=True)
    code = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True)
    available = serializers.IntegerField(read_only=True, allow_null=True)


class CartTotalsSerializer(serializers.Serializer):
    subtotal = MoneyField()
    line_discount = MoneyField()
    coupon_discount = MoneyField()
    discount_total = MoneyField()
    net_sales = MoneyField()
    tax_total = MoneyField()
    shipping_amount = MoneyField()
    total = MoneyField()
    item_count = serializers.IntegerField(read_only=True)
    currency = serializers.CharField(read_only=True)


class CouponResultSerializer(serializers.Serializer):
    """
    The coupon as the cart sees it.

    ⚠️  The **scope** is explained, not left to guesswork: `applies_to` is `ALL` when every
        line gets the discount and `SOME` when the coupon is limited to certain products,
        with `eligible_line_ids` naming the lines it covers and `eligible_subtotal` the
        amount it was calculated on — so the storefront can say "Applies to 2 of 3 items".
        All of it is computed by the server; the client never decides eligibility.
    """

    is_valid = serializers.BooleanField(read_only=True)
    code = serializers.SerializerMethodField()
    kind = serializers.SerializerMethodField()
    #: The same figure as `discount_amount` — the name the scope contract uses
    discount = MoneyField(source="discount_amount")
    discount_amount = MoneyField()
    free_shipping = serializers.BooleanField(read_only=True)
    applies_to = serializers.CharField(read_only=True)
    eligible_line_ids = serializers.SerializerMethodField()
    eligible_count = serializers.SerializerMethodField()
    line_count = serializers.IntegerField(read_only=True)
    eligible_subtotal = MoneyField()
    reason = serializers.SerializerMethodField()
    message = serializers.CharField(read_only=True)
    message_en = serializers.CharField(read_only=True)

    def get_code(self, obj) -> str:
        return obj.coupon.code if obj.coupon else ""

    def get_kind(self, obj) -> str:
        return obj.coupon.kind if obj.coupon else ""

    def get_eligible_line_ids(self, obj) -> list:
        # Only a valid result covers any line; the refs are cart line ids (strings)
        if not obj.is_valid:
            return []
        return [ref for ref in obj.eligible_refs if isinstance(ref, str)]

    def get_eligible_count(self, obj) -> int:
        return len(obj.eligible_refs) if obj.is_valid else 0

    def get_reason(self, obj) -> str:
        return obj.reason.value if obj.reason else ""


class CartSnapshotSerializer(serializers.Serializer):
    """
    The complete cart after re-validation.

    ⚠️  `is_checkoutable` is the only gate to checkout — the frontend displays
        it and never decides it.
    """

    id = serializers.UUIDField(source="cart.id", read_only=True)
    status = serializers.CharField(source="cart.status", read_only=True)
    coupon_code = serializers.CharField(source="cart.coupon_code", read_only=True)
    lines = serializers.SerializerMethodField()
    totals = serializers.SerializerMethodField()
    issues = LineIssueSerializer(many=True, read_only=True)
    coupon = serializers.SerializerMethodField()
    #: `{enabled, threshold, qualifies, remaining}` — the free-shipping rule against this cart
    free_shipping = serializers.SerializerMethodField()
    is_checkoutable = serializers.BooleanField(read_only=True)

    def get_lines(self, snapshot) -> list:
        result = []
        line_map = {
            (str(line.product_id), str(line.variant_id or "")): line
            for line in snapshot.cart.lines.select_related("product", "variant").all()
        }

        for (product, _quantity, variant), priced in snapshot.lines:
            key = (str(product.pk), str(variant.pk if variant else ""))
            line = line_map.get(key)
            color = variant.color if variant is not None and variant.color_id else None
            # ⚠️  The colour's own photo first, then the product's — the line shows
            #     the item the customer actually chose, not the colour on the cover.
            picture = image_for(product, color)

            # ⚠️  The "price before discount" is judged against `unit_price` — the very figure the
            #     product page showed this customer (price list → colour → product → + variant
            #     difference) — and shown only when it is above it. The server decides here too.
            old_price = compare_at.display_facts(
                compare_at.reference_compare_at(product, color, variant), priced.unit_price
            )

            result.append(
                {
                    "id": str(line.pk) if line else None,
                    "product_id": str(product.pk),
                    "product_slug": product.slug,
                    "product_sku": product.sku,
                    "product_name_ar": product.name_ar,
                    "product_name_en": product.name_en,
                    "variant_id": str(variant.pk) if variant else None,
                    "variant_sku": variant.sku if variant else None,
                    "variant_name_ar": variant.name_ar if variant else None,
                    "variant_name_en": variant.name_en if variant else None,
                    "color": (
                        {
                            "id": str(color.pk),
                            "name_ar": color.name_ar,
                            "name_en": color.name_en,
                            "hex": color.hex,
                        }
                        if color is not None
                        else None
                    ),
                    "image": picture.image.url if picture else None,
                    "pricing": PricedLineSerializer(priced).data,
                    **old_price,
                }
            )
        return result

    def get_totals(self, snapshot) -> dict:
        from core.money import get_currency

        priced = snapshot.priced
        return CartTotalsSerializer(
            {
                "subtotal": priced.subtotal,
                "line_discount": priced.line_discount,
                "coupon_discount": priced.coupon_discount,
                "discount_total": priced.discount_total,
                "net_sales": priced.net_sales,
                "tax_total": priced.tax_total,
                "shipping_amount": priced.shipping_amount,
                "total": priced.total,
                "item_count": priced.item_count,
                "currency": get_currency(),
            }
        ).data

    def get_coupon(self, snapshot) -> dict | None:
        if snapshot.coupon_result is None:
            return None
        return CouponResultSerializer(snapshot.coupon_result).data

    def get_free_shipping(self, snapshot) -> dict:
        """
        ⚠️  Computed by `revalidate` — the storefront never subtracts the cart from
            the threshold itself, and `enabled=false` means it draws nothing.
        """
        return FreeShippingStatusSerializer(snapshot.free_shipping).data


# ═══════════════════════════════════════════════════════════
#  Inputs
# ═══════════════════════════════════════════════════════════


class AddLineSerializer(serializers.Serializer):
    product = serializers.UUIDField()
    variant = serializers.UUIDField(required=False, allow_null=True)
    quantity = serializers.IntegerField(min_value=1, max_value=999, default=1)


class SetQuantitySerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=0, max_value=999)


class ApplyCouponSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32)


class AddBundleSerializer(serializers.Serializer):
    bundle = serializers.UUIDField()
    essentials_only = serializers.BooleanField(default=False)
