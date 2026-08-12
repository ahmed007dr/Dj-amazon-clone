"""
عقود الكتالوج.

⚠️  المحتوى يُرسَل **باللغتين دائمًا** (ADR-34) — لوحة الأدمن تعرض
    الاثنتين، وإرسال المترجم فقط يجبر على نداء ثانٍ.
"""

from rest_framework import serializers

from catalog.models import (
    Brand,
    Category,
    Manufacturer,
    Product,
    ProductImage,
    ProductVariant,
)


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
    التقييم المُجمَّع.

    ⚠️  يأتي من `select_related('rating')` — لا من حساب لحظي.
        الحساب اللحظي هو ما أنتج N+1 في النموذج القديم.
    """

    average = serializers.DecimalField(max_digits=3, decimal_places=2, read_only=True)
    count = serializers.IntegerField(read_only=True)
    distribution = serializers.DictField(read_only=True)


class ProductListSerializer(serializers.ModelSerializer):
    """
    بطاقة المنتج في القوائم.

    ⚠️  **بلا سعر نهائي وبلا كمية.**

        السعر يحسبه `pricing` حسب العميل، والتوفر يجيب عنه
        `inventory`. إضافتهما هنا تعني أن الكتالوج يجيب على
        سؤالين لا يملكهما.
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
        """يقرأ من `to_attr` الذي هيّأه الـ prefetch — بلا استعلام."""
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
            # الحقول الدوائية
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
        يقرأ الأبناء من الشجرة المبنية في الذاكرة — لا من قاعدة
        البيانات. التكرار على `obj.children.all()` هنا يعني استعلامًا
        لكل عقدة.
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
#  الأدمن
# ═══════════════════════════════════════════════════════════


class AdminProductSerializer(serializers.ModelSerializer):
    """
    نسخة الأدمن — كل الحقول قابلة للكتابة.

    ⚠️  `slug` للقراءة فقط: تغييره يكسر الروابط الخارجية وفهرسة
        محركات البحث. (ADR-27)
    """

    class Meta:
        model = Product
        exclude = ["deleted_at"]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]

    def validate(self, attrs):
        """
        ⚠️  اتساق الحقول التنظيمية.

        منتج مُعلَّم `requires_prescription` وتصنيفه `OTC` تناقض
        صامت — أحد الحقلين خاطئ، والخطأ يظهر عند أول مراجعة
        تنظيمية لا قبلها.
        """
        from catalog.models import ProductKind, RegulatoryClass

        instance = self.instance
        kind = attrs.get("kind", getattr(instance, "kind", None))
        regulatory = attrs.get("regulatory_class", getattr(instance, "regulatory_class", None))
        requires_rx = attrs.get(
            "requires_prescription", getattr(instance, "requires_prescription", False)
        )

        if requires_rx and regulatory in (
            RegulatoryClass.OTC,
            RegulatoryClass.NOT_APPLICABLE,
        ):
            raise serializers.ValidationError(
                {"regulatory_class": ("منتج يتطلب وصفة لا يكون تصنيفه OTC أو «لا ينطبق»")}
            )

        if kind == ProductKind.MEDICINE and regulatory == RegulatoryClass.NOT_APPLICABLE:
            raise serializers.ValidationError(
                {"regulatory_class": "الدواء يجب أن يحمل تصنيفًا تنظيميًا"}
            )

        return attrs
