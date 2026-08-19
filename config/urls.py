"""
Project URL routing.

The API structure mirrors domain boundaries — there is no single giant API module.
See docs/backend/08-API-CONVENTIONS.md
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

# ⚠️  The docs page itself is protected by IsAdminUser, and the default
#     authentication class is JWT alone — so a browser cannot even open it to
#     paste a token in. In development only we also accept the admin session so
#     the page opens after logging in at /admin/. The IsAdminUser permission
#     stays enforced as-is, and production remains JWT-only.
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
#  /api/v1/  — each endpoint is enabled in its own phase
# ═══════════════════════════════════════════════════════════
api_v1 = [
    # ── Visual identity — read before anything else on frontend load ──
    path("branding/", include("branding.urls")),
    # ── Identity ───────────────────────────────────────────
    path("auth/", include("accounts.urls")),
    path("customers/", include("customers.urls")),
    path("administration/", include("administration.urls")),
    # ── Access and catalog ─────────────────────────────────
    path("access/", include("access.urls")),
    path("catalog/", include("catalog.urls")),
    path("reviews/", include("reviews.urls")),
    path("academic/", include("academic.urls")),
    # ── Inventory and trade ────────────────────────────────
    path("inventory/", include("inventory.urls")),
    path("cart/", include("cart.urls")),
    path("orders/", include("orders.urls")),
    path("shipping/", include("shipping.urls")),
    path("payments/", include("payments.urls")),
    # ── Pricing and promotions — admin only ────────────────
    # ⚠️  Prices reach the customer already computed inside the product, cart and
    #     order, and coupons are validated in the cart. No public endpoint in either domain.
    path("pricing/", include("pricing.urls")),
    path("promotions/", include("promotions.urls")),
    # ── Notifications and email ────────────────────────────
    # ⚠️  `mailing` has no public endpoint: server and user names expose
    #     infrastructure and tell an attacker where to try passwords.
    path("notifications/", include("notifications.urls")),
    path("mailing/", include("mailing.urls")),
    # ── Point of sale ──────────────────────────────────────
    path("pos/", include("pos.urls")),
    # ── Finance ────────────────────────────────────────────
    path("finance/", include("finance.urls")),
    # ── B2B ────────────────────────────────────────────────
    path("b2b/", include("b2b.urls")),
    # ── Staff portal ───────────────────────────────────────
    path("employees/", include("employees.urls")),
    path("targets/", include("targets.urls")),
    path("commissions/", include("commissions.urls")),
    # ── Loyalty and referrals ──────────────────────────────
    path("loyalty/", include("loyalty.urls")),
    # ── Suppliers and reporting ────────────────────────────
    path("suppliers/", include("suppliers.urls")),
    path("reports/", include("reporting.urls")),
    path("analytics/", include("analytics.urls")),
    # ── Later ──────────────────────────────────────────────
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1, "api"), namespace="v1")),
    path("i18n/", include("django.conf.urls.i18n")),
    # ⚠️  Sitemaps live **at the root with no prefix** — crawlers request
    #     `/robots.txt` and `/sitemap.xml` literally. See seo/README.md
    path("", include("seo.urls")),
]

if settings.DEBUG:
    urlpatterns += [
        path("api/v1/docs/", schema_view.with_ui("swagger"), name="swagger"),
        path("api/v1/schema/", schema_view.without_ui(), name="schema"),
        path("__debug__/", include("debug_toolbar.urls")),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
