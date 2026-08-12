"""
مسارات المشروع.

بنية الـ API تعكس حدود النطاقات — لا وحدة API عملاقة واحدة.
انظر docs/backend/08-API-CONVENTIONS.md
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

schema_view = get_schema_view(
    openapi.Info(
        title="Medical Commerce Platform API",
        default_version="v1",
        description="واجهة برمجية لمنصة التجارة الطبية",
    ),
    public=False,
    permission_classes=(permissions.IsAdminUser,),
)

# ═══════════════════════════════════════════════════════════
#  /api/v1/  — تُفعَّل كل نقطة في مرحلتها
# ═══════════════════════════════════════════════════════════
api_v1 = [
    path("auth/", include("accounts.urls")),
    # path('branding/',       include('branding.urls')),        المرحلة ١.٥
    # path('customers/',      include('customers.urls')),       المرحلة ١
    # path('administration/', include('administration.urls')),  المرحلة ٢
    # path('catalog/',        include('catalog.urls')),         المرحلة ٣
    # path('reviews/',        include('reviews.urls')),         المرحلة ٣
    # path('inventory/',      include('inventory.urls')),       المرحلة ٤
    # path('pricing/',        include('pricing.urls')),         المرحلة ٥
    # path('promotions/',     include('promotions.urls')),      المرحلة ٥
    # path('cart/',           include('cart.urls')),            المرحلة ٥
    # path('orders/',         include('orders.urls')),          المرحلة ٥
    # path('shipping/',       include('shipping.urls')),        المرحلة ٥
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1, "api"), namespace="v1")),
    path("i18n/", include("django.conf.urls.i18n")),
]

if settings.DEBUG:
    urlpatterns += [
        path("api/v1/docs/", schema_view.with_ui("swagger"), name="swagger"),
        path("api/v1/schema/", schema_view.without_ui(), name="schema"),
        path("__debug__/", include("debug_toolbar.urls")),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
