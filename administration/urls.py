"""مسارات بوابة الأدمن — /api/v1/administration/"""

from django.urls import path

from administration import api, tax_api

app_name = "administration"

urlpatterns = [
    # الحسابات
    path("accounts/", api.AccountListAPI.as_view(), name="accounts"),
    path("accounts/<uuid:pk>/", api.AccountDetailAPI.as_view(), name="account-detail"),
    path(
        "accounts/<uuid:pk>/suspend/",
        api.SuspendAccountAPI.as_view(),
        name="account-suspend",
    ),
    path(
        "accounts/<uuid:pk>/activate/",
        api.ActivateAccountAPI.as_view(),
        name="account-activate",
    ),
    path(
        "accounts/<uuid:pk>/status-history/",
        api.AccountStatusHistoryAPI.as_view(),
        name="account-status-history",
    ),
    # المراقبة
    path("online-now/", api.OnlineNowAPI.as_view(), name="online-now"),
    path(
        "accounts/<uuid:pk>/sessions/",
        api.AccountSessionsAPI.as_view(),
        name="account-sessions",
    ),
    path(
        "accounts/<uuid:pk>/activity/",
        api.AccountActivityAPI.as_view(),
        name="account-activity",
    ),
    path("audit-log/", api.AuditLogListAPI.as_view(), name="audit-log"),
    # ── الضريبة — نسبة متغيّرة · فئات معفاة · إيقاف كلي ────
    path("tax/settings/", tax_api.TaxSettingsAPI.as_view(), name="tax-settings"),
    path("tax/classes/", tax_api.TaxClassListCreateAPI.as_view(), name="tax-classes"),
    path(
        "tax/classes/<uuid:pk>/",
        tax_api.TaxClassDetailAPI.as_view(),
        name="tax-class-detail",
    ),
    path(
        "tax/classes/<uuid:pk>/set-default/",
        tax_api.SetDefaultTaxClassAPI.as_view(),
        name="tax-class-set-default",
    ),
]
