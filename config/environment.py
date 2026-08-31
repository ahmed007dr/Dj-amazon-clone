
# ═══════════════════════════════════════════════════════════
#  ⇩⇩⇩  THE SWITCH  ⇩⇩⇩
# ═══════════════════════════════════════════════════════════

IS_PRODUCTION = True    # production
#IS_PRODUCTION = False  # development


# ═══════════════════════════════════════════════════════════
#  Development
# ═══════════════════════════════════════════════════════════

DEVELOPMENT = {
    "SCHEME": "http",
    #: The Vite dev server — the port is part of the origin the browser sees
    "SITE_DOMAIN": "localhost:5173",
    #: The Django dev server
    "API_DOMAIN": "127.0.0.1:8000",
    "API_PREFIX": "/api/v1",
    #: Empty = media follows the API server
    "MEDIA_ORIGIN": "",
    "DEFAULT_LOCALE": "ar",
    
    "EXTRA_HOSTS": ["localhost", "127.0.0.1", "[::1]"],
    
    "EXTRA_ORIGINS": [
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
    ],
}


# ═══════════════════════════════════════════════════════════
#  Production — med-box.net
# ═══════════════════════════════════════════════════════════

PRODUCTION = {
    # ⚠️  `https` is mandatory: `core/checks.py` refuses to boot on `http` in
    #     production, because the access token would cross the network in clear.
    "SCHEME": "https",
    # ⚠️  **One domain serves both sides.** There is no `api.` subdomain.
    #
    #     The two names below are deliberately identical: Django and the React
    #     build live at the same origin, and the prefix is what separates them.
    #
    #         med-box.net/              → React
    #         med-box.net/api/v1/       → Django REST
    #         med-box.net/<ADMIN_URL>/  → Django admin
    #
    #     The derivation in `base.py` is unchanged — it simply resolves both to
    #     the same origin, which makes CORS a same-origin case and removes a
    #     whole class of silent browser-side failures.
    "SITE_DOMAIN": "med-box.net",
    "API_DOMAIN": "med-box.net",
    "API_PREFIX": "/api/v1",
    # ⚠️  Empty on purpose now: media follows the API origin, and the API origin
    #     *is* the site origin. Naming it again would be a second copy of one value.
    "MEDIA_ORIGIN": "",
    "DEFAULT_LOCALE": "ar",
    # ⚠️  `www` is a different host to Django, and its absence returns 400 —
    #     for the crawler's `robots.txt` request among others.
    "EXTRA_HOSTS": ["www.med-box.net"],
    "EXTRA_ORIGINS": ["https://www.med-box.net"],
}


# ═══════════════════════════════════════════════════════════
#  Derived — read by settings, manage.py, wsgi and vite
# ═══════════════════════════════════════════════════════════

#: The active block
ACTIVE = PRODUCTION if IS_PRODUCTION else DEVELOPMENT

#: The settings module — read by `manage.py`, `config/wsgi.py`, `passenger_wsgi.py`
SETTINGS_MODULE = "config.settings.prod" if IS_PRODUCTION else "config.settings.dev"

# ⚠️  Two files, never one shared file with the environment appended.
#
#     A single `.env` holding both meant the production password sat on the
#     development machine, and a careless switch pointed a local run at the real
#     database. Separate files make the wrong one *absent*, not merely unselected.
SECRETS_FILE = ".env.production" if IS_PRODUCTION else ".env.development"
