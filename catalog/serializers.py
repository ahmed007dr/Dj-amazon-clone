"""
عقود الكتالوج.

⚠️  المحتوى يُرسَل **باللغتين دائمًا** (ADR-34) — لوحة الأدمن تعرض
    الاثنتين، وإرسال المترجم فقط يجبر على نداء ثانٍ.
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
        # ⚠️  الترتيب و«الرئيسية» تُحدَّدان من نقاط مخصّصة لا من الرفع.
        #
        #     السماح بإرسال `is_primary=True` مع الرفع يكسر القيد
        #     الفريد بدل أن ينقل الرئيسية، ويخرج للأدمن كخطأ ٥٠٠.
        read_only_fields = ["display_order", "is_primary"]

    def validate_image(self, value):
        """
        ⚠️  **الفحص هنا لا في الواجهة.**

            حدّ الحجم في `<input accept>` تلميح للمتصفح لا حاجز؛
            ورافع بـ curl لا يمرّ بالواجهة أصلًا.
        """
        # ⚠️  `ValidationError` من Django ليست نظيرتها من DRF.
        #
        #     تركها تصعد يجعل الرفض يخرج ٥٠٠ بدل ٤٠٠ برسالة —
        #     فيبدو الملف المرفوض عطلًا في الخادم.
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


# ═══════════════════════════════════════════════════════════
#  الأدمن — التصنيف المرجعي
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  هذه الثلاثة كانت تُدار من لوحة Django وحدها. وهي **شرط**
#      لإضافة أي منتج: الفئة إلزامية على `Product`، فمتجر بلا
#      شاشة فئات لا يستطيع إضافة صنفه الأول من لوحته.


class AdminCategorySerializer(serializers.ModelSerializer):
    """
    ⚠️  `path` و`depth` و`slug` **محسوبة لا مُدخَلة**.

        المسار يُبنى من الأب وسلسلة الأسماء، ويُعاد بناؤه لكل
        الأحفاد عند النقل. قبوله من العميل يعني شجرةً يكتبها من
        لا يعرف قواعدها — وأول مسار خاطئ يُخفي فرعًا كاملًا من كل
        استعلام شجري.
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
        """«أدوية ← مسكّنات» — لعرضها في قائمة اختيار مسطّحة."""
        parts, node, guard = [], obj, 0
        while node is not None and guard < 8:
            parts.append(node.name_ar)
            node = node.parent
            guard += 1
        return " ← ".join(reversed(parts))

    def validate_parent(self, value):
        """
        ⚠️  فئة لا تكون أبًا لنفسها ولا لأحد أجدادها.

            الدورة تجعل `_rebuild_path` تستدعي نفسها بلا نهاية،
            فيعلّق الطلب إلى الأبد بلا أثر في أي سجل.
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
