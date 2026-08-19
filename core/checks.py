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
from django.core.checks import Error, register
from django.http.request import validate_host

#: A tag allowing them to be run alone: `manage.py check --tag domain`
DOMAIN = "domain"

#: Names unfit to be the domain of a server facing the world
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}  # noqa: S104


def _hostname(domain: str) -> str:
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
                "الأصلان يُشتقّان من PUBLIC_SITE_DOMAIN في .env.public — "
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
                hint="اضبط PUBLIC_SCHEME=https في .env.public",
                id="core.E004",
            )
        )

    for name in ("PUBLIC_SITE_DOMAIN", "PUBLIC_API_DOMAIN"):
        host = _hostname(getattr(settings, name)).lower()

        if host in _LOCAL_HOSTS:
            errors.append(
                Error(
                    f"{name} = {host} — دومين محلي في إعداد إنتاج.",
                    hint="اضبط الدومين الحقيقي في .env.public قبل النشر.",
                    id="core.E005",
                )
            )

    return errors
