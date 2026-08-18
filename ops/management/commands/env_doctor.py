"""
عرض الإعداد الفعّال — جواب واحد على «أنا على أي دومين وأي قاعدة بيانات؟»

    python manage.py env_doctor

⚠️  **مخرَجه صالح للّصق في تذكرة عطل.**

    هذا قيده التصميمي الأول: لا كلمة مرور ولا مفتاح ولا توكن يظهر
    هنا مهما بلغت فائدته في التشخيص. الأمر الذي يُشغَّل وقت الحادثة
    ثم يُنسخ مخرَجه إلى محادثة أو تذكرة يجعل كل ما يطبعه علنيًا
    بحكم الأمر الواقع — والأسرار تُقاس بحالتها (مضبوط · غائب · عدد
    المفاتيح) لا بقيمتها.

⚠️  ولماذا أمر أصلًا ما دامت القيم في ملفات؟

    لأن السؤال ليس «ما في الملف» بل «ما القيمة **الفعّالة**»: بيئة
    التشغيل تعلو الملف، و`.env` يعلو `.env.public`، وثلاث طبقات
    إعداد تجعل قراءة ملف واحد إجابةً مضلّلة. والقيم المشتقّة
    (`ALLOWED_HOSTS` · CORS · CSRF) لا توجد في أي ملف أصلًا.
"""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import connection

#: حالة سرّ — لا قيمته
_SET = "✓ مضبوط"
_MISSING = "✕ غير مضبوط"


def _secret_state(value: str | None) -> str:
    """⚠️  الطول لا القيمة. حتى آخر أربعة محارف لا تُطبع لمفتاح."""
    return f"{_SET} ({len(value)} محرفًا)" if value else _MISSING


class Command(BaseCommand):
    help = "عرض الإعداد الفعّال: الدومين · قاعدة البيانات · الكاش · البريد (بلا أسرار)"

    def handle(self, *args, **options):
        failures = 0

        self._section("المصدر")
        for name in (".env.public", ".env"):
            path = settings.BASE_DIR / name
            state = "✓ موجود" if path.exists() else "— غائب"
            self._row(name, state)
        self._note("بيئة التشغيل تعلو الملفين · و`.env` يعلو `.env.public`")

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
        # ⚠️  الوحدة مع الصنف (`console.EmailBackend`) لا الصنف وحده:
        #     كل محوّلات Django تسمّي صنفها `EmailBackend`، فالاسم
        #     المجرّد لا يفرّق بين إرسال حقيقي وطباعة في الطرفية.
        backend = ".".join(settings.EMAIL_BACKEND.rsplit(".", 2)[-2:])
        self._row("EMAIL_BACKEND", backend)
        self._row("EMAIL_HOST", settings.EMAIL_HOST or "—")
        self._row("EMAIL_PORT", settings.EMAIL_PORT)
        self._row("EMAIL_HOST_USER", settings.EMAIL_HOST_USER or "—")
        self._row("EMAIL_HOST_PASSWORD", _secret_state(settings.EMAIL_HOST_PASSWORD))
        self._row("DEFAULT_FROM_EMAIL", settings.DEFAULT_FROM_EMAIL)

        # ⚠️  أكثر الأعطال إرباكًا: «النظام لا يرسل بريدًا» بينما هو
        #     يطبعه في سجل الخادم وقد «نجح» كل إرسال.
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
            # ⚠️  رمز خروج غير صفري — يصلح فحصًا في خط النشر
            self.stderr.write(self.style.ERROR(f"{failures} عطل في الاتصال"))
            raise SystemExit(1)

        self.stdout.write(
            self.style.SUCCESS("لا عطل في الاتصال. الإعداد نفسه يفحصه: manage.py check")
        )

    # ── الاتصالات ──────────────────────────────────────────

    def _database(self) -> int:
        self._section("قاعدة البيانات")
        config = connection.settings_dict

        self._row("ENGINE", config["ENGINE"].rsplit(".", 1)[-1])
        self._row("NAME", config["NAME"])
        self._row("HOST", config["HOST"] or "—")
        self._row("PORT", config["PORT"] or "—")
        self._row("USER", config["USER"] or "—")
        # ⚠️  كلمة المرور غائبة عمدًا — ولا حتى مقنّعة.
        self._row("PASSWORD", _secret_state(config["PASSWORD"]))

        try:
            connection.ensure_connection()
        except Exception as exc:  # التشخيص يعرض السبب ولا يرفع
            self._row("الاتصال", self.style.ERROR(f"✕ فشل — {exc}"))
            return 1

        self._row("الاتصال", self.style.SUCCESS("✓ ناجح"))
        return 0

    def _cache(self) -> int:
        self._section("الكاش")
        backend = settings.CACHES["default"]["BACKEND"].rsplit(".", 1)[-1]
        self._row("BACKEND", backend)

        if backend == "LocMemCache":
            # ⚠️  ذاكرة العملية: كل عامل كاشه الخاص، ولا شيء يبقى بعد
            #     إعادة التشغيل. مقبول في التطوير، وعطل صامت في إنتاج
            #     بعدة عمال — إبطال في عامل لا يراه الآخرون.
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

    # ── العرض ──────────────────────────────────────────────

    def _section(self, title: str) -> None:
        rule = "─" * max(0, 46 - len(title))
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"── {title} {rule}"))

    def _row(self, label: str, value) -> None:
        self.stdout.write(f"  {label:<24} {value}")

    def _note(self, text: str) -> None:
        self.stdout.write(self.style.WARNING(f"  ⚠️  {text}"))
