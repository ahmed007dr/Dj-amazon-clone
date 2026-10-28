"""Visual identity routes — /api/v1/branding/"""

from django.urls import path

from branding import api

app_name = "branding"

urlpatterns = [
    # ── Public ─────────────────────────────────────────────
    path("theme/", api.PublicThemeAPI.as_view(), name="theme"),
    # ── Admin ──────────────────────────────────────────────
    path("admin/profiles/", api.ProfileListCreateAPI.as_view(), name="profiles"),
    path("admin/profiles/<uuid:pk>/", api.ProfileDetailAPI.as_view(), name="profile-detail"),
    path(
        "admin/profiles/<uuid:pk>/activate/",
        api.ActivateProfileAPI.as_view(),
        name="profile-activate",
    ),
    path(
        # ⚠️  `uuid`, not `int` — no sequential id in any URL
        "admin/profiles/<uuid:pk>/palettes/<uuid:palette_pk>/",
        api.PaletteDetailAPI.as_view(),
        name="palette-detail",
    ),
    path("admin/preview/", api.PreviewThemeAPI.as_view(), name="preview"),
    # ── Contact channels (⚠️  `uuid`, never `int`) ──────────
    path(
        "admin/profiles/<uuid:pk>/contact-channels/",
        api.ChannelListCreateAPI.as_view(),
        name="channels",
    ),
    path(
        "admin/profiles/<uuid:pk>/contact-channels/reorder/",
        api.ChannelReorderAPI.as_view(),
        name="channels-reorder",
    ),
    path(
        "admin/profiles/<uuid:pk>/contact-channels/<uuid:channel_pk>/",
        api.ChannelDetailAPI.as_view(),
        name="channel-detail",
    ),
    path(
        "admin/profiles/<uuid:pk>/contact-channels/<uuid:channel_pk>/toggle/",
        api.ChannelToggleAPI.as_view(),
        name="channel-toggle",
    ),
    path(
        "admin/contact-channels/preview/",
        api.ChannelPreviewAPI.as_view(),
        name="channel-preview",
    ),
]
