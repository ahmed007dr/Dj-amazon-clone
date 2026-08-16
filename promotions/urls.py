"""
مسارات الكوبونات — /api/v1/promotions/

⚠️  **لا قائمة عامة**: كشف الكوبونات يجعل كل زائر يجرّب أعلى خصم
    متاح بدل الكود الذي وصله في حملته. والتحقق من كود بعينه يقع
    في السلة حيث يُدخله العميل.
"""

from django.urls import path

from promotions import api

app_name = "promotions"

urlpatterns = [
    path("admin/coupons/", api.CouponListCreateAPI.as_view(), name="coupons"),
    path("admin/coupons/<uuid:pk>/", api.CouponDetailAPI.as_view(), name="coupon-detail"),
    # سجل الصرف — للقراءة فقط
    path("admin/redemptions/", api.CouponRedemptionListAPI.as_view(), name="redemptions"),
]
