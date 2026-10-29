
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
    "SCHEME": "https",
    "SITE_DOMAIN": "med-box.net",
    "API_DOMAIN": "med-box.net",
    "API_PREFIX": "/api/v1",
    "MEDIA_ORIGIN": "",
    "DEFAULT_LOCALE": "ar",
    "EXTRA_HOSTS": ["www.med-box.net"],
    "EXTRA_ORIGINS": ["https://www.med-box.net"],
}


# ═══════════════════════════════════════════════════════════
#  Derived — read by settings, manage.py, wsgi and vite
# ═══════════════════════════════════════════════════════════

ACTIVE = PRODUCTION if IS_PRODUCTION else DEVELOPMENT
SETTINGS_MODULE = "config.settings.prod" if IS_PRODUCTION else "config.settings.dev"
SECRETS_FILE = ".env.production" if IS_PRODUCTION else ".env.development"
