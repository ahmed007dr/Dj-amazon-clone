"""
Domain configuration checks — at startup, not after deployment.

⚠️  **The problem this solves**: every domain misconfiguration is silent at the server.

    An origin missing from CORS makes the browser block the response after the
    server has returned a perfectly good 200; a host missing from
    `ALLOWED_HOSTS` returns 400 for the crawler's requests alone; and a
    `localhost` domain in production makes email activation links point at the
    recipient's own machine. Not one of them writes a line to the Django log,
    and all of them are discovered after deployment — or after the pages vanish
    from search results.

    The check moves them to before deployment: `manage.py check` fails, so the
    server never boots at all.

⚠️  And the strict checks are tied to `IS_PRODUCTION`, not to `DEBUG`.

    `DEBUG=False` is a legitimate state in tests and development, and tying them
    to it was failing an environment that was entirely correct in place.
"""

from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, Warning, register
from django.http.request import validate_host

#: A tag allowing them to be run alone: `manage.py check --tag domain`
DOMAIN = "domain"

#: Names unfit to be the domain of a server facing the world
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}  # noqa: S104


def _hostname(domain: str) -> str:
    """⚠️  A bracketed IPv6 literal is all colons and no port — `[::1]` split on
    the last one yields `[:`, a host that matches nothing."""
    if domain.startswith("["):
        return domain.split("]")[0] + "]"

    return domain.rsplit(":", 1)[0] if ":" in domain else domain


@register(DOMAIN)
def check_frontend_origin_allowed(app_configs, **kwargs):
    """
    The frontend origin is listed in CORS.

    ⚠️  This is the most time-expensive misconfiguration of them all: the
        frontend shows a blank screen while the server reports it answered 200
        to every call. So the fault is hunted in the server while it is in the browser.
    """
    if getattr(settings, "CORS_ALLOW_ALL_ORIGINS", False):
        return []

    origin = settings.FRONTEND_BASE_URL.rstrip("/")
    allowed = {value.rstrip("/") for value in settings.CORS_ALLOWED_ORIGINS}

    if origin in allowed:
        return []

    return [
        Error(
            f"أصل الفرونت إند {origin} غير مدرَج في CORS_ALLOWED_ORIGINS ({sorted(allowed)}).",
            hint=(
                "الأصلان يُشتقّان من SITE_DOMAIN في config/environment.py — "
                "فاختلافهما يعني تجاوزًا صريحًا لأحدهما بمتغيّر بيئة. "
                "احذف التجاوز أو أكمله."
            ),
            id="core.E001",
        )
    ]


@register(DOMAIN)
def check_domains_in_allowed_hosts(app_configs, **kwargs):
    """
    The site and server domains are both accepted in `ALLOWED_HOSTS`.

    ⚠️  Compared with `validate_host` — Django's own matcher.

        Checking with `in` would have rejected `.example.com` (the leading dot
        means "all subdomains") and produced a false error pushing the operator
        to "fix" a perfectly sound configuration.
    """
    errors = []

    for name in ("PUBLIC_SITE_DOMAIN", "PUBLIC_API_DOMAIN"):
        host = _hostname(getattr(settings, name)).lower()

        if not validate_host(host, settings.ALLOWED_HOSTS):
            errors.append(
                Error(
                    f"{name} = {host} غير مقبول في ALLOWED_HOSTS ({settings.ALLOWED_HOSTS}).",
                    hint=(
                        "المضيف بلا منفذ هو ما يُقارَن. "
                        "احذف تجاوز DJANGO_ALLOWED_HOSTS ليعود الاشتقاق التلقائي."
                    ),
                    id="core.E002",
                )
            )

    return errors


@register(DOMAIN)
def check_api_prefix(app_configs, **kwargs):
    if settings.PUBLIC_API_PREFIX.startswith("/"):
        return []

    return [
        Error(
            f"PUBLIC_API_PREFIX = {settings.PUBLIC_API_PREFIX} يجب أن يبدأ بشرطة مائلة.",
            hint="مثال: /api/v1 — يُلحَق بأصل الخادم لتكوين عنوان النداءات.",
            id="core.E003",
        )
    ]


