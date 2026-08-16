"""
مسارات التسعير — /api/v1/pricing/

⚠️  **كلها تحت `admin/` وكلها للأدمن.**

    السعر يصل العميل محسوبًا داخل المنتج والسلة والطلب؛ ولا نقطة
    عامة هنا. كشف قوائم الأسعار يعطي المنافس هيكل تسعيرك كاملًا.
"""

from django.urls import path

from pricing import api

app_name = "pricing"

urlpatterns = [
    # قوائم الأسعار
    path("admin/lists/", api.PriceListListCreateAPI.as_view(), name="lists"),
    path("admin/lists/<uuid:pk>/", api.PriceListDetailAPI.as_view(), name="list-detail"),
    # قواعد التسعير — سعر منتج في قائمة بكمية دنيا
    path("admin/rules/", api.PriceRuleListCreateAPI.as_view(), name="rules"),
    path("admin/rules/<uuid:pk>/", api.PriceRuleDetailAPI.as_view(), name="rule-detail"),
    # الخصومات الترويجية — تظهر في الكتالوج بلا كود
    path("admin/overrides/", api.PriceOverrideListCreateAPI.as_view(), name="overrides"),
    path(
        "admin/overrides/<uuid:pk>/",
        api.PriceOverrideDetailAPI.as_view(),
        name="override-detail",
    ),
]
