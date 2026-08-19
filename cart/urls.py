"""Cart routes — /api/v1/cart/"""

from django.urls import path

from cart import api

app_name = "cart"

urlpatterns = [
    path("", api.CartDetailAPI.as_view(), name="detail"),
    path("lines/", api.CartLinesAPI.as_view(), name="lines"),
    path("lines/<uuid:pk>/", api.CartLineDetailAPI.as_view(), name="line-detail"),
    path("coupon/", api.CartCouponAPI.as_view(), name="coupon"),
    path("bundle/", api.CartBundleAPI.as_view(), name="bundle"),
    path("merge/", api.CartMergeAPI.as_view(), name="merge"),
]
