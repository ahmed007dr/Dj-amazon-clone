"""
Domain configuration tests. (ADR-73 · ADR-74)

⚠️  **Why test settings at all?**

    Because every mistake in them is silent at the server: a missing origin in
    CORS makes the browser block a perfectly good 200, and a missing host
    returns 400 for the crawler's requests alone. Not one of them writes a line
    to the Django log, and all of them are discovered after deployment. The test
    here makes the derivation itself — not vigilance — the guard.
"""

from io import StringIO

import pytest
from django.conf import settings
from django.core.management import call_command
from django.test import override_settings

from core import checks

# ═══════════════════════════════════════════════════════════
#  Derivation — one value produces all five
# ═══════════════════════════════════════════════════════════


class TestDerivedDomain:
    def test_frontend_origin_is_allowed_by_cors(self):
        """
        ⚠️  A mismatch here produces a blank screen and a server reporting it answered 200.
        """
        assert settings.FRONTEND_BASE_URL.rstrip("/") in settings.CORS_ALLOWED_ORIGINS

    def test_both_domains_are_in_allowed_hosts(self):
        """
        The site domain is listed alongside the server domain: `seo` serves
        `robots.txt` and `sitemap.xml` on the domain a human visits.
        """
        for domain in (settings.PUBLIC_SITE_DOMAIN, settings.PUBLIC_API_DOMAIN):
            assert checks._hostname(domain) in settings.ALLOWED_HOSTS

    def test_allowed_hosts_carry_no_port(self):
        """⚠️  A port in `ALLOWED_HOSTS` breaks the match silently."""
        assert not [host for host in settings.ALLOWED_HOSTS if ":" in host and host != "[::1]"]

    def test_media_origin_follows_api_when_unset(self):
        if not settings.PUBLIC_MEDIA_ORIGIN:
            assert settings.MEDIA_ORIGIN == settings.API_ORIGIN

    def test_language_matches_the_shared_default(self):
        """A server in Arabic and a frontend in English is a contradiction visible on the first
        load."""
        assert settings.LANGUAGE_CODE == settings.PUBLIC_DEFAULT_LOCALE


# ═══════════════════════════════════════════════════════════
#  The checks — they fail at startup, not after deployment
# ═══════════════════════════════════════════════════════════


class TestDomainChecks:
    def test_clean_configuration_passes(self):
        for check in (
            checks.check_frontend_origin_allowed,
            checks.check_domains_in_allowed_hosts,
            checks.check_api_prefix,
            checks.check_production_domains,
        ):
            assert check(None) == []

    @override_settings(CORS_ALLOWED_ORIGINS=["https://other.example.com"])
    def test_frontend_origin_missing_from_cors_is_an_error(self):
        assert [e.id for e in checks.check_frontend_origin_allowed(None)] == ["core.E001"]

    @override_settings(ALLOWED_HOSTS=["example.com"])
    def test_domain_missing_from_allowed_hosts_is_an_error(self):
        errors = checks.check_domains_in_allowed_hosts(None)
        assert [e.id for e in errors] == ["core.E002", "core.E002"]

    @override_settings(ALLOWED_HOSTS=[".example.com"], PUBLIC_SITE_DOMAIN="shop.example.com")
    def test_wildcard_subdomain_is_accepted(self):
        """
        ⚠️  The leading dot means "all subdomains" — and the naive `in` check
            rejected it, pushing the operator to "fix" a perfectly sound
            configuration.
        """
        errors = checks.check_domains_in_allowed_hosts(None)
        assert [e.id for e in errors] == ["core.E002"]  # the server domain alone

    @override_settings(PUBLIC_API_PREFIX="api/v1")
    def test_prefix_without_leading_slash_is_an_error(self):
        assert [e.id for e in checks.check_api_prefix(None)] == ["core.E003"]

    @override_settings(IS_PRODUCTION=True, PUBLIC_SCHEME="http")
    def test_production_refuses_plain_http(self):
        assert "core.E004" in [e.id for e in checks.check_production_domains(None)]

    @override_settings(
        IS_PRODUCTION=True,
        PUBLIC_SCHEME="https",
        PUBLIC_SITE_DOMAIN="localhost:5173",
        PUBLIC_API_DOMAIN="127.0.0.1:8000",
    )
    def test_production_refuses_local_domains(self):
        errors = checks.check_production_domains(None)
        assert [e.id for e in errors] == ["core.E005", "core.E005"]

    @override_settings(IS_PRODUCTION=False, PUBLIC_SCHEME="http", PUBLIC_SITE_DOMAIN="localhost")
    def test_development_is_left_alone(self):
        """
        ⚠️  The strict checks are tied to `IS_PRODUCTION`, not to `DEBUG`: the
            test runner forces `DEBUG=False` on a correct development configuration.
        """
        assert checks.check_production_domains(None) == []


# ═══════════════════════════════════════════════════════════
#  env_doctor — its output gets pasted into an incident ticket
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEnvDoctor:
    def _run(self) -> str:
        out = StringIO()
        call_command("env_doctor", stdout=out, stderr=StringIO())
        return out.getvalue()

    def test_shows_the_effective_domain(self):
        output = self._run()
        assert settings.FRONTEND_BASE_URL in output
        assert f"{settings.API_ORIGIN}{settings.PUBLIC_API_PREFIX}" in output

    def test_prints_no_secret_value(self):
        """
        ⚠️  **Its first design constraint.**

            The command is run during an incident and its output is copied into
            a ticket or a chat — so everything it prints is public as a matter
            of fact. And secrets are judged by their status, not their value.
        """
        output = self._run()

        secrets = [
            settings.SECRET_KEY,
            settings.DATABASES["default"].get("PASSWORD") or "",
            settings.EMAIL_HOST_PASSWORD,
            settings.FIELD_ENCRYPTION_KEY,
        ]

        for secret in secrets:
            if secret:
                assert secret not in output
