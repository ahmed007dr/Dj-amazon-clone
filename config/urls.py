"""
Project URL routing.

The API structure mirrors domain boundaries — there is no single giant API module.
See docs/backend/08-API-CONVENTIONS.md
"""

import re

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView
from django.views.static import serve
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
    # ⚠️  The path comes from `ADMIN_URL` in the secrets file, not from a literal.
    #
    #     `/admin/` is the first path every credential-stuffing bot tries. Moving
    #     it is obscurity and nothing more — the login and the permissions behind
    #     it are what actually protect the panel — but it costs nothing and takes
    #     the door off the list.
    #
    #     ⚠️  This is **Django's** admin, served from the API domain. `/admin` on
    #         the site domain is the React portal and is untouched by this.
    path(f"{settings.ADMIN_URL}/", admin.site.urls),
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


# ═══════════════════════════════════════════════════════════
#  Media — served by Django, minus the private tree
# ═══════════════════════════════════════════════════════════
# ⚠️  `static()` returns an empty list when DEBUG is off, so media used to be
#     unreachable in production. One domain means Passenger owns everything and
#     no web server sits in front of the files — so the route is unconditional here.
#
# ⚠️  **And `private/` and `mail/` are excluded in the pattern itself.**
#
#     Customer verification documents, expense invoices and inbound mail
#     attachments are served through a signed URL with a five-minute life and an
#     ownership check (`customers/api.py`), reading from disk. Serving the whole
#     of MEDIA_ROOT here would have handed every one of them to anyone who knows
#     the path — turning a protected download into a public one while every
#     screen kept working exactly as before.
#
#     The negative lookahead is the boundary. It lives in the URLconf rather than
#     in `.htaccess` because a rule in the application cannot be lost by a
#     careless upload.
urlpatterns += [
    re_path(
        r"^media/(?!private/|mail/)(?P<path>.*)$",
        serve,
        {"document_root": settings.MEDIA_ROOT},
    ),
]


# ═══════════════════════════════════════════════════════════
#  The React application — last, and it must stay last
# ═══════════════════════════════════════════════════════════
# ⚠️  React Router owns the paths a human types, and the server knows none of
#     them. Without this, `/cart` works while navigating inside the app and
#     returns 404 on refresh or on a pasted link — a fault that appears for the
#     visitor and never for the developer.
#
# ⚠️  The exclusions are what keep Django's own routes reachable.
#
#     A bare catch-all would swallow `/api/v1/` and the admin, and the API would
#     answer every call with the HTML of the home page — a "200 OK" that breaks
#     every request, which is far harder to read than a 404.
#
# ⚠️  `ADMIN_URL` is interpolated, not written literally: the admin path comes
#     from the environment, so a hard-coded `admin/` here would exclude the wrong
#     path the moment it is changed, and lock the panel behind the SPA.
#
# ⚠️  Not to be confused with React's own `/admin` — that is the twenty-one-screen
#     admin portal, and it is *meant* to fall through to this rule.
_DJANGO_PREFIXES = "|".join(
    [
        r"api/",
        rf"{re.escape(settings.ADMIN_URL)}/",
        r"i18n/",
        r"media/",
        r"static/",
        r"robots\.txt",
        r"sitemap\.xml",
    ]
)

urlpatterns += [
    re_path(
        rf"^(?!{_DJANGO_PREFIXES}).*$",
        TemplateView.as_view(template_name="index.html"),
        name="react-app",
    ),
]
