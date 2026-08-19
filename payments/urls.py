"""Payment routes — /api/v1/payments/"""

from django.urls import path

from payments import api

app_name = "payments"

urlpatterns = [
    # ── Customer ───────────────────────────────────────────
    # The available methods are computed from the gateways enabled right now
    path("methods/", api.AvailableMethodsAPI.as_view(), name="methods"),
    # ── Gateways ───────────────────────────────────────────
    # ⚠️  One URL per gateway, not a single shared URL.
    #
    #     A shared URL would have needed the gateway inferred from the payload
    #     shape — a guess that fails silently when two gateways look alike or one changes a field.
    #     The code in the path makes the choice explicit, and allows handing a
    #     different URL to each gateway, as their panels require.
    #
    # ⚠️  And it is registered in the gateway's own panel — an endpoint the gateway
    #     cannot reach means orders left "processing" while the money is collected.
    path(
        "webhooks/<slug:provider_code>/",
        api.ProviderWebhookAPI.as_view(),
        name="webhook",
    ),
    # ── Admin: gateways ────────────────────────────────────
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
    # Credentials — write-only, never read (ADR-15)
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
    # ── Admin: transactions ────────────────────────────────
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
