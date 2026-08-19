"""
Local development settings.

    DJANGO_SETTINGS_MODULE=config.settings.dev
"""

from .base import *
from .base import ALLOWED_HOSTS, CORS_ALLOWED_ORIGINS, INSTALLED_APPS, MIDDLEWARE, env

DEBUG = env.bool("DJANGO_DEBUG", default=True)

# ⚠️  These three names are added to the host derived from
#     `PUBLIC_API_DOMAIN`; they do not replace it.
#
#     A developer opens `localhost` one moment and `127.0.0.1` the next — two
#     distinct hosts to the browser, even though it is the same machine.
ALLOWED_HOSTS = list(dict.fromkeys([*ALLOWED_HOSTS, "localhost", "127.0.0.1", "[::1]"]))


# ── Debug toolbar — development environment only ───────────
# Shipping it in production leaks internal information

INSTALLED_APPS += ["debug_toolbar"]
MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")


# ── Developer tooling — development environment only ───────
# ⚠️  `seed_dev` creates accounts with a well-known, published password.
#
#     Leaving the app uninstalled in production makes the command **not exist**
#     there — stronger than an `if DEBUG` check inside it, because a single
#     wrong environment variable flips a check but cannot conjure a command.

INSTALLED_APPS += ["devtools"]


# ── CORS — Vite dev server ─────────────────────────────────
# ⚠️  The frontend runs on another port, so every call from it is cross-origin.
#
#     Without this the browser silently blocks **every** response — a 200 arrives
#     from the server and the browser refuses to hand it to the code. The error
#     shows in the browser console, not the Django log, so it is hunted for in the wrong place.
#
#     Development only. Production stays on the origin derived from the site domain.
#
# ⚠️  The twin is added here too: `localhost` and `127.0.0.1` are the same machine
#     but two different origins to the browser. A developer who opens one while
#     the setting names the other sees every call blocked, with not one line in the Django log.

_CORS_TWINS = {"localhost": "127.0.0.1", "127.0.0.1": "localhost"}

CORS_ALLOWED_ORIGINS = list(
    dict.fromkeys(
        [
            *CORS_ALLOWED_ORIGINS,
            *(
                origin.replace(host, twin, 1)
                for origin in CORS_ALLOWED_ORIGINS
                for host, twin in _CORS_TWINS.items()
                if f"//{host}" in origin
            ),
        ]
    )
)

INTERNAL_IPS = ["127.0.0.1"]


# ── Email ──────────────────────────────────────────────────
# Default: print to the terminal instead of sending for real

EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)


# ⚠️  Password validators stay complete, exactly as in production.
#     Relaxing them here opens a gap between environments that hides bugs until deployment.
