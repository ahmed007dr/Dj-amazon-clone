"""Visual identity admin panel."""

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from branding.models import BrandProfile, ContactChannel, ThemePalette
from core.admin import DeletedListFilter, DomainModelAdmin, TimeStampedAdmin


class ThemePaletteInline(admin.StackedInline):
    model = ThemePalette
    extra = 0
    max_num = 2  # light and dark, no more
    readonly_fields = ("created_at", "updated_at")


class ContactChannelInline(admin.TabularInline):
    """
    ⚠️  Saved through `ContactChannel.clean()`, so a hostile link is refused here exactly
        as it is by the API.
    """

    model = ContactChannel
    extra = 0
    fields = (
        "kind",
        "value",
        "label_ar",
        "label_en",
        "message_ar",
        "message_en",
        "display_order",
        "is_active",
        "show_floating_button",
    )


@admin.register(BrandProfile)
class BrandProfileAdmin(DomainModelAdmin):
    list_display = ("code", "name_ar", "default_mode", "contact_email", "is_active", "is_deleted")
    list_filter = ("is_active", "default_mode", DeletedListFilter)
    search_fields = ("code", "name_ar", "name_en", "contact_email")
    ordering = ("-is_active", "code")
    inlines = (ThemePaletteInline, ContactChannelInline)

    fieldsets = (
        (None, {"fields": ("id", "code", "name_ar", "name_en", "is_active")}),
        (_("الشعار"), {"fields": ("tagline_ar", "tagline_en")}),
        (_("الصور"), {"fields": ("logo_light", "logo_dark", "icon", "favicon", "og_image")}),
        (
            _("واجهة الصفحة الرئيسية"),
            {
                "fields": (
                    "hero_image_light",
                    "hero_image_dark",
                    "hero_title_ar",
                    "hero_title_en",
                    "hero_subtitle_ar",
                    "hero_subtitle_en",
                    "hero_cta_label_ar",
                    "hero_cta_label_en",
                    "hero_cta_url",
                )
            },
        ),
        (
            _("الطباعة والشكل"),
            {
                "fields": (
                    "font_ar",
                    "font_en",
                    "font_size_base",
                    "radius",
                    "shadow_level",
                    "default_mode",
                )
            },
        ),
        (
            _("التواصل"),
            {"fields": ("contact_email", "contact_phone", "whatsapp", "address_ar", "address_en")},
        ),
        (
            _("الشبكات الاجتماعية"),
            {
                "classes": ("collapse",),
                "fields": ("facebook", "instagram", "x_twitter", "linkedin", "youtube", "tiktok"),
            },
        ),
        (_("تواريخ"), {"fields": ("created_at", "updated_at", "deleted_at")}),
    )


@admin.register(ThemePalette)
class ThemePaletteAdmin(TimeStampedAdmin):
    list_display = ("profile", "mode", "primary", "secondary", "accent", "bg")
    list_filter = ("mode", "profile")
    list_select_related = ("profile",)
    search_fields = ("profile__code", "profile__name_ar")


@admin.register(ContactChannel)
class ContactChannelAdmin(TimeStampedAdmin):
    list_display = (
        "profile",
        "kind",
        "value",
        "display_order",
        "is_active",
        "show_floating_button",
    )
    list_filter = ("kind", "is_active", "profile")
    list_select_related = ("profile",)
    search_fields = ("value", "label_ar", "label_en", "profile__code")
    ordering = ("profile", "display_order")
