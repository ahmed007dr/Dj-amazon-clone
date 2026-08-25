"""
Catalogue contracts.

⚠️  Content is sent **in both languages always** (ADR-34) — the admin panel
    displays both, and sending only the translated one forces a second call.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from catalog.models import (
    Brand,
    Category,
    Manufacturer,
    Product,
    ProductImage,
    ProductVariant,
)
from core.files import ALLOWED_IMAGE_TYPES, MAX_IMAGE_SIZE, validate_upload


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
        ]
        # ⚠️  Ordering and "primary" are set from dedicated endpoints, not on upload.
        #
        #     Allowing `is_primary=True` to be sent with the upload breaks the
        #     unique constraint instead of moving the primary, and reaches the admin as a 500.
        read_only_fields = ["display_order", "is_primary"]

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


class ProductListSerializer(serializers.ModelSerializer):
    """
    The product card in lists.

    ⚠️  **No final price and no quantity.**

        `pricing` computes the price per customer, and `inventory` answers
        availability. Adding them here means the catalogue answering two
        questions it does not own.
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
    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    rating = serializers.SerializerMethodField()

    class Meta(ProductListSerializer.Meta):
        fields = [
            *ProductListSerializer.Meta.fields,
            "description_ar",
            "description_en",
            "manufacturer",
            "images",
            "variants",
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
    """

    class Meta:
        model = Product
        exclude = ["deleted_at"]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]

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
        if errors:
            raise serializers.ValidationError(errors)

        return attrs


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
