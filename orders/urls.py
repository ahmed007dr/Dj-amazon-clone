"""Order routes — /api/v1/orders/"""

from django.urls import path

from orders import api

app_name = "orders"

urlpatterns = [
    # Customer — the identifier is a UUID, not the order number (ADR-25 · ADR-29)
    path("", api.MyOrderListAPI.as_view(), name="my-orders"),
    path("checkout/", api.CheckoutAPI.as_view(), name="checkout"),
    path("<uuid:pk>/", api.MyOrderDetailAPI.as_view(), name="detail"),
    path("<uuid:pk>/cancel/", api.CancelOrderAPI.as_view(), name="cancel"),
    # Admin
    path("admin/", api.AdminOrderListAPI.as_view(), name="admin-orders"),
    path("admin/<uuid:pk>/", api.AdminOrderDetailAPI.as_view(), name="admin-detail"),
    path(
        "admin/<uuid:pk>/transition/",
        api.AdminTransitionAPI.as_view(),
        name="admin-transition",
    ),
    path(
        "admin/<uuid:pk>/complete/",
        api.AdminCompleteOrderAPI.as_view(),
        name="admin-complete",
    ),
]
