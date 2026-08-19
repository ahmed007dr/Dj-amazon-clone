"""Visual identity contracts."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from branding.contrast import audit_palette
from branding.models import BrandProfile, ThemePalette
from core.files import ALLOWED_IMAGE_TYPES, validate_upload


class ThemePaletteSerializer(serializers.ModelSerializer):
    """
    ⚠️  `contrast` is read-only and recomputed on every display.

        Storing it means a number going silently stale at the first colour edit.
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
        ⚠️  The model's `clean()` does not run automatically through DRF.

            Calling it explicitly here is what makes the contrast check a real
            guard rather than code nothing ever reaches.
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


#: The five identity assets — all images uploaded from the panel
ASSET_FIELDS = ("logo_light", "logo_dark", "icon", "favicon", "og_image")

#: ⚠️  Smaller than the product image limit: the logo is downloaded on **every**
#:     page by every visitor. A two-megabyte file slows the whole site, not one product page.
MAX_ASSET_SIZE = 2 * 1024 * 1024


class BrandProfileSerializer(serializers.ModelSerializer):
    palettes = ThemePaletteSerializer(many=True, read_only=True)

    # ⚠️  `allow_null` is what makes **clearing** possible.
    #
    #     The default field silently ignores an empty value coming from a
    #     multipart form — it returns 200 and leaves the image in place. So the
    #     admin presses "delete", sees success, and the logo has not changed.
    #
    #     Uploading stays `multipart`; clearing is JSON with a `null` value.
    logo_light = serializers.ImageField(required=False, allow_null=True)
    logo_dark = serializers.ImageField(required=False, allow_null=True)
    icon = serializers.ImageField(required=False, allow_null=True)
    favicon = serializers.ImageField(required=False, allow_null=True)
    og_image = serializers.ImageField(required=False, allow_null=True)

    def update(self, instance, validated_data):
        """
        ⚠️  `None` ← the empty string.

            The `ImageField` column is not nullable (`blank`, not `null`), so
            passing `None` through raises a database error on save. And the
            empty string is Django's representation of "no image".
        """
        for field in ASSET_FIELDS:
            if field in validated_data and validated_data[field] is None:
                validated_data[field] = ""

        return super().update(instance, validated_data)

    def _validate_asset(self, value):
        """
        ⚠️  **The check is on the file signature, not on its header.**

            `content_type` comes from the client and is forged in one line. And
            identity assets are served from the site's own origin, so an SVG
            file carrying a script becomes a hole for every visitor — more
            dangerous than its counterpart in product images, because the logo
            appears on every page.

        ⚠️  And these fields used to have **no check at all** while product
            images were checked — a disparity nothing justified.
        """
        # A field left untouched arrives as text, not a file — there is nothing to check
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
    ⚠️  The public payload **does not resemble the model**.

        The frontend needs a ready-made token map (`--color-primary: #...`),
        not field names. Building it in the frontend duplicates the token names
        in two places, so adding a colour becomes two edits in two repositories.
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
