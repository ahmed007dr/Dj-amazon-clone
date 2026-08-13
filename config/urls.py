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
from rest_framework.authentication import SessionAuthentication
from rest_framework.settings import api_settings

# ⚠️  صفحة التوثيق نفسها محمية بـ IsAdminUser، وفئة التوثيق الافتراضية
#     هي JWT وحدها — فالمتصفح لا يستطيع فتحها أصلًا ليلصق فيها توكنًا.
#     في التطوير فقط نقبل جلسة لوحة الإدارة حتى تُفتح الصفحة بعد
#     تسجيل الدخول في /admin/. الصلاحية IsAdminUser تبقى مفروضة كما هي،
#     والإنتاج يبقى على JWT وحده.
_schema_auth = list(api_settings.DEFAULT_AUTHENTICATION_CLASSES)
if settings.DEBUG:
    _schema_auth.append(SessionAuthentication)

schema_view = get_schema_view(
    openapi.Info(
        title="Medical Commerce Platform API",
        default_version="v1",
        description="واجهة برمجية لمنصة التجارة الطبية",
    ),
    public=False,
    authentication_classes=_schema_auth,
    permission_classes=(permissions.IsAdminUser,),
)

# ═══════════════════════════════════════════════════════════
#  /api/v1/  — تُفعَّل كل نقطة في مرحلتها
# ═══════════════════════════════════════════════════════════
api_v1 = [
    # ── الهوية البصرية — يُقرأ قبل أي شيء آخر عند تحميل الواجهة ──
    path("branding/", include("branding.urls")),
    # ── الهوية ─────────────────────────────────────────────
    path("auth/", include("accounts.urls")),
    path("customers/", include("customers.urls")),
    path("administration/", include("administration.urls")),
    # ── الوصول والكتالوج ───────────────────────────────────
    path("access/", include("access.urls")),
    path("catalog/", include("catalog.urls")),
    path("reviews/", include("reviews.urls")),
    path("academic/", include("academic.urls")),
    # ── المخزون والتجارة ───────────────────────────────────
    path("inventory/", include("inventory.urls")),
    path("cart/", include("cart.urls")),
    path("orders/", include("orders.urls")),
    path("shipping/", include("shipping.urls")),
    path("payments/", include("payments.urls")),
    # ── الإشعارات ──────────────────────────────────────────
    path("notifications/", include("notifications.urls")),
    # ── لاحقًا ─────────────────────────────────────────────
    # path("pos/",      include("pos.urls")),           المرحلة ٧
    # path("finance/",  include("finance.urls")),       المرحلة ٨
    # path("employees/", include("employees.urls")),    المرحلة ١٠
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
