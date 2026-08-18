"""
فحوص إعداد الدومين — وقت الإقلاع لا بعد النشر.

⚠️  **المشكلة التي تحلّها**: أخطاء الدومين كلها صامتة عند الخادم.

    أصل غير مدرَج في CORS يجعل المتصفح يحجب الاستجابة بعد أن يعيد
    الخادم ٢٠٠ سليمة؛ ومضيف ناقص في `ALLOWED_HOSTS` يعطي 400 لطلبات
    المزحف وحدها؛ ودومين `localhost` في الإنتاج يجعل روابط تفعيل
    البريد تشير إلى جهاز المستلم نفسه. لا واحدة منها تكتب سطرًا في
    سجل Django، وكلها تُكتشف بعد النشر — أو بعد أن تختفي الصفحات من
    نتائج البحث.

    الفحص ينقلها إلى ما قبل النشر: `manage.py check` يفشل، فلا
    يقلع الخادم أصلًا.

⚠️  والفحوص الصارمة مربوطة بـ `IS_PRODUCTION` لا بـ `DEBUG`.

    `DEBUG=False` حالة مشروعة في الاختبارات والتطوير، وربطها بها كان
    يُفشل بيئة صحيحة تمامًا في مكانها.
"""

from __future__ import annotations

from django.conf import settings
from django.core.checks import Error, register
from django.http.request import validate_host

#: وسم يسمح بتشغيلها وحدها: `manage.py check --tag domain`
DOMAIN = "domain"

#: أسماء لا تصلح دومينًا لخادم يخدم العالم
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]"}  # noqa: S104


def _hostname(domain: str) -> str:
    return domain.rsplit(":", 1)[0] if ":" in domain else domain


@register(DOMAIN)
def check_frontend_origin_allowed(app_configs, **kwargs):
    """
    أصل الفرونت إند مدرَج في CORS.

    ⚠️  هذا أكثر أخطاء الإعداد كلفةً في الوقت: الواجهة تُظهر شاشة
        فارغة، والخادم يقول إنه ردّ ٢٠٠ على كل نداء. فيُبحث عن العطل
        في الخادم بينما هو في المتصفح.
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
    دومينا الموقع والخادم مقبولان في `ALLOWED_HOSTS`.

    ⚠️  المقارنة بـ `validate_host` — مطابِق Django نفسه.

        الفحص بـ `in` كان سيرفض `.example.com` (البادئة النقطية
        تعني «كل النطاقات الفرعية») ويُنتج خطأً كاذبًا يدفع المشغّل
        إلى «إصلاح» إعداد سليم.
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
    ⚠️  الإنتاج لا يقلع بإعداد تطوير.

        خادم حقيقي بدومين `localhost` يعيد 400 لكل زائر، ويولّد
        روابط تفعيل بريد تشير إلى جهاز المستلم نفسه. وبمخطَّط `http`
        يسافر توكن الدخول نصًّا صريحًا على الشبكة.
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
