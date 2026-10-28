"""
Catalogue contracts.

⚠️  Content is sent **in both languages always** (ADR-34) — the admin panel
    displays both, and sending only the translated one forces a second call.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from rest_framework import serializers

from catalog import audit, compare_at
from catalog.models import (
    Brand,
    Category,
    Manufacturer,
    Product,
    ProductImage,
    ProductVariant,
)
from core.color_facts import color_facts
from core.files import ALLOWED_IMAGE_TYPES, MAX_IMAGE_SIZE, validate_upload
from core.money import quantize
from core.price_facts import viewer_prices


class CategoryBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "slug", "name_ar", "name_en"]


class BrandBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "slug", "name_ar", "name_en", "logo"]


class ManufacturerBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Manufacturer
        fields = ["id", "slug", "name_ar", "name_en", "country"]


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = [
            "id",
            "image",
            "alt_text_ar",
            "alt_text_en",
            "display_order",
            "is_primary",
            "color",
        ]
        # ⚠️  Ordering and "primary" are set from dedicated endpoints, not on upload.
        #
        #     Allowing `is_primary=True` to be sent with the upload breaks the
        #     unique constraint instead of moving the primary, and reaches the admin as a 500.
        #
        #     `color` is read-only for the same kind of reason: it is read from the
        #     request by `image_api`, which checks the colour belongs to the product.
        #     Accepting it here would skip that check.
        read_only_fields = ["display_order", "is_primary", "color"]

    def validate_image(self, value):
        """
        ⚠️  **The check happens here, not in the frontend.**

            A size limit in `<input accept>` is a hint to the browser, not a
            barrier; and someone uploading with curl never passes through the frontend at all.
        """
        # ⚠️  Django's `ValidationError` is not DRF's equivalent.
        #
        #     Letting it propagate makes the rejection come out as a 500 instead of a
        #     400 with a message — so a rejected file looks like a server fault.
        try:
            validate_upload(
                value,
                allowed_types=ALLOWED_IMAGE_TYPES,
                max_size=MAX_IMAGE_SIZE,
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return value


class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "sku",
            "barcode",
            "name_ar",
            "name_en",
            "attributes",
            "price_adjustment",
            "display_order",
            "color",
        ]


class RatingSerializer(serializers.Serializer):
    """
    The aggregated rating.

    ⚠️  It comes from `select_related('rating')` — not from an on-the-fly
        computation. On-the-fly computation is what produced N+1 in the legacy model.
    """

    average = serializers.DecimalField(max_digits=3, decimal_places=2, read_only=True)
    count = serializers.IntegerField(read_only=True)
    distribution = serializers.DictField(read_only=True)


class _PricedListSerializer(serializers.ListSerializer):
    """
    Prices the **whole page** in one go, then serialises each card from that.

    ⚠️  The viewer's price comes from `pricing` through `core.price_facts`, and asking it
        per card is the N+1 this class exists to prevent: it loads the page's rules in a
        fixed number of queries and hands the result to the child serializer.
    """

    def to_representation(self, data):
        # A manager is re-queried, a queryset or a page is used as it is (as DRF's own does):
        # `.all()` on an evaluated queryset would throw away its prefetches.
        items = list(data.all() if isinstance(data, models.manager.BaseManager) else data)
        self.child.load_prices(items)
        return [self.child.to_representation(item) for item in items]


class ProductListSerializer(serializers.ModelSerializer):
    """
    The product card in lists.

    ⚠️  **No quantity, and the price is `pricing`'s, not computed here.**

        `inventory` answers availability, and `pricing` computes the price per customer.
        `price` below is whatever the registered provider returned for *this viewer*
        (`core.price_facts`) — the catalogue adds only what it owns: the owner-typed
        "price before discount", shown when it is above that price (`catalog.compare_at`).
    """

    category = CategoryBriefSerializer(read_only=True)
    brand = BrandBriefSerializer(read_only=True)
    primary_image = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "slug",
            "sku",
            "name_ar",
            "name_en",
            "short_description_ar",
            "short_description_en",
            "kind",
            "category",
            "brand",
            "primary_image",
            "rating",
            "base_price",
            "is_featured",
            "requires_prescription",
            "regulatory_class",
        ]
        list_serializer_class = _PricedListSerializer

    # ── Prices ─────────────────────────────────────────────

    def load_prices(self, products, variants=()) -> None:
        """
        Ask `pricing` once for these products (and variants) and remember the answer.

        Idempotent per key: a second call adds the keys it has not seen, so the detail
        serializer can call it for the product and its variants without losing either.
        """
        found = viewer_prices(products, variants, user=self._price_user())
        cache = getattr(self, "_viewer_prices", None) or {"products": {}, "variants": {}}
        cache["products"].update(found["products"])
        cache["variants"].update(found["variants"])
        self._viewer_prices = cache

    def _product_price(self, obj) -> Decimal:
        cache = getattr(self, "_viewer_prices", None)
        if cache is None or str(obj.pk) not in cache["products"]:
            self.load_prices([obj])
            cache = self._viewer_prices
        # No provider (or it failed) → the reference price is the honest fallback
        return cache["products"].get(str(obj.pk), obj.base_price)

    def to_representation(self, obj):
        data = super().to_representation(obj)
        price = self._product_price(obj)
        data["price"] = format(quantize(price), "f")
        data.update(compare_at.display_facts(compare_at.reference_compare_at(obj), price))
        return data

    def _price_user(self):
        """Who is being priced: the preview user if there is one, else the requester."""
        if "price_user" in self.context:
            return self.context["price_user"]
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return user if getattr(user, "is_authenticated", False) else None

    def get_primary_image(self, obj):
        """Reads from the `to_attr` the prefetch prepared — no query."""
        images = getattr(obj, "primary_images", None)
        if images:
            return ProductImageSerializer(images[0], context=self.context).data
        return None

    def get_rating(self, obj):
        rating = getattr(obj, "rating", None)
        if rating is None:
            return {"average": "0.00", "count": 0}
        return {"average": str(rating.average), "count": rating.count}


class ProductDetailSerializer(ProductListSerializer):
    manufacturer = ManufacturerBriefSerializer(read_only=True)
    images = serializers.SerializerMethodField()
    variants = serializers.SerializerMethodField()
    colors = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = [
            *ProductListSerializer.Meta.fields,
            "description_ar",
            "description_en",
            "manufacturer",
            "images",
            "variants",
            "colors",
            "barcode",
            # Pharmaceutical fields
            "active_ingredient_ar",
            "active_ingredient_en",
            "strength",
            "dosage_form",
            "pack_size",
            "storage_condition",
            "registration_number",
            "weight_grams",
            # SEO
            "meta_title_ar",
            "meta_title_en",
            "meta_description_ar",
            "meta_description_en",
        ]

    def to_representation(self, obj):
        # ⚠️  The prices of the product **and every variant** in one provider call, before any
        #     field runs — `get_variants` and `get_colors` only read the answer.
        #     A coloured variant is given its colour in memory: the engine looks it up to
        #     apply the colour's own price, and fetching it per variant is the N+1 to avoid.
        variants = list(obj.variants.all())
        colors_by_id = {color.pk: color for color in obj.colors.all()}
        for variant in variants:
            if variant.color_id in colors_by_id:
                variant.color = colors_by_id[variant.color_id]
        self._variants = variants
        self.load_prices([obj], variants)
        return super().to_representation(obj)

    def get_variants(self, obj):
        """
        The variants, each with **its own** price and "price before discount".

        The page used to add a variant's `price_adjustment` to a price in the browser. Here
        the figure is `pricing`'s for that exact variant, and the old price carries the same
        difference (`catalog.compare_at.reference_compare_at`), so a size that costs more
        also "was" worth more — and the saving reads the same on every size.
        """
        variants = self._variants
        rows = ProductVariantSerializer(variants, many=True, context=self.context).data
        prices = self._viewer_prices["variants"]

        payload = []
        for variant, row in zip(variants, rows, strict=True):
            price = prices.get(str(variant.pk), obj.base_price + variant.price_adjustment)
            color = variant.color if variant.color_id else None
            payload.append(
                {
                    **row,
                    "price": format(quantize(price), "f"),
                    **compare_at.display_facts(
                        compare_at.reference_compare_at(obj, color, variant), price
                    ),
                }
            )
        return payload

    def get_images(self, obj):
        """
        The **base** gallery.

        ⚠️  Filtered here as well as in the detail queryset: a caller that built its
            own queryset without that prefetch would otherwise get every colour's
            photos mixed into the main gallery.
        """
        base = [image for image in obj.images.all() if image.color_id is None]
        return ProductImageSerializer(base, many=True, context=self.context).data

    def get_colors(self, obj):
        """
        The product's colours for the storefront swatches.

        Each carries its **own images only** — the page falls back to the base
        gallery when `images` is empty — plus a price and an availability that
        come from `pricing` and `inventory` through `core.color_facts` (this
        module cannot import either; see that file). `price_override` is the raw
        figure, `price` what *this customer* pays for the colour.
        """
        colors = [
            color
            for color in obj.colors.all()
            if color.is_active and color.deleted_at is None
        ]
        if not colors:
            return []

        for color in colors:
            if not hasattr(color, "active_variants"):
                # Only when a caller skipped the detail queryset's prefetch
                color.active_variants = [v for v in color.variants.all() if v.is_active]

        facts = color_facts(obj, colors, user=self._price_user())

        payload = []
        for color in colors:
            entry = facts.get(str(color.pk), {})
            price = entry.get("price")
            if price is None:
                own = color.price_override
                price = str(own if own is not None else obj.base_price)
            variants = color.active_variants

            payload.append(
                {
                    "id": str(color.pk),
                    "name_ar": color.name_ar,
                    "name_en": color.name_en,
                    "hex": color.hex,
                    "price": price,
                    "price_override": (
                        None if color.price_override is None else str(color.price_override)
                    ),
                    # The colour's own "price before discount", judged against `price` — the
                    # figure *this customer* pays for it — so a student price that is not
                    # below the old figure shows no strike-through here either.
                    **compare_at.display_facts(
                        compare_at.reference_compare_at(
                            obj, color, variants[0] if variants else None
                        ),
                        Decimal(price),
                    ),
                    # No variant = nothing to put in the cart = sold out, whatever stock says
                    "is_available": bool(variants) and entry.get("is_available", True),
                    "is_low": entry.get("is_low", False),
                    "available": entry.get("available"),
                    "variant_id": str(variants[0].pk) if variants else None,
                    "images": ProductImageSerializer(
                        color.images.all(), many=True, context=self.context
                    ).data,
                }
            )
        return payload

    def get_rating(self, obj):
        rating = getattr(obj, "rating", None)
        if rating is None:
            return {"average": "0.00", "count": 0, "distribution": {}}
        return {
            "average": str(rating.average),
            "count": rating.count,
            "distribution": rating.distribution,
        }


class CategorySerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "slug",
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "image",
            "icon",
            "depth",
            "display_order",
            "children",
        ]

    def get_children(self, obj):
        """
        Reads the children from the tree built in memory — not from the
        database. Iterating `obj.children.all()` here means one query per node.
        """
        node = self.context.get("tree_node")
        if node is None:
            return []
        return [
            CategorySerializer(child["object"], context={"tree_node": child}).data
            for child in node["children"]
        ]


class BrandSerializer(serializers.ModelSerializer):
    manufacturer = ManufacturerBriefSerializer(read_only=True)

    class Meta:
        model = Brand
        fields = [
            "id",
            "slug",
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "logo",
            "manufacturer",
            "is_featured",
        ]


class ManufacturerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Manufacturer
        fields = [
            "id",
            "slug",
            "name_ar",
            "name_en",
            "country",
            "registration_number",
            "website",
            "logo",
        ]


# ═══════════════════════════════════════════════════════════
#  Admin
# ═══════════════════════════════════════════════════════════


class AdminProductSerializer(serializers.ModelSerializer):
    """
    The admin version — every field is writable.

    ⚠️  `slug` is read-only: changing it breaks external links and search engine
        indexing. (ADR-27)

    ⚠️  `created_by` / `updated_by` are **declared** as read-only objects, not left to
        the `exclude` default: the model-serializer would otherwise expose them as
        writable primary-key fields, and any admin could forge "added by" for someone
        else. The server stamps them from `request.user` (see `catalog.api`).
    """

    created_by = serializers.SerializerMethodField()
    updated_by = serializers.SerializerMethodField()

    class Meta:
        model = Product
        exclude = ["deleted_at"]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]

    def get_created_by(self, obj) -> dict | None:
        return audit.actor_brief(obj.created_by)

    def get_updated_by(self, obj) -> dict | None:
        return audit.actor_brief(obj.updated_by)

    def validate(self, attrs):
        """
        ⚠️  Consistency of the regulatory fields — **through `catalog.rules`.**

            The check used to be written out here, which made it a property of
            this screen rather than of the catalogue: bulk import writes rows
            with `bulk_create` and never touches a serializer, so the same
            contradiction went straight into the database from a spreadsheet.
            One function, both callers.
        """
        from catalog import rules

        instance = self.instance
        errors = rules.regulatory_errors(
            kind=attrs.get("kind", getattr(instance, "kind", None)),
            regulatory_class=attrs.get(
                "regulatory_class", getattr(instance, "regulatory_class", None)
            ),
            requires_prescription=attrs.get(
                "requires_prescription", getattr(instance, "requires_prescription", False)
            ),
        )
        # ⚠️  "Price before discount" against the price **as it will be after this save** —
        #     a PATCH that only raises `base_price` can strand an unchanged compare-at below
        #     it, and a PATCH that only sets compare-at must be judged against the stored price.
        errors.update(
            rules.compare_at_errors(
                compare_at=(
                    attrs["compare_at_price"]
                    if "compare_at_price" in attrs
                    else getattr(instance, "compare_at_price", None)
                ),
                price=(
                    attrs["base_price"]
                    if "base_price" in attrs
                    else getattr(instance, "base_price", Decimal("0"))
                ),
            )
        )
        if errors:
            raise serializers.ValidationError(errors)

        return attrs


class ProductHistorySerializer(serializers.Serializer):
    """
    One row of a product's timeline, read from `core.AuditLog`.

    ⚠️  `action_label` is the server's own (translated) label so the screen never
        keeps a second list of audit actions that drifts from `AuditAction`.
        `changes` is passed through as stored: `{"field": {"old": …, "new": …}}`
        for updates, a small descriptive dict for create/delete/restore.
    """

    id = serializers.IntegerField(read_only=True)
    action = serializers.CharField(read_only=True)
    action_label = serializers.SerializerMethodField()
    object_repr = serializers.CharField(read_only=True)
    changes = serializers.JSONField(read_only=True)
    actor = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)

    def get_action_label(self, obj) -> str:
        return str(obj.get_action_display())

    def get_actor(self, obj) -> dict | None:
        return audit.actor_brief(obj.actor)


# ═══════════════════════════════════════════════════════════
#  Admin — reference classification
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  These three used to be managed from the Django panel alone. And they are
#      **a precondition** for adding any product: the category is mandatory on
#      `Product`, so a store with no categories screen cannot add its first item from its panel.


class AdminCategorySerializer(serializers.ModelSerializer):
    """
    ⚠️  `path`, `depth` and `slug` are **computed, not supplied**.

        The path is built from the parent and the chain of names, and rebuilt
        for every descendant on a move. Accepting it from the client means a
        tree written by someone who does not know its rules — and the first
        wrong path hides an entire branch from every tree query.
    """

    product_count = serializers.SerializerMethodField()
    path_label = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            "id",
            "slug",
            "parent",
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "image",
            "icon",
            "path",
            "path_label",
            "depth",
            "display_order",
            "is_active",
            "show_in_menu",
            "product_count",
        ]
        read_only_fields = ["id", "slug", "path", "depth"]

    def get_product_count(self, obj) -> int:
        return obj.products.count()

    def get_path_label(self, obj) -> str:
        """ "Medicines ← Painkillers" — for display in a flat select list."""
        parts, node, guard = [], obj, 0
        while node is not None and guard < 8:
            parts.append(node.name_ar)
            node = node.parent
            guard += 1
        return " ← ".join(reversed(parts))

    def validate_parent(self, value):
        """
        ⚠️  A category is not a parent of itself, nor of any of its ancestors.

            A cycle makes `_rebuild_path` call itself endlessly, hanging the
            request forever with no trace in any log.
        """
        instance = self.instance
        if value is None or instance is None:
            return value

        if value.pk == instance.pk:
            raise serializers.ValidationError("الفئة لا تكون أبًا لنفسها")

        if instance.path and value.path.startswith(f"{instance.path}/"):
            raise serializers.ValidationError("لا يمكن نقل فئة إلى داخل أحد فروعها")

        return value


class AdminManufacturerSerializer(serializers.ModelSerializer):
    brand_count = serializers.SerializerMethodField()

    class Meta:
        model = Manufacturer
        fields = [
            "id",
            "slug",
            "name_ar",
            "name_en",
            "country",
            "registration_number",
            "website",
            "logo",
            "is_active",
            "brand_count",
        ]
        read_only_fields = ["id", "slug"]

    def get_brand_count(self, obj) -> int:
        return obj.brands.count()


class AdminBrandSerializer(serializers.ModelSerializer):
    manufacturer_name = serializers.CharField(
        source="manufacturer.name_ar", read_only=True, default=""
    )
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Brand
        fields = [
            "id",
            "slug",
            "manufacturer",
            "manufacturer_name",
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "logo",
            "display_order",
            "is_featured",
            "is_active",
            "product_count",
        ]
        read_only_fields = ["id", "slug"]

    def get_product_count(self, obj) -> int:
        return obj.products.count()
