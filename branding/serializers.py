"""عقود الهوية البصرية."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from branding.contrast import audit_palette
from branding.models import BrandProfile, ThemePalette


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


class BrandProfileSerializer(serializers.ModelSerializer):
    palettes = ThemePaletteSerializer(many=True, read_only=True)

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
