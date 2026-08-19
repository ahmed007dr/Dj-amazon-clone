"""Point-of-sale routes — /api/v1/pos/"""

from django.urls import path

from pos import api

app_name = "pos"

urlpatterns = [
    # ── Cashier ────────────────────────────────────────────
    path("registers/", api.RegisterListAPI.as_view(), name="registers"),
    path("session/", api.MySessionAPI.as_view(), name="session"),
    path("session/open/", api.OpenSessionAPI.as_view(), name="session-open"),
    path("session/close/", api.CloseSessionAPI.as_view(), name="session-close"),
    path("session/cash/", api.SessionCashAPI.as_view(), name="session-cash"),
    path("products/", api.POSProductSearchAPI.as_view(), name="products"),
    path("quote/", api.QuoteAPI.as_view(), name="quote"),
    path("checkout/", api.CheckoutAPI.as_view(), name="checkout"),
    path("refund/", api.POSRefundAPI.as_view(), name="refund"),
    # ── Admin ──────────────────────────────────────────────
    path("admin/registers/", api.AdminRegisterListCreateAPI.as_view(), name="admin-registers"),
    path(
        "admin/registers/<uuid:pk>/",
        api.AdminRegisterDetailAPI.as_view(),
        name="admin-register-detail",
    ),
    path("admin/sessions/", api.AdminSessionListAPI.as_view(), name="admin-sessions"),
    path(
        "admin/sessions/<uuid:pk>/",
        api.AdminSessionDetailAPI.as_view(),
        name="admin-session-detail",
    ),
]
