"""مسارات الدفع — /api/v1/payments/"""

from django.urls import path

from payments import api

app_name = "payments"

urlpatterns = [
    # ── العميل ─────────────────────────────────────────────
    # الطرق المتاحة تُحسب من البوابات المفعّلة الآن
    path("methods/", api.AvailableMethodsAPI.as_view(), name="methods"),
    # ── الأدمن: البوابات ───────────────────────────────────
    path("admin/adapters/", api.AdapterListAPI.as_view(), name="adapters"),
    path("admin/providers/", api.ProviderListCreateAPI.as_view(), name="providers"),
    path(
        "admin/providers/<uuid:pk>/",
        api.ProviderDetailAPI.as_view(),
        name="provider-detail",
    ),
    path(
        "admin/providers/<uuid:pk>/toggle/",
        api.ToggleProviderAPI.as_view(),
        name="provider-toggle",
    ),
    path(
        "admin/providers/reorder/",
        api.ReorderProvidersAPI.as_view(),
        name="providers-reorder",
    ),
    # بيانات الاعتماد — للكتابة فقط، لا تُقرأ (ADR-15)
    path(
        "admin/providers/<uuid:pk>/credentials/",
        api.ProviderCredentialsAPI.as_view(),
        name="provider-credentials",
    ),
    path(
        "admin/providers/<uuid:pk>/credentials/<uuid:credential_pk>/",
        api.ProviderCredentialDetailAPI.as_view(),
        name="provider-credential-detail",
    ),
    # ── الأدمن: المعاملات ──────────────────────────────────
    path("admin/transactions/", api.TransactionListAPI.as_view(), name="transactions"),
    path(
        "admin/transactions/<uuid:pk>/",
        api.TransactionDetailAPI.as_view(),
        name="transaction-detail",
    ),
    path(
        "admin/transactions/<uuid:pk>/capture/",
        api.CaptureTransactionAPI.as_view(),
        name="transaction-capture",
    ),
    path(
        "admin/transactions/<uuid:pk>/refund/",
        api.RefundAPI.as_view(),
        name="transaction-refund",
    ),
]