@register(DOMAIN)
def check_production_domains(app_configs, **kwargs):
    """
    ⚠️  Production does not boot with a development configuration.

        A real server on a `localhost` domain returns 400 to every visitor and
        generates email activation links pointing at the recipient's own
        machine. And on an `http` scheme the access token travels the network in plaintext.
    """
    if not getattr(settings, "IS_PRODUCTION", False):
        return []

    errors = []

    if settings.PUBLIC_SCHEME != "https":
        errors.append(
            Error(
                f"PUBLIC_SCHEME = {settings.PUBLIC_SCHEME} — الإنتاج يتطلّب https.",
                hint="اضبط IS_PRODUCTION = True في config/environment.py",
                id="core.E004",
            )
        )

    for name in ("PUBLIC_SITE_DOMAIN", "PUBLIC_API_DOMAIN"):
        host = _hostname(getattr(settings, name)).lower()

        if host in _LOCAL_HOSTS:
            errors.append(
                Error(
                    f"{name} = {host} — دومين محلي في إعداد إنتاج.",
                    hint="الدومين يأتي من كتلة PRODUCTION في config/environment.py.",
                    id="core.E005",
                )
            )

    return errors


@register(DOMAIN)
def check_production_secrets_file(app_configs, **kwargs):
    """
    Production boots against its own secrets file, not the development one.

    ⚠️  **This is the guard that makes the committed switch safe.**

        `config/environment.py` is tracked in Git, so `IS_PRODUCTION = True` can
        be committed and then pulled onto a machine that has no
        `.env.production`. `base.py` falls back to `.env` there — deliberately,
        so a half-migrated machine still runs — and the result is production
        settings reading development secrets: the production domain, `DEBUG`
        off, HTTPS enforced, over a development database and a development
        secret key. It boots, and it reports itself as production.

        The absent file is the signal, and it is exact: a real deployment has
        the file, and a switch left flipped never does.
    """
    if not getattr(settings, "IS_PRODUCTION", False):
        return []

    from config import environment

    if (settings.BASE_DIR / environment.SECRETS_FILE).exists():
        return []

    return [
        Error(
            f"IS_PRODUCTION مفعَّل بينما {environment.SECRETS_FILE} غير موجود.",
            hint=(
                f"أنشئه من القالب: cp .env.example {environment.SECRETS_FILE} — "
                "وإلّا قُرئ `.env` بدلًا منه، فتعمل إعدادات الإنتاج بأسرار التطوير."
            ),
            id="core.E006",
        )
    ]


@register(DOMAIN)
def check_production_database_host(app_configs, **kwargs):
    """
    A production database on a networked-local host — reported, not refused.

    ⚠️  **A warning and not an error, deliberately.**

        The first draft of this check raised `Error` on a `127.0.0.1` database
        under `IS_PRODUCTION`, on the reasoning that the pair identifies a switch
        left flipped on a development machine.

        It would have blocked the actual deployment. Shared hosting — cPanel
        here — puts PostgreSQL on `127.0.0.1` and reaches it over TCP, so the
        pair is the *normal* production state there, not a mistake. A check that
        refuses the very configuration it was written for teaches its operator
        to bypass checks.

        So the signal is kept and its severity dropped: worth reading on the
        machine where it is wrong, harmless on the machine where it is right.
        The exact case — the switch flipped without production secrets — is
        caught as an error by `core.E006` above.
    """
    if not getattr(settings, "IS_PRODUCTION", False):
        return []

    host = settings.DATABASES.get("default", {}).get("HOST", "")

    if host.lower() not in {"localhost", "127.0.0.1", "::1"}:
        return []

    return [
        Warning(
            f"IS_PRODUCTION مفعَّل وقاعدة البيانات على {host}.",
            hint=(
                "سليم على استضافة مشتركة (cPanel يضع PostgreSQL على 127.0.0.1). "
                "أمّا على جهاز التطوير فيعني أن السويتش تُرك على True."
            ),
            id="core.W001",
        )
    ]


@register(DOMAIN)
def check_admin_url_is_not_default(app_configs, **kwargs):
    """
    Production does not serve Django's admin from `/admin/`.

    ⚠️  A warning, because the panel is not *unprotected* at the default path —
        the login and the permissions are untouched. What the default costs is
        the first filter: `/admin/` is the opening guess of every
        credential-stuffing bot, so leaving it there guarantees the login page
        is found and hammered, and the failures fill the log until the real
        signal is buried in them.

    ⚠️  And the check exists because the failure is **invisible**: the panel
        works perfectly at `/admin/`. Nothing about a working page says the
        setting was never applied — only this line does.
    """
    if not getattr(settings, "IS_PRODUCTION", False):
        return []

    if getattr(settings, "ADMIN_URL", "admin") != "admin":
        return []

    return [
        Warning(
            "لوحة أدمن Django ما زالت على المسار الافتراضي /admin/ في الإنتاج.",
            hint=(
                "اضبط ADMIN_URL في .env.production — لا في config/environment.py، "
                "فذاك مرفوع في Git."
            ),
            id="core.W002",
        )
    ]
