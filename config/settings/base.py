"""
Settings shared across every environment.

⚠️  Never put a secret in this file. Every sensitive value is read from environment variables.
    See .env.example
"""

from pathlib import Path

import environ

from config import environment

# BASE_DIR = .../src
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

# ⚠️  **The secrets file is chosen by the switch, not by name.**
#
#     `config/environment.py` decides whether this is development or production,
#     and that one decision picks the settings module, the domain **and** the
#     file opened here. A single `.env` serving both meant the production
#     password sat on the development machine; separate files make the wrong one
#     *absent* rather than merely unselected.
#
# ⚠️  **The first file wins.**
#
#     `read_env` never replaces a value already present in the environment — nor
#     one read by an earlier file. The order below is exactly the precedence ladder:
#
#         the real process environment  >  .env.<environment>  >  .env (legacy)
#
#     This is the reverse of what a reader usually expects (that the last one
#     wins), so it is stated explicitly: the container overrides both files.
#
#     `.env` is read last as a fallback so a machine that has not yet split its
#     secrets keeps working — it never overrides the environment-specific file.
environ.Env.read_env(BASE_DIR / environment.SECRETS_FILE)
environ.Env.read_env(BASE_DIR / ".env")


# ═══════════════════════════════════════════════════════════
#  Domain — one source both sides derive from (ADR-73 · ADR-74)
# ═══════════════════════════════════════════════════════════
# ⚠️  The domain is written once in `config/environment.py`, and the frontend
#     reads **the same file** (`web/vite.config.ts` parses it directly).
#
#     Before this the domain was spread over five values across two files:
#     `DJANGO_ALLOWED_HOSTS` (host without scheme), `CORS_ALLOWED_ORIGINS`
#     (full origin), `FRONTEND_BASE_URL` (the frontend), `CSRF_TRUSTED_ORIGINS`
#     and `VITE_API_BASE_URL` (the server). Four shapes for one thing means
#     forgetting one produces a **silent** failure — deriving them makes
#     forgetting impossible rather than merely rare.
#
# ⚠️  The source moved here from `.env.public`; the derivation below is unchanged.
#
#     `.env.public` was a file edited by hand per environment, which made
#     switching a matter of remembering to edit it. The switch is now one boolean
#     that also picks the settings module and the secrets file — so the three
#     cannot disagree. **That file is gone**: leaving it readable would let a
#     stale `PUBLIC_SITE_DOMAIN=localhost` silently outrank the block below,
#     because an environment variable beats a default.
#
# ⚠️  Explicit overrides stay possible: every derived value below accepts an
#     environment variable that outranks it, for the cases that fall outside the
#     pattern (a second domain · a CDN · a load balancer forwarding an internal host).

_ACTIVE = environment.ACTIVE

PUBLIC_SCHEME = env("PUBLIC_SCHEME", default=_ACTIVE["SCHEME"])
PUBLIC_SITE_DOMAIN = env("PUBLIC_SITE_DOMAIN", default=_ACTIVE["SITE_DOMAIN"])
PUBLIC_API_DOMAIN = env("PUBLIC_API_DOMAIN", default=_ACTIVE["API_DOMAIN"])
PUBLIC_API_PREFIX = env("PUBLIC_API_PREFIX", default=_ACTIVE["API_PREFIX"])
PUBLIC_MEDIA_ORIGIN = env("PUBLIC_MEDIA_ORIGIN", default=_ACTIVE["MEDIA_ORIGIN"])
PUBLIC_DEFAULT_LOCALE = env("PUBLIC_DEFAULT_LOCALE", default=_ACTIVE["DEFAULT_LOCALE"])

#: Hosts and origins beyond the two domains — `www`, the LAN address, spare Vite ports
PUBLIC_EXTRA_HOSTS = _ACTIVE["EXTRA_HOSTS"]
PUBLIC_EXTRA_ORIGINS = _ACTIVE["EXTRA_ORIGINS"]


def _origin(domain: str) -> str:
    """`shop.example.com` ← `https://shop.example.com`"""
    return f"{PUBLIC_SCHEME}://{domain}"


def _hostname(domain: str) -> str:
    """
    ⚠️  `ALLOWED_HOSTS` matches on the host alone — a port in it breaks the match.

    ⚠️  And a bracketed IPv6 literal is returned untouched.

        `[::1]` is all colons and no port; splitting on the last one yields
        `[:` — a host that matches nothing, added silently to `ALLOWED_HOSTS`.
    """
    if domain.startswith("["):
        return domain.split("]")[0] + "]"

    return domain.rsplit(":", 1)[0] if ":" in domain else domain


