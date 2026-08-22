"""
Show the effective configuration — one answer to "which domain and which database am I on?"

    python manage.py env_doctor

⚠️  **Its output is safe to paste into an incident ticket.**

    That is its first design constraint: no password, no key and no token
    appears here however useful it would be for diagnosis. A command run during
    an incident and then copied into a chat or a ticket makes everything it
    prints public as a matter of fact — and secrets are reported by their status
    (set · absent · number of keys), not by their value.

⚠️  And why a command at all, when the values are in files?

    Because the question is not "what is in the file" but "what is the
    **effective** value": the process environment outranks the file, and `.env`
    outranks `.env.public`, so three configuration layers make reading one file
    a misleading answer. And the derived values (`ALLOWED_HOSTS` · CORS · CSRF)
    exist in no file at all.
"""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import connection

#: A secret's status — not its value
_SET = "✓ مضبوط"
_MISSING = "✕ غير مضبوط"


def _secret_state(value: str | None) -> str:
    """⚠️  The length, not the value. Not even the last four characters of a key are printed."""
    return f"{_SET} ({len(value)} محرفًا)" if value else _MISSING


class Command(BaseCommand):
    help = "عرض الإعداد الفعّال: الدومين · قاعدة البيانات · الكاش · البريد (بلا أسرار)"

    def handle(self, *args, **options):
        failures = 0

        self._section("المصدر")

        # ⚠️  السويتش أول سطر في المخرَج عمدًا.
        #
        #     كل سطر بعده — الدومين والقاعدة والكاش — نتيجةٌ له. وقارئ يرى
        #     دومين إنتاج دون أن يعرف أي بيئة فعّالة يخمّن، وأول ما يُسأل
        #     في أي حادثة هو «أنا على أي بيئة؟».
        from config import environment

        self._row("IS_PRODUCTION", "✓ إنتاج" if environment.IS_PRODUCTION else "— تطوير")
        self._row("config/environment.py", "✓ موجود")
        self._row("وحدة الإعدادات", settings.SETTINGS_MODULE)

        secrets = settings.BASE_DIR / environment.SECRETS_FILE
        self._row(environment.SECRETS_FILE, "✓ موجود" if secrets.exists() else "— غائب")

        legacy = settings.BASE_DIR / ".env"
        if legacy.exists():
            self._row(".env", "✓ موجود (احتياطي — لا يعلو ملف البيئة)")

        self._note("بيئة التشغيل تعلو الملفات · وملف البيئة يعلو `.env`")

        self._section("الدومين — المكتوب")
        self._row("PUBLIC_SCHEME", settings.PUBLIC_SCHEME)
        self._row("PUBLIC_SITE_DOMAIN", settings.PUBLIC_SITE_DOMAIN)
        self._row("PUBLIC_API_DOMAIN", settings.PUBLIC_API_DOMAIN)
        self._row("PUBLIC_API_PREFIX", settings.PUBLIC_API_PREFIX)
        self._row("PUBLIC_DEFAULT_LOCALE", settings.PUBLIC_DEFAULT_LOCALE)

        self._section("الدومين — المشتقّ")
        self._row("ALLOWED_HOSTS", " · ".join(settings.ALLOWED_HOSTS))
        self._row("CORS_ALLOWED_ORIGINS", " · ".join(settings.CORS_ALLOWED_ORIGINS))
        self._row("CSRF_TRUSTED_ORIGINS", " · ".join(settings.CSRF_TRUSTED_ORIGINS))
        self._row("FRONTEND_BASE_URL", settings.FRONTEND_BASE_URL)

        self._section("ما تبنيه الواجهة من نفس المصدر")
        self._row("VITE_API_BASE_URL", f"{settings.API_ORIGIN}{settings.PUBLIC_API_PREFIX}")
        self._row("VITE_MEDIA_BASE_URL", settings.MEDIA_ORIGIN)

        failures += self._database()
        failures += self._cache()

        self._section("البريد")
        # ⚠️  The module together with the class (`console.EmailBackend`), not the class alone:
        #     every Django backend names its class `EmailBackend`, so the bare name
        #     does not distinguish a real send from printing to the terminal.
        backend = ".".join(settings.EMAIL_BACKEND.rsplit(".", 2)[-2:])
        self._row("EMAIL_BACKEND", backend)
        self._row("EMAIL_HOST", settings.EMAIL_HOST or "—")
        self._row("EMAIL_PORT", settings.EMAIL_PORT)
        self._row("EMAIL_HOST_USER", settings.EMAIL_HOST_USER or "—")
        self._row("EMAIL_HOST_PASSWORD", _secret_state(settings.EMAIL_HOST_PASSWORD))
        self._row("DEFAULT_FROM_EMAIL", settings.DEFAULT_FROM_EMAIL)

        # ⚠️  The most confusing fault of all: "the system does not send email" while it
        #     is printing it into the server log and every send has "succeeded".
        if ".console." in settings.EMAIL_BACKEND:
            self._note("الرسائل تُطبع في الطرفية ولا تُرسل")
        elif ".locmem." in settings.EMAIL_BACKEND:
            self._note("الرسائل تُحفظ في الذاكرة وتُهمَل — محوّل الاختبارات")
        elif ".dummy." in settings.EMAIL_BACKEND:
            self._note("الرسائل تُهمَل بلا أثر")

        self._section("الأسرار")
        self._row("DJANGO_SECRET_KEY", _secret_state(settings.SECRET_KEY))
        keys = [k for k in (settings.FIELD_ENCRYPTION_KEY or "").split(",") if k.strip()]
        self._row("FIELD_ENCRYPTION_KEY", f"{_SET} ({len(keys)} مفتاح)" if keys else _MISSING)

        self._section("الحالة")
        self._row("DEBUG", settings.DEBUG)
        self._row("IS_PRODUCTION", getattr(settings, "IS_PRODUCTION", False))
        self._row("TIME_ZONE", settings.TIME_ZONE)
        self._row("LANGUAGE_CODE", settings.LANGUAGE_CODE)

        self.stdout.write("")
        if failures:
            # ⚠️  A non-zero exit code — usable as a check in the deployment pipeline
            self.stderr.write(self.style.ERROR(f"{failures} عطل في الاتصال"))
            raise SystemExit(1)

        self.stdout.write(
            self.style.SUCCESS("لا عطل في الاتصال. الإعداد نفسه يفحصه: manage.py check")
        )

    # ── Connections ────────────────────────────────────────

    def _database(self) -> int:
        self._section("قاعدة البيانات")
        config = connection.settings_dict

        self._row("ENGINE", config["ENGINE"].rsplit(".", 1)[-1])
        self._row("NAME", config["NAME"])
        self._row("HOST", config["HOST"] or "—")
        self._row("PORT", config["PORT"] or "—")
        self._row("USER", config["USER"] or "—")
        # ⚠️  The password is deliberately absent — not even masked.
        self._row("PASSWORD", _secret_state(config["PASSWORD"]))

        try:
            connection.ensure_connection()
        except Exception as exc:  # Diagnosis shows the cause and does not raise
            self._row("الاتصال", self.style.ERROR(f"✕ فشل — {exc}"))
            return 1

        self._row("الاتصال", self.style.SUCCESS("✓ ناجح"))
        return 0

    def _cache(self) -> int:
        self._section("الكاش")
        backend = settings.CACHES["default"]["BACKEND"].rsplit(".", 1)[-1]
        self._row("BACKEND", backend)

        if backend == "LocMemCache":
            # ⚠️  Process memory: every worker has its own cache, and nothing survives
            #     a restart. Acceptable in development, and a silent fault in a
            #     multi-worker production — an invalidation in one worker the others never see.
            self._note("ذاكرة محلية لكل عملية — لا تصلح لإنتاج بعدة عمال")

        try:
            cache.set("env_doctor", "ok", 5)
            healthy = cache.get("env_doctor") == "ok"
        except Exception as exc:
            self._row("الاتصال", self.style.ERROR(f"✕ فشل — {exc}"))
            return 1

        if not healthy:
            self._row("الاتصال", self.style.ERROR("✕ الكتابة نجحت والقراءة لم تُرجع القيمة"))
            return 1

        self._row("الاتصال", self.style.SUCCESS("✓ ناجح"))
        return 0

    # ── Output ─────────────────────────────────────────────

    def _section(self, title: str) -> None:
        rule = "─" * max(0, 46 - len(title))
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"── {title} {rule}"))

    def _row(self, label: str, value) -> None:
        self.stdout.write(f"  {label:<24} {value}")

    def _note(self, text: str) -> None:
        self.stdout.write(self.style.WARNING(f"  ⚠️  {text}"))
