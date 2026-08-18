"""
اختبارات إعداد الدومين. (ADR-73 · ADR-74)

⚠️  **لماذا تُختبر الإعدادات أصلًا؟**

    لأن كل خطأ فيها صامت عند الخادم: أصل ناقص في CORS يجعل المتصفح
    يحجب استجابة ٢٠٠ سليمة، ومضيف ناقص يعطي 400 لطلبات المزحف
    وحدها. لا واحد منها يكتب سطرًا في سجل Django، وكلها تُكتشف بعد
    النشر. الاختبار هنا يجعل الاشتقاق نفسه — لا الانتباه — هو الحارس.
"""

from io import StringIO

import pytest
from django.conf import settings
from django.core.management import call_command
from django.test import override_settings

from core import checks

# ═══════════════════════════════════════════════════════════
#  الاشتقاق — قيمة واحدة تُنتج الخمس
# ═══════════════════════════════════════════════════════════


class TestDerivedDomain:
    def test_frontend_origin_is_allowed_by_cors(self):
        """
        ⚠️  عدم التطابق هنا يُنتج شاشة فارغة وخادمًا يقول إنه ردّ ٢٠٠.
        """
        assert settings.FRONTEND_BASE_URL.rstrip("/") in settings.CORS_ALLOWED_ORIGINS

    def test_both_domains_are_in_allowed_hosts(self):
        """
        دومين الموقع مُدرَج مع دومين الخادم: `seo` يخدم `robots.txt`
        و`sitemap.xml` على الدومين الذي يزوره الإنسان.
        """
        for domain in (settings.PUBLIC_SITE_DOMAIN, settings.PUBLIC_API_DOMAIN):
            assert checks._hostname(domain) in settings.ALLOWED_HOSTS

    def test_allowed_hosts_carry_no_port(self):
        """⚠️  المنفذ في `ALLOWED_HOSTS` يُفشل المطابقة بصمت."""
        assert not [host for host in settings.ALLOWED_HOSTS if ":" in host and host != "[::1]"]

    def test_media_origin_follows_api_when_unset(self):
        if not settings.PUBLIC_MEDIA_ORIGIN:
            assert settings.MEDIA_ORIGIN == settings.API_ORIGIN

    def test_language_matches_the_shared_default(self):
        """خادم بالعربية وواجهة بالإنجليزية تناقض يظهر في أول تحميل."""
        assert settings.LANGUAGE_CODE == settings.PUBLIC_DEFAULT_LOCALE


# ═══════════════════════════════════════════════════════════
#  الفحوص — تفشل وقت الإقلاع لا بعد النشر
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
        ⚠️  البادئة النقطية تعني «كل النطاقات الفرعية» — والفحص
            البسيط بـ `in` كان يرفضها ويدفع المشغّل إلى «إصلاح»
            إعداد سليم.
        """
        errors = checks.check_domains_in_allowed_hosts(None)
        assert [e.id for e in errors] == ["core.E002"]  # دومين الخادم وحده

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
        ⚠️  الفحوص الصارمة مربوطة بـ `IS_PRODUCTION` لا بـ `DEBUG`:
            مشغّل الاختبارات يفرض `DEBUG=False` على إعداد تطوير صحيح.
        """
        assert checks.check_production_domains(None) == []


# ═══════════════════════════════════════════════════════════
#  env_doctor — مخرَجه يُلصق في تذكرة عطل
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
        ⚠️  **قيده التصميمي الأول.**

            الأمر يُشغَّل وقت الحادثة ويُنسخ مخرَجه إلى تذكرة أو
            محادثة — فكل ما يطبعه علنيّ بحكم الأمر الواقع. والأسرار
            تُقاس بحالتها لا بقيمتها.
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
