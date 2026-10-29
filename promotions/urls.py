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
    # ⚠️  Literal segments before `<uuid:pk>`: the converter would not match them anyway,
    #     but the order keeps that true if the converter is ever loosened.
    path("admin/coupons/bulk/", api.CouponBulkCreateAPI.as_view(), name="coupons-bulk"),
    path(
        "admin/coupons/analytics/",
        api.CouponAnalyticsOverviewAPI.as_view(),
        name="coupons-analytics",
    ),
    path("admin/coupons/<uuid:pk>/", api.CouponDetailAPI.as_view(), name="coupon-detail"),
    path(
        "admin/coupons/<uuid:pk>/analytics/",
        api.CouponAnalyticsDetailAPI.as_view(),
        name="coupon-analytics",
    ),
    path("admin/coupons/<uuid:pk>/orders/", api.CouponOrdersAPI.as_view(), name="coupon-orders"),
    path(
        "admin/coupons/<uuid:pk>/customers/",
        api.CouponCustomersAPI.as_view(),
        name="coupon-customers",
    ),
    # The redemption log — read-only
    path("admin/redemptions/", api.CouponRedemptionListAPI.as_view(), name="redemptions"),
]
