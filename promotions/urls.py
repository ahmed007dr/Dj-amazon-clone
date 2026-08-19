"""
Coupon routes — /api/v1/promotions/

⚠️  **No public list**: exposing the coupons makes every visitor try the highest
    available discount instead of the code they were sent in their campaign. And
    validating a specific code happens in the cart, where the customer enters it.
"""

from django.urls import path

from promotions import api

app_name = "promotions"

urlpatterns = [
    path("admin/coupons/", api.CouponListCreateAPI.as_view(), name="coupons"),
    path("admin/coupons/<uuid:pk>/", api.CouponDetailAPI.as_view(), name="coupon-detail"),
    # The redemption log — read-only
    path("admin/redemptions/", api.CouponRedemptionListAPI.as_view(), name="redemptions"),
]
