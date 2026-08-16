"""عقود الهوية البصرية."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from branding.contrast import audit_palette
from branding.models import BrandProfile, ThemePalette
from core.files import ALLOWED_IMAGE_TYPES, validate_upload


class ThemePaletteSerializer(serializers.ModelSerializer):
    """
    ⚠️  `contrast` للقراءة فقط ويُحسب عند كل عرض.

        تخزينه يعني رقمًا يتقادم بصمت عند أول تعديل لون.
    """

    contrast = serializers.SerializerMethodField()

    class Meta:
        model = ThemePalette
        fields = [
            "id",
            "mode",
            "primary",
            "on_primary",
            "secondary",
            "accent",
            "success",
            "warning",
            "danger",
            "info",
            "bg",
            "surface",
            "border",
            "text",
            "text_muted",
            "contrast",
        ]
        read_only_fields = ["id", "mode"]

    def get_contrast(self, obj) -> list:
        return audit_palette(obj)

    def validate(self, attrs):
        """
        ⚠️  `clean()` في الموديل لا يعمل تلقائيًا عبر DRF.

            استدعاؤه صراحةً هنا هو ما يجعل فحص التباين حارسًا فعليًا
            بدل أن يكون كودًا لا يمرّ به شيء.
        """
        instance = self.instance
        candidate = ThemePalette(
            **{
                field: attrs.get(field, getattr(instance, field, None))
                for field in self.Meta.fields
                if field not in {"id", "contrast"}
            }
        )
        candidate.profile_id = getattr(instance, "profile_id", None)

        try:
            candidate.clean()
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error

        return attrs


#: أصول الهوية الخمسة — كلها صور تُرفَع من اللوحة
ASSET_FIELDS = ("logo_light", "logo_dark", "icon", "favicon", "og_image")

#: ⚠️  أصغر من حد صور المنتجات: اللوجو يُحمَّل في **كل** صفحة لكل
#:     زائر. ملف بحجمين ميجابايت يبطئ الموقع كله لا صفحة منتج.
MAX_ASSET_SIZE = 2 * 1024 * 1024


class BrandProfileSerializer(serializers.ModelSerializer):
    palettes = ThemePaletteSerializer(many=True, read_only=True)

    # ⚠️  `allow_null` هو ما يجعل **المسح** ممكنًا.
    #
    #     الحقل الافتراضي يتجاهل القيمة الفارغة القادمة من نموذج
    #     متعدد الأجزاء بصمت — يعيد ٢٠٠ ويُبقي الصورة مكانها. فيضغط
    #     الأدمن «حذف» ويرى نجاحًا واللوجو لم يتغيّر.
    #
    #     والرفع يبقى `multipart`؛ أما المسح فـ JSON بقيمة `null`.
    logo_light = serializers.ImageField(required=False, allow_null=True)
    logo_dark = serializers.ImageField(required=False, allow_null=True)
    icon = serializers.ImageField(required=False, allow_null=True)
    favicon = serializers.ImageField(required=False, allow_null=True)
    og_image = serializers.ImageField(required=False, allow_null=True)

    def update(self, instance, validated_data):
        """
        ⚠️  `None` ← سلسلة فارغة.

            عمود `ImageField` غير قابل لـ `NULL` (`blank` لا `null`)،
            فتمرير `None` كما هو يرفع خطأ قاعدة بيانات عند الحفظ.
            والسلسلة الفارغة هي تمثيل «لا صورة» في Django.
        """
        for field in ASSET_FIELDS:
            if field in validated_data and validated_data[field] is None:
                validated_data[field] = ""

        return super().update(instance, validated_data)

    def _validate_asset(self, value):
        """
        ⚠️  **الفحص على توقيع الملف لا على ترويسته.**

            `content_type` يأتي من العميل ويُزوَّر بسطر واحد. وأصول
            الهوية تُقدَّم من أصل الموقع نفسه، فملف SVG يحمل نصًا
            برمجيًا يصير ثغرة على كل زائر — وهي أخطر من نظيرتها في
            صور المنتجات لأن اللوجو يظهر في كل صفحة.

        ⚠️  وكانت هذه الحقول **بلا أي فحص** بينما صور المنتجات
            مفحوصة — تفاوت لا يبرّره شيء.
        """
        # الحقل المتروك كما هو يصل نصًّا لا ملفًا — لا شيء يُفحص
        if not hasattr(value, "size"):
            return value

        try:
            validate_upload(
                value,
                allowed_types=ALLOWED_IMAGE_TYPES,
                max_size=MAX_ASSET_SIZE,
            )
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages) from error

        return value

    validate_logo_light = _validate_asset
    validate_logo_dark = _validate_asset
    validate_icon = _validate_asset
    validate_favicon = _validate_asset
    validate_og_image = _validate_asset

    class Meta:
        model = BrandProfile
        fields = [
            "id",
            "code",
            "name_ar",
            "name_en",
            "tagline_ar",
            "tagline_en",
            "logo_light",
            "logo_dark",
            "icon",
            "favicon",
            "og_image",
            "font_ar",
            "font_en",
            "font_size_base",
            "radius",
            "shadow_level",
            "default_mode",
            "contact_email",
            "contact_phone",
            "whatsapp",
            "address_ar",
            "address_en",
            "facebook",
            "instagram",
            "x_twitter",
            "linkedin",
            "youtube",
            "tiktok",
            "is_active",
            "palettes",
        ]
        read_only_fields = ["id", "is_active"]


class PublicThemeSerializer(serializers.Serializer):
    """
    ⚠️  الحمولة العامة **لا تشبه الموديل**.

        الفرونت يحتاج خريطة رموز جاهزة (`--color-primary: #...`)
        لا أسماء حقول. بناؤها في الواجهة يكرّر أسماء الرموز في
        مكانين، فتصير إضافة لون تعديلين في مستودعين.
    """

    code = serializers.CharField(read_only=True)
    name = serializers.DictField(read_only=True)
    tagline = serializers.DictField(read_only=True)
    assets = serializers.DictField(read_only=True)
    default_mode = serializers.CharField(read_only=True)
    tokens = serializers.DictField(read_only=True)
    palettes = serializers.DictField(read_only=True)
    contact = serializers.DictField(read_only=True)
    social = serializers.DictField(read_only=True)