#: The site a human visits — email links and the sitemap are built from it
SITE_ORIGIN = _origin(PUBLIC_SITE_DOMAIN)

#: The API server
API_ORIGIN = _origin(PUBLIC_API_DOMAIN)

#: Media origin — follows the server unless a CDN is set explicitly
MEDIA_ORIGIN = PUBLIC_MEDIA_ORIGIN or API_ORIGIN


# ═══════════════════════════════════════════════════════════
#  Security
# ═══════════════════════════════════════════════════════════

SECRET_KEY = env("DJANGO_SECRET_KEY")

# The default is safe — environments that need debugging enable it explicitly
DEBUG = env.bool("DJANGO_DEBUG", default=False)

#: Production marker — read by the startup checks in `core/checks.py`.
#:
#: ⚠️  **Not derived from `DEBUG`.**
#:
#:     `DEBUG=False` is a legitimate state outside production: the test runner
#:     forces it, and developers enable it to exercise production behaviour
#:     locally. Tying the "domain is not localhost" and "scheme is https" checks
#:     to it was failing the tests on a configuration that was perfectly correct.
#:
#: ⚠️  It now follows the switch in `config/environment.py`. `prod.py` still
#:     asserts `True` explicitly, so an operator who names the production
#:     settings module gets the strict checks whatever the switch says.
IS_PRODUCTION = environment.IS_PRODUCTION

# ⚠️  The site domain is listed alongside the server domain.
#
#     `seo/` serves `robots.txt` and `sitemap.xml` at the **root**, because a
#     crawler requests them literally from the domain a human visits. Any proxy
#     forwarding them to Django arrives with a `Host` header carrying the site
#     domain — so its absence here returns 400 for the crawler's two requests
#     alone, a fault nobody notices until the pages vanish from search results.
#
# ⚠️  `EXTRA_HOSTS` carries what the two domains do not imply: `www` in
#     production, and `localhost`/`127.0.0.1`/a LAN address in development.
#     Ports are stripped here — `ALLOWED_HOSTS` matches on the host alone.
ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=list(
        dict.fromkeys(
            [
                _hostname(PUBLIC_API_DOMAIN),
                _hostname(PUBLIC_SITE_DOMAIN),
                *(_hostname(host) for host in PUBLIC_EXTRA_HOSTS),
            ]
        )
    ),
)


# ═══════════════════════════════════════════════════════════
#  Applications
# ═══════════════════════════════════════════════════════════

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_yasg",
    "corsheaders",
]

