"""مسارات الموردين — /api/v1/suppliers/"""

from django.urls import path

from suppliers import api

app_name = "suppliers"

urlpatterns = [
    path("", api.SupplierListCreateAPI.as_view(), name="list"),
    # ── العروض — أساس Marketplace ──────────────────────────
    # ⚠️  قبل `<uuid:pk>/` عمدًا: المسارات الثابتة تسبق المتغيّرة
    #     وإلا التقط `<uuid:pk>` ما ليس معرّفًا.
    path("offers/", api.SupplierOfferListCreateAPI.as_view(), name="offers"),
    path("offers/<uuid:pk>/", api.SupplierOfferDetailAPI.as_view(), name="offer-detail"),
    path("products/<uuid:pk>/offers/", api.ProductOffersAPI.as_view(), name="product-offers"),
    path("reorder-suggestions/", api.ReorderSuggestionsAPI.as_view(), name="reorder"),
    # ── أوامر الشراء ───────────────────────────────────────
    path("orders/", api.PurchaseOrderListAPI.as_view(), name="orders"),
    path("orders/create/", api.CreatePurchaseOrderAPI.as_view(), name="order-create"),
    path("orders/<uuid:pk>/", api.PurchaseOrderDetailAPI.as_view(), name="order-detail"),
    path("orders/<uuid:pk>/send/", api.SendPurchaseOrderAPI.as_view(), name="order-send"),
    path(
        "orders/<uuid:pk>/receive/",
        api.ReceivePurchaseOrderAPI.as_view(),
        name="order-receive",
    ),
    path("orders/<uuid:pk>/cancel/", api.CancelPurchaseOrderAPI.as_view(), name="order-cancel"),
    # ── المورّد المفرد ─────────────────────────────────────
    path("<uuid:pk>/", api.SupplierDetailAPI.as_view(), name="detail"),
    path("<uuid:pk>/statement/", api.SupplierStatementAPI.as_view(), name="statement"),
    path("<uuid:pk>/payments/", api.SupplierPaymentAPI.as_view(), name="payments"),
    path("<uuid:pk>/ledger/", api.SupplierLedgerAPI.as_view(), name="ledger"),
]
