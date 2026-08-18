"""مسارات البريد — /api/v1/mailing/"""

from django.urls import path

from mailing import api

app_name = "mailing"

urlpatterns = [
    path("admin/accounts/", api.AccountListCreateAPI.as_view(), name="accounts"),
    path("admin/accounts/<uuid:pk>/", api.AccountDetailAPI.as_view(), name="account-detail"),
    path("admin/accounts/<uuid:pk>/verify/", api.VerifyAccountAPI.as_view(), name="account-verify"),
    path(
        "admin/accounts/<uuid:pk>/test-send/",
        api.TestSendAPI.as_view(),
        name="account-test-send",
    ),
    # ── المسؤوليات ─────────────────────────────────────────
    path("admin/routes/", api.RouteListCreateAPI.as_view(), name="routes"),
    path("admin/routes/<uuid:pk>/", api.RouteDetailAPI.as_view(), name="route-detail"),
    path("admin/routing/", api.RoutingMapAPI.as_view(), name="routing-map"),
    # ── الصادر ─────────────────────────────────────────────
    path("admin/outbox/", api.OutboxListAPI.as_view(), name="outbox"),
    path("admin/outbox/<uuid:pk>/retry/", api.RetryMessageAPI.as_view(), name="outbox-retry"),
    # ── القوالب ────────────────────────────────────────────
    # ⚠️  المفتاح نصّي لا UUID: هوية القالب اسمه (`password_reset`)
    #     وهو ثابت في الكود، بخلاف صفّ التجاوز الذي قد يُحذف ويُعاد.
    path("admin/templates/", api.TemplateListAPI.as_view(), name="templates"),
    path("admin/templates/<slug:key>/", api.TemplateDetailAPI.as_view(), name="template-detail"),
    path(
        "admin/templates/<slug:key>/preview/",
        api.TemplatePreviewAPI.as_view(),
        name="template-preview",
    ),
]
