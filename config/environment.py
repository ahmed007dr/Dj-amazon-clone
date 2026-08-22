"""
The environment switch — development or production, decided on one line.

    IS_PRODUCTION = True   →  development
    IS_PRODUCTION = True    →  production

⚠️  **This file carries no secret and never will.**

    It is committed to Git, so anything written here is public to everyone with
    repository access. Passwords, keys and connection strings live in
    `.env.development` / `.env.production`, which are never committed.

⚠️  **One line, three consequences.** The switch below decides all of:

        1. which settings module boots   (`config.settings.dev` / `.prod`)
        2. which secrets file is read    (`.env.development` / `.env.production`)
        3. which domain both sides use   (the blocks below)

    They used to be three independent decisions — a settings module chosen by an
    environment variable, a secrets file chosen by filename, and a domain chosen
    by editing `.env.public`. Three switches means a deployment where two agree
    and the third does not: production settings reading development secrets, or
    a frontend built for one domain talking to a server answering on another.
    Neither writes a line to any log.

⚠️  **The frontend reads this very file.**

    `web/vite.config.ts` parses it directly, so the domain is written once for
    Django and Vite alike. See ADR-73 · ADR-74 — the principle is unchanged,
    only its source moved here from `.env.public`.

⚠️  And the values below are **defaults, not commands**.

    Every one stays overridable by a real environment variable
    (`PUBLIC_SITE_DOMAIN`, `DJANGO_ALLOWED_HOSTS`, …) for the cases outside the
    pattern: a second domain, a CDN, a load balancer forwarding an internal
    host. See `config/settings/base.py`.
"""

# ═══════════════════════════════════════════════════════════
#  ⇩⇩⇩  THE SWITCH  ⇩⇩⇩
# ═══════════════════════════════════════════════════════════

# IS_PRODUCTION = True    # production
IS_PRODUCTION = False  # development


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
    # ⚠️  `localhost` and `127.0.0.1` are the same machine and two different
    #     hosts to the browser. A developer who opens one while the setting
    #     names the other gets 400 with nothing in the Django log.
    #
    #     A LAN address belongs here too when testing from a real phone on the
    #     same Wi-Fi — the phone cannot reach `127.0.0.1`.
    "EXTRA_HOSTS": ["localhost", "127.0.0.1", "[::1]"],
    # ⚠️  Vite moves to the next free port when 5173 is taken, and the browser
    #     then blocks every response while the server reports 200 — the error
    #     surfaces in the browser console, never in the Django log.
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
    #: The site a human visits — the built frontend on public_html
    "SITE_DOMAIN": "med-box.net",
    #: The Django server — its own cPanel subdomain
    "API_DOMAIN": "api.med-box.net",
    "API_PREFIX": "/api/v1",
    # ⚠️  Set explicitly, because media sits under `public_html` — the *site*
    #     domain, not the server's. Leaving it empty makes every image be
    #     requested from `api.med-box.net` while the file is on `med-box.net`.
    "MEDIA_ORIGIN": "https://med-box.net",
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