# ⚠️  The order mirrors the layer diagram in docs/backend/02-DEPENDENCIES.md
#     Dependencies only point downwards — enforced by import-linter in CI
LOCAL_APPS = [
    # L0 — Infrastructure
    "core",
    "branding",
    # ⚠️  `mailing` sits beside `branding`: it depends on `core` alone and knows no
    #     business domain. `accounts` is above it because it sends activation email.
    "mailing",
    # L1 — Identity
    "accounts",
    # L1.5 — Access policies: depend on accounts only, consumed by everyone
    "access",
    # ⚠️  `analytics` is a sibling of `access`, above `accounts`.
    #
    #     It measures traffic and classifies devices via `accounts.services`, and
    #     knows no business domain: store, cart and order are all "an HTTP request".
    #     Placing it higher would have stopped `administration` reading the visitor count.
    "analytics",
    # L2 — Personas and base domains
    "customers",
    "administration",
    "academic",
    "catalog",
    "shipping",
    # L3
    "pricing",
    "inventory",
    "reviews",
    # L4 → L6
    "promotions",
    # payments below orders — the order calls payment, not the reverse
    "payments",
    "cart",
    "orders",
    # consumer only — no domain imports it
    "notifications",
    # ⚠️  Cross-domain operational commands — **installed in production**.
    #     Unlike `devtools`, which stays in the development environment alone.
    "ops",
    # ⚠️  Sitemaps combine `catalog` and `academic` and filter them through `access` —
    #     and neither of those domains may import the other.
    "seo",
    # ⚠️  Point of sale is a **channel**, not a parallel system: every sale produces
    #     an `Order` with `channel=POS`. Above `orders` because it calls it.
    "pos",
    # ⚠️  Finance **listens and is never called**: it picks up revenue from `orders`
    #     events and states, and computes cost from `inventory` movements.
    #     No business domain imports it.
    "finance",
    # ⚠️  B2B above `orders`: credit terms charge the order to the customer account
    #     and issue its invoice. `orders` does not know it exists.
    "b2b",
    # ⚠️  `employees` above `customers`: assignment is owned by the upper side
    #     (ADR-12), and `customers` knows nothing at all about employees.
    "employees",
    # ⚠️  Targets above `employees`, and commissions above both targets and `finance`:
    #     commission on profit needs the cost of goods sold.
    "targets",
    "commissions",
    # ⚠️  Loyalty above both `orders` and `promotions`: it listens for order
    #     completion to award points, and issues a **coupon** on redemption instead
    #     of touching the cart or the order — both of which sit below it.
    "loyalty",
    # ⚠️  `suppliers` above `inventory` and `catalog`: receiving creates a batch
    #     through `inventory.services.receive`, never by writing directly.
    "suppliers",
    # ⚠️  `reporting` **reads and never writes** — no models, no migrations.
    #     The top layer: it knows everyone and nobody knows it.
    "reporting",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTH_USER_MODEL = "accounts.User"


# ═══════════════════════════════════════════════════════════
#  Middleware
# ═══════════════════════════════════════════════════════════
# ⚠️  The order is deliberate:
#     CorsMiddleware before CommonMiddleware (required by the package)
#     LanguageMiddleware after authentication — it needs request.user to read the preference

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.LanguageMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # ⚠️  **Last on purpose** — measurement runs on the finished response.
    #
    #     Response middleware runs in reverse order, so this position makes it the
    #     first to see the final response with its correct status code. Putting it at
    #     the top would have counted requests rejected by CORS or CSRF as real usage.
    "analytics.middleware.TrafficMiddleware",
]


# ═══════════════════════════════════════════════════════════
#  CORS — the frontend is a separate app (ADR-03)
# ═══════════════════════════════════════════════════════════

#: The only allowed origin — derived from the site domain, not written beside it
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=list(dict.fromkeys([SITE_ORIGIN, *PUBLIC_EXTRA_ORIGINS])),
)

# ⚠️  Both the site **and the server** belong in the CSRF trusted origins.
#
#     The Django admin is served from the server domain and relies on the session
#     and the token together; dropping it makes every save under `/admin/` fail
#     with 403 behind an HTTPS proxy.
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=list(dict.fromkeys([SITE_ORIGIN, API_ORIGIN, *PUBLIC_EXTRA_ORIGINS])),
)

CORS_ALLOW_CREDENTIALS = True
# ⚠️  Every custom header the server reads **must** be listed here.
#
#     An unlisted header makes the browser reject the request at the preflight
#     stage — the call never reaches Django at all, and nothing shows up in its
#     log. The developer hunts for the fault in the server while it is in the
#     browser.
#
#     The ones listed below are read by: cart/api.py · access/preview.py
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-language",
    "authorization",
    "content-type",
    "idempotency-key",
    "x-requested-with",
    # Guest cart — before registration
    "x-cart-session",
    # Admin preview mode (read-only · audited)
    "x-preview-as",
    "x-preview-verified",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"


# ═══════════════════════════════════════════════════════════
#  Templates
# ═══════════════════════════════════════════════════════════
# Removed entirely in phase 0.5 (SPA decision)

# Templates serve the Django admin only — the presentation layer was removed (SPA decision · ADR-03)
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ═══════════════════════════════════════════════════════════
#  Database
# ═══════════════════════════════════════════════════════════
# Moves to PostgreSQL in phase 0.5

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}


# ═══════════════════════════════════════════════════════════
#  Authentication
# ═══════════════════════════════════════════════════════════

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    "accounts.backend.EmailOrPhoneBackend",
]


# ═══════════════════════════════════════════════════════════
#  REST Framework
# ═══════════════════════════════════════════════════════════

REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "core.api.pagination.DefaultCursorPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # Checks suspension on every request — layer 3 of ADR-16
        "accounts.authentication.StatefulJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "EXCEPTION_HANDLER": "core.api.exception_handler.custom_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "COERCE_DECIMAL_TO_STRING": True,  # Money as a string, not a number (ADR-31)
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%SZ",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/minute",
        "user": "300/minute",
        # Authentication endpoints — tight limits that block guessing
        "login": "5/minute",
        "register": "3/hour",
        "password_reset": "3/hour",
        # ⚠️  Gateway events — a separate and higher scope.
        #
        #     The guard here is the signature, not the counter. A low limit drops a
        #     genuine spike, and every lost event is a paid order nobody knows was
        #     paid. Keeping it apart from `anon` also stops a busy gateway from
        #     consuming the visitor quota and taking store browsing down with it.
        "webhook": "600/minute",
    },
}


# ═══════════════════════════════════════════════════════════
#  JWT
# ═══════════════════════════════════════════════════════════
# Short-lived access token + rotation + blacklist — layers 1 and 2 of the
# session-revocation mechanism on suspension. Layer 3 (Redis set) in phase 2.

from datetime import timedelta

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}


# ═══════════════════════════════════════════════════════════
#  Cache
# ═══════════════════════════════════════════════════════════
# Without REDIS_URL it falls back to local memory — development does not break when Redis is absent

_redis_url = env("REDIS_URL", default="")

if _redis_url:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _redis_url,
        },
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "medical-commerce-locmem",
        },
    }


# ═══════════════════════════════════════════════════════════
#  Language and time
# ═══════════════════════════════════════════════════════════

# ⚠️  The default language is written once in `config/environment.py` and read by
#     both sides: the server here, and the frontend through `VITE_DEFAULT_LOCALE`.
#     Two separate values meant a server answering in Arabic and a frontend
#     starting in English — a contradiction visible on the very first page load.
LANGUAGE_CODE = env("LANGUAGE_CODE", default=PUBLIC_DEFAULT_LOCALE)
TIME_ZONE = env("TIME_ZONE", default="Africa/Cairo")

USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("ar", "Arabic"),
    ("en", "English"),
]

LOCALE_PATHS = [BASE_DIR / "locale"]


# ═══════════════════════════════════════════════════════════
#  Static files and media
# ═══════════════════════════════════════════════════════════

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"


# ═══════════════════════════════════════════════════════════
#  Email
# ═══════════════════════════════════════════════════════════
# ⚠️  Credentials come from the environment exclusively. No password in the code.

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@example.com")


# ═══════════════════════════════════════════════════════════
#  Configurable business rules
# ═══════════════════════════════════════════════════════════
# Moves to core/settings as database-backed settings (phase 1)

# Currency
DEFAULT_CURRENCY = env("DEFAULT_CURRENCY", default="EGP")
CURRENCY_DECIMAL_PLACES = env.int("CURRENCY_DECIMAL_PLACES", default=2)

# Tax — configurable, never hard-coded
TAX_ENABLED = env.bool("TAX_ENABLED", default=True)
TAX_DEFAULT_RATE = env("TAX_DEFAULT_RATE", default="14.00")
TAX_PRICES_INCLUDE_TAX = env.bool("TAX_PRICES_INCLUDE_TAX", default=False)


# ═══════════════════════════════════════════════════════════
#  Frontend
# ═══════════════════════════════════════════════════════════
# ⚠️  Derived from `PUBLIC_SITE_DOMAIN` — no literal value.
#
#     Its default used to be `localhost:3000`, a leftover from the Next.js era,
#     while the Vite server listens on 5173. And because it is the source of
#     email links and the sitemap (`seo/sitemaps.py`), the wrong default produced
#     dead activation links and a sitemap pointing at a port nobody was on —
#     without a single error in any log.
FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", default=SITE_ORIGIN)


# ═══════════════════════════════════════════════════════════
#  Sitemaps
# ═══════════════════════════════════════════════════════════
# ⚠️  The default is **off**.
#
#     An indexed staging environment competes with the real site for the same
#     keywords and exposes test data as though it were products. Off-by-default
#     makes forgetting to configure it a safe mistake; the reverse makes
#     it a silent marketing disaster.

SEO_INDEXING_ENABLED = env.bool("SEO_INDEXING_ENABLED", default=False)


# ═══════════════════════════════════════════════════════════
#  Encryption
# ═══════════════════════════════════════════════════════════
# For payment gateway credentials stored in the database (phase 5)

FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="")


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# drf-yasg — disable the legacy compatibility renderers
SWAGGER_USE_COMPAT_RENDERERS = False
