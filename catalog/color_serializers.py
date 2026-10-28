"""
Colour contracts — the admin's view of a colour.

The public view (what the storefront gets) is built inside
`ProductDetailSerializer`, because it needs prices and availability from layers
the catalogue cannot import; see `core/color_facts.py`.
"""

from __future__ import annotations

from rest_framework import serializers

from catalog import rules
from catalog.models import HEX_COLOR_VALIDATOR, ProductColor
from catalog.serializers import ProductImageSerializer


class AdminProductColorSerializer(serializers.ModelSerializer):
    """
    A colour as the admin edits it.

    ⚠️  `price_override` is **nullable on purpose**: `null` = "use the product's
        price", `0.00` = a free item. The two must not be conflated, so the field
        accepts an explicit `null` and an omitted key leaves the stored value alone.

    ⚠️  The product comes from the URL (`context["product"]`), never from the body —
        a colour cannot be moved to another product by editing JSON.
    """

    hex = serializers.CharField(max_length=7, validators=[HEX_COLOR_VALIDATOR])
    price_override = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, allow_null=True, required=False
    )
    #: "Price before discount" for this colour — nullable like `price_override`, and judged
    #: against the colour's *own* effective price (see `validate`).
    compare_at_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, allow_null=True, required=False
    )
    name_ar = serializers.CharField(max_length=200, trim_whitespace=True)
    name_en = serializers.CharField(max_length=200, trim_whitespace=True)

    image_count = serializers.IntegerField(read_only=True, default=0)
    primary_image = serializers.SerializerMethodField()
    variant_id = serializers.SerializerMethodField()
    variant_count = serializers.SerializerMethodField()
    #: Exact figure — admins only (this serializer sits behind `CanManageCatalog`).
    stock_available = serializers.SerializerMethodField()

    class Meta:
        model = ProductColor
        fields = [
            "id",
            "name_ar",
            "name_en",
            "hex",
            "price_override",
            "compare_at_price",
            "display_order",
            "is_active",
            "image_count",
            "primary_image",
            "variant_id",
            "variant_count",
            "stock_available",
        ]
        read_only_fields = ["id"]

    # ── Reading ────────────────────────────────────────────

    def get_primary_image(self, obj):
        images = getattr(obj, "primary_images", None)
        if images:
            return ProductImageSerializer(images[0], context=self.context).data
        return None

    def _variants(self, obj) -> list:
        cached = getattr(obj, "color_variants", None)
        return cached if cached is not None else list(obj.variants.all())

    def get_variant_id(self, obj) -> str | None:
        variants = self._variants(obj)
        return str(variants[0].pk) if variants else None

    def get_variant_count(self, obj) -> int:
        return len(self._variants(obj))

    def get_stock_available(self, obj) -> int | None:
        facts = self.context.get("color_facts") or {}
        entry = facts.get(str(obj.pk))
        return entry.get("quantity") if entry else None

    # ── Writing ────────────────────────────────────────────

    def validate_hex(self, value: str) -> str:
        return value.upper()

    def validate(self, attrs):
        product = self.context["product"]

        # ⚠️  Names are unique among a product's living colours (a partial DB
        #     constraint backs this up) — checked here so the admin gets a message
        #     on the field instead of an integrity error.
        for field, message in (
            ("name_ar", "يوجد لون بهذا الاسم العربي لنفس المنتج"),
            ("name_en", "A colour with this English name already exists for this product"),
        ):
            value = attrs.get(field)
            if value is None:
                continue
            clash = ProductColor.objects.filter(product=product, **{field: value})
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError({field: [message]})

        # ⚠️  Against the price the colour will have **after** this save: its own when it has
        #     one, else the product's. A PATCH that clears `price_override` can leave an
        #     unchanged compare-at below the product's price, so both sides are merged
        #     with the stored values before judging.
        instance = self.instance
        price_override = (
            attrs["price_override"]
            if "price_override" in attrs
            else getattr(instance, "price_override", None)
        )
        compare_at = (
            attrs["compare_at_price"]
            if "compare_at_price" in attrs
            else getattr(instance, "compare_at_price", None)
        )
        errors = rules.compare_at_errors(
            compare_at=compare_at,
            price=price_override if price_override is not None else product.base_price,
        )
        if errors:
            raise serializers.ValidationError(errors)

        return attrs
