"""Visual identity contracts."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from branding import channels
from branding.contrast import audit_palette
from branding.models import BrandProfile, ChannelKind, ContactChannel, ThemePalette
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


#: The identity assets — all images uploaded from the panel
ASSET_FIELDS = (
    "logo_light",
    "logo_dark",
    "icon",
    "favicon",
    "og_image",
    "hero_image_light",
    "hero_image_dark",
)

#: ⚠️  Smaller than the product image limit: the logo is downloaded on **every**
#:     page by every visitor. A two-megabyte file slows the whole site, not one product page.
MAX_ASSET_SIZE = 2 * 1024 * 1024

#: ⚠️  The home banner is the one asset that is genuinely a photograph: 1920 px wide at a
#:     sensible JPEG quality is already a megabyte or two. It is only downloaded by visitors
#:     who open the home page, and only one of the two (the one for their theme) — so the
#:     ceiling is higher than a logo's, and still a ceiling.
MAX_HERO_SIZE = 5 * 1024 * 1024

#: Per-field overrides of `MAX_ASSET_SIZE`
ASSET_MAX_SIZE = {
    "hero_image_light": MAX_HERO_SIZE,
    "hero_image_dark": MAX_HERO_SIZE,
}


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
    hero_image_light = serializers.ImageField(required=False, allow_null=True)
    hero_image_dark = serializers.ImageField(required=False, allow_null=True)

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

    def _validate_asset(self, value, field_name: str = ""):
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
                max_size=ASSET_MAX_SIZE.get(field_name, MAX_ASSET_SIZE),
            )
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages) from error

        return value

    # ⚠️  One thin wrapper per field rather than `validate_<f> = _validate_asset`: DRF calls
    #     `validate_<field>(value)` and does not say which field, and the hero images have a
    #     different ceiling from the logos.
    def validate_logo_light(self, value):
        return self._validate_asset(value, "logo_light")

    def validate_logo_dark(self, value):
        return self._validate_asset(value, "logo_dark")

    def validate_icon(self, value):
        return self._validate_asset(value, "icon")

    def validate_favicon(self, value):
        return self._validate_asset(value, "favicon")

    def validate_og_image(self, value):
        return self._validate_asset(value, "og_image")

    def validate_hero_image_light(self, value):
        return self._validate_asset(value, "hero_image_light")

    def validate_hero_image_dark(self, value):
        return self._validate_asset(value, "hero_image_dark")

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
            "hero_image_light",
            "hero_image_dark",
            "hero_title_ar",
            "hero_title_en",
            "hero_subtitle_ar",
            "hero_subtitle_en",
            "hero_cta_label_ar",
            "hero_cta_label_en",
            "hero_cta_url",
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
    hero = serializers.DictField(read_only=True)
    default_mode = serializers.CharField(read_only=True)
    tokens = serializers.DictField(read_only=True)
    palettes = serializers.DictField(read_only=True)
    contact = serializers.DictField(read_only=True)
    social = serializers.DictField(read_only=True)
    contact_channels = serializers.ListField(child=serializers.DictField(), read_only=True)


def _channel_errors(error: channels.ChannelValidationError) -> serializers.ValidationError:
    """`ChannelValidationError` → DRF field errors, keeping each error's stable `code`."""
    return serializers.ValidationError(
        {field: [ErrorDetail(err.message, code=err.code)] for field, err in error.errors.items()}
    )


class ContactChannelSerializer(serializers.ModelSerializer):
    """
    The admin's view of a channel: the editable fields plus what they resolve to.

    ⚠️  `display` / `href` / `label` are **recomputed on every read**, never stored —
        a stored link goes stale the first time the rules change.
    """

    display = serializers.SerializerMethodField()
    href = serializers.SerializerMethodField()
    href_en = serializers.SerializerMethodField()
    label = serializers.SerializerMethodField()

    class Meta:
        model = ContactChannel
        fields = [
            "id",
            "kind",
            "value",
            "label_ar",
            "label_en",
            "message_ar",
            "message_en",
            "display_order",
            "is_active",
            "show_floating_button",
            "display",
            "href",
            "href_en",
            "label",
        ]
        read_only_fields = ["id"]
        extra_kwargs = {
            # ⚠️  Length and emptiness of `value` are `branding.channels`'s to judge, so the
            #     refusal carries a stable code and a bilingual message like every other one.
            "value": {"allow_blank": True, "max_length": 2000},
            # A new channel goes to the end unless told otherwise — see `create()`
            "display_order": {"required": False},
        }

    def _described(self, obj) -> dict:
        try:
            return obj.describe()
        except channels.ChannelError:
            # A row that predates a stricter rule shows as unreadable instead of 500-ing the list
            return {"display": "", "href": "", "href_en": ""}

    def get_display(self, obj) -> str:
        return self._described(obj)["display"]

    def get_href(self, obj) -> str:
        return self._described(obj)["href"]

    def get_href_en(self, obj) -> str:
        return self._described(obj)["href_en"]

    def get_label(self, obj) -> dict:
        return obj.label

    def validate(self, attrs):
        """
        ⚠️  The rules depend on `kind` *and* `value` together, so they run on the
            merged state — a PATCH that changes only the kind re-checks the old value
            against the new kind instead of saving a Telegram row holding a phone number.
        """
        instance = self.instance
        defaults = {
            "kind": "",
            "value": "",
            "label_ar": "",
            "label_en": "",
            "message_ar": "",
            "message_en": "",
            "show_floating_button": False,
        }
        merged = {
            field: attrs.get(field, getattr(instance, field, default))
            for field, default in defaults.items()
        }
        try:
            cleaned = channels.clean_channel(**merged)
        except channels.ChannelValidationError as error:
            raise _channel_errors(error) from error

        # The canonical values replace what was typed, so the response (and the row)
        # carry `201012345678`, not `010 1234 5678`
        return {**attrs, **cleaned}

    def create(self, validated_data):
        profile = self.context["profile"]
        if "display_order" not in validated_data:
            last = (
                ContactChannel.objects.filter(profile=profile)
                .order_by("-display_order")
                .values_list("display_order", flat=True)
                .first()
            )
            validated_data["display_order"] = 0 if last is None else last + 1
        return ContactChannel.objects.create(profile=profile, **validated_data)


class ChannelPreviewSerializer(serializers.Serializer):
    """What the "add channel" form sends on every pause in typing — nothing is saved."""

    kind = serializers.ChoiceField(choices=ChannelKind.choices)
    value = serializers.CharField(allow_blank=True, required=False, default="", max_length=2000)
    message_ar = serializers.CharField(allow_blank=True, required=False, default="")
    message_en = serializers.CharField(allow_blank=True, required=False, default="")


class ChannelReorderSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
