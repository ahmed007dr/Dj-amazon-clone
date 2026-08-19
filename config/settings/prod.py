"""
Production settings.

    DJANGO_SETTINGS_MODULE=config.settings.prod

⚠️  Every variable here is mandatory. A missing one halts startup on purpose —
    better than booting silently with an insecure configuration.
"""

from .base import *
from .base import env

DEBUG = False

#: Enables the strict domain checks in `core/checks.py`
IS_PRODUCTION = True

# ⚠️  The domains are **mandatory here, with no default** — absence halts startup.
#
#     `base.py` gives them development defaults (`localhost`) so the development
#     environment boots without configuration. Those are exactly the values
#     production must never boot with: a real server with
#     `ALLOWED_HOSTS = ["localhost"]` returns 400 to every visitor, and with a
#     `localhost` origin in CORS the browser blocks every response. The value read
#     here is never used — the point is to fail startup now instead of
#     failing the site after deployment.
#
#     `ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS`
#     stay derived from them in `base.py` — they are not repeated here.
env("PUBLIC_SITE_DOMAIN")
env("PUBLIC_API_DOMAIN")

# ⚠️  Encryption key for gateway credentials — **mandatory here**.
#
#     The empty default in `base.py` serves development and testing. In
#     production its absence means either rejecting every gateway-key save or —
#     if we were lenient — payment keys stored as plaintext in a real database.
#     Halting startup is cheaper than either.
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY")


# ═══════════════════════════════════════════════════════════
#  HTTPS hardening
# ═══════════════════════════════════════════════════════════

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)  # one year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# ⚠️  `CSRF_TRUSTED_ORIGINS` is derived in `base.py` from the site and server
#     domains. It used to live here with an empty default and appeared in no
#     environment template — meaning the default state of production was an
#     admin panel answering 403 to every save behind an HTTPS proxy.


# ═══════════════════════════════════════════════════════════
#  Logging
# ═══════════════════════════════════════════════════════════

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {process:d} {thread:d} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("DJANGO_LOG_LEVEL", default="INFO"),
    },
    "loggers": {
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
