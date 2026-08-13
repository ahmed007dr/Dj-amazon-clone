"""
عقود السلة.

⚠️  الأسعار **مخرجات محسوبة لا مدخلات**.

    ما يرسله العميل من أسعار وإجماليات يُتجاهَل تمامًا — كلها
    `read_only`. قبولها يعني سلة يحدد العميل سعرها بتعديل حقل في
    المتصفح.
"""

from rest_framework import serializers


class MoneyField(serializers.DecimalField):
    """
    مبلغ يُسلسَل **نصًا**. (ADR-31)

    `JSON.parse` يحوّل الأرقام إلى `double` فتُفقد الدقة:
    `450.00` تصير `450`.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 12)
        kwargs.setdefault("decimal_places", 2)
        kwargs.setdefault("read_only", True)
        kwargs.setdefault("coerce_to_string", True)
        super().__init__(**kwargs)


class PricedLineSerializer(serializers.Serializer):
    """سطر مُسعَّر — كله مخرجات."""

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
    سطر السلة مع تسعيره اللحظي.

    يجمع بيانات السطر المخزَّنة (المنتج والكمية) مع السعر المحسوب
    من `pricing` — والسعر لا يُخزَّن.
    """

    id = serializers.UUIDField(read_only=True)
    product_id = serializers.UUIDField(read_only=True)
    product_slug = serializers.CharField(read_only=True)
    product_sku = serializers.CharField(read_only=True)
    product_name_ar = serializers.CharField(read_only=True)
    product_name_en = serializers.CharField(read_only=True)
    variant_id = serializers.UUIDField(read_only=True, allow_null=True)
    image = serializers.CharField(read_only=True, allow_null=True)
    pricing = PricedLineSerializer(read_only=True)


class LineIssueSerializer(serializers.Serializer):
    """
    مشكلة في سطر.

    ⚠️  تُعرض للعميل ليصحّحها — لا تُخفى.

        سلة تمنع إتمام الشراء بلا تفسير تُفقد المبيعة؛ وسطر يُحذف
        بصمت يُفقد الثقة.
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
    is_valid = serializers.BooleanField(read_only=True)
    code = serializers.SerializerMethodField()
    discount_amount = MoneyField()
    free_shipping = serializers.BooleanField(read_only=True)
    reason = serializers.SerializerMethodField()
    message = serializers.CharField(read_only=True)

    def get_code(self, obj) -> str:
        return obj.coupon.code if obj.coupon else ""

    def get_reason(self, obj) -> str:
        return obj.reason.value if obj.reason else ""


class CartSnapshotSerializer(serializers.Serializer):
    """
    السلة كاملة بعد إعادة التحقق.

    ⚠️  `is_checkoutable` هي البوابة الوحيدة إلى إتمام الشراء —
        والواجهة تعرضها ولا تقرّرها.
    """

    id = serializers.UUIDField(source="cart.id", read_only=True)
    status = serializers.CharField(source="cart.status", read_only=True)
    coupon_code = serializers.CharField(source="cart.coupon_code", read_only=True)
    lines = serializers.SerializerMethodField()
    totals = serializers.SerializerMethodField()
    issues = LineIssueSerializer(many=True, read_only=True)
    coupon = serializers.SerializerMethodField()
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
            images = getattr(product, "primary_images", None)

            result.append(
                {
                    "id": str(line.pk) if line else None,
                    "product_id": str(product.pk),
                    "product_slug": product.slug,
                    "product_sku": product.sku,
                    "product_name_ar": product.name_ar,
                    "product_name_en": product.name_en,
                    "variant_id": str(variant.pk) if variant else None,
                    "image": images[0].image.url if images else None,
                    "pricing": PricedLineSerializer(priced).data,
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


# ═══════════════════════════════════════════════════════════
#  المدخلات
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
