"""
الإعدادات المشتركة بين كل البيئات.

⚠️  ممنوع وضع أي سر في هذا الملف. كل قيمة حساسة تُقرأ من متغيرات البيئة.
    انظر .env.example
"""

from pathlib import Path

import environ

# BASE_DIR = .../src
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")


# ═══════════════════════════════════════════════════════════
#  الأمان
# ═══════════════════════════════════════════════════════════

SECRET_KEY = env("DJANGO_SECRET_KEY")

# الافتراضي آمن — البيئات التي تحتاج التصحيح تفعّله صراحةً
DEBUG = env.bool("DJANGO_DEBUG", default=False)

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])


# ═══════════════════════════════════════════════════════════
#  التطبيقات
# ═══════════════════════════════════════════════════════════

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_yasg",
    "corsheaders",
]

# ⚠️  الترتيب يعكس مخطط الطبقات في docs/backend/02-DEPENDENCIES.md
#     التبعية تسير للأسفل فقط — يفرضه import-linter في الـ CI
LOCAL_APPS = [
    # L0 — البنية التحتية
    "core",
    "branding",
    # L1 — الهوية
    "accounts",
    # L1.5 — سياسات الوصول: تعتمد على accounts فقط ويستهلكها الجميع
    "access",
    # L2 — الشخصيات ونطاقات الأساس
    "customers",
    "administration",
    "academic",
    "catalog",
    "shipping",
    # L3
    "pricing",
    "inventory",
    "reviews",
    # L4 → L6
    "promotions",
    # payments تحت orders — الطلب يستدعي الدفع لا العكس
    "payments",
    "cart",
    "orders",
    # مستهلك فقط — لا نطاق يستورده
    "notifications",
    # ⚠️  أوامر التشغيل عابرة النطاقات — **مثبّت في الإنتاج**.
    #     بخلاف `devtools` الذي يبقى في بيئة التطوير وحدها.
    "ops",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTH_USER_MODEL = "accounts.User"


# ═══════════════════════════════════════════════════════════
#  الوسائط (Middleware)
# ═══════════════════════════════════════════════════════════
# ⚠️  الترتيب مقصود:
#     CorsMiddleware قبل CommonMiddleware (متطلب الحزمة)
#     LanguageMiddleware بعد المصادقة — يحتاج request.user لقراءة تفضيله

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.LanguageMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ═══════════════════════════════════════════════════════════
#  CORS — الفرونت إند منفصل (ADR-03)
# ═══════════════════════════════════════════════════════════

CORS_ALLOW_CREDENTIALS = True
# ⚠️  كل ترويسة مخصّصة يقرأها الخادم **يجب** أن تُدرَج هنا.
#
#     الترويسة غير المدرَجة تجعل المتصفح يرفض الطلب في مرحلة
#     الفحص المبدئي (preflight) — فلا يصل النداء إلى Django أصلًا،
#     ولا يظهر شيء في سجلّه. المطوّر يبحث عن الخطأ في الخادم بينما
#     هو في المتصفح.
#
#     المدرَجة أدناه يقرؤها: cart/api.py · access/preview.py
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-language",
    "authorization",
    "content-type",
    "idempotency-key",
    "x-requested-with",
    # سلة الزائر — قبل التسجيل
    "x-cart-session",
    # وضع معاينة الأدمن (قراءة فقط · مُدقَّق)
    "x-preview-as",
    "x-preview-verified",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"


# ═══════════════════════════════════════════════════════════
#  القوالب
# ═══════════════════════════════════════════════════════════
# تُحذف بالكامل في المرحلة 0.5 (قرار SPA)

# القوالب للوحة Django فقط — طبقة العرض حُذفت (قرار SPA · ADR-03)
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# ═══════════════════════════════════════════════════════════
#  قاعدة البيانات
# ═══════════════════════════════════════════════════════════
# تنتقل إلى PostgreSQL في المرحلة 0.5

DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}


# ═══════════════════════════════════════════════════════════
#  المصادقة
# ═══════════════════════════════════════════════════════════

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    "accounts.backend.EmailOrPhoneBackend",
]


# ═══════════════════════════════════════════════════════════
#  REST Framework
# ═══════════════════════════════════════════════════════════

REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "core.api.pagination.DefaultCursorPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # يفحص الإيقاف على كل طلب — الطبقة ٣ من ADR-16
        "accounts.authentication.StatefulJWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "EXCEPTION_HANDLER": "core.api.exception_handler.custom_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "COERCE_DECIMAL_TO_STRING": True,  # المال نصًا لا رقمًا (ADR-31)
    "DATETIME_FORMAT": "%Y-%m-%dT%H:%M:%SZ",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/minute",
        "user": "300/minute",
        # نقاط المصادقة — حدود مشدّدة تمنع التخمين
        "login": "5/minute",
        "register": "3/hour",
        "password_reset": "3/hour",
    },
}


# ═══════════════════════════════════════════════════════════
#  JWT
# ═══════════════════════════════════════════════════════════
# عمر قصير للـ Access + تدوير + قائمة سوداء — الطبقات ١ و٢ من
# آلية إبطال الجلسة عند الإيقاف. الطبقة ٣ (مجموعة Redis) في المرحلة ٢.

from datetime import timedelta

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}


# ═══════════════════════════════════════════════════════════
#  الكاش
# ═══════════════════════════════════════════════════════════
# بلا REDIS_URL يستخدم ذاكرة محلية — لا يفشل التطوير عند غياب Redis

_redis_url = env("REDIS_URL", default="")

if _redis_url:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _redis_url,
        },
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "medical-commerce-locmem",
        },
    }


# ═══════════════════════════════════════════════════════════
#  اللغة والتوقيت
# ═══════════════════════════════════════════════════════════

LANGUAGE_CODE = env("LANGUAGE_CODE", default="ar")
TIME_ZONE = env("TIME_ZONE", default="Africa/Cairo")

USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("ar", "Arabic"),
    ("en", "English"),
]

LOCALE_PATHS = [BASE_DIR / "locale"]


# ═══════════════════════════════════════════════════════════
#  الملفات الثابتة والوسائط
# ═══════════════════════════════════════════════════════════

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"


# ═══════════════════════════════════════════════════════════
#  البريد الإلكتروني
# ═══════════════════════════════════════════════════════════
# ⚠️  بيانات الاعتماد من البيئة حصرًا. لا كلمة مرور في الكود.

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@example.com")


# ═══════════════════════════════════════════════════════════
#  قواعد العمل القابلة للضبط
# ═══════════════════════════════════════════════════════════
# تنتقل إلى core/settings كإعدادات في قاعدة البيانات (المرحلة ١)

# العملة
DEFAULT_CURRENCY = env("DEFAULT_CURRENCY", default="EGP")
CURRENCY_DECIMAL_PLACES = env.int("CURRENCY_DECIMAL_PLACES", default=2)

# الضريبة — قابلة للضبط، غير مثبتة في الكود
TAX_ENABLED = env.bool("TAX_ENABLED", default=True)
TAX_DEFAULT_RATE = env("TAX_DEFAULT_RATE", default="14.00")
TAX_PRICES_INCLUDE_TAX = env.bool("TAX_PRICES_INCLUDE_TAX", default=False)


# ═══════════════════════════════════════════════════════════
#  الفرونت إند
# ═══════════════════════════════════════════════════════════

FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", default="http://localhost:3000")
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])


# ═══════════════════════════════════════════════════════════
#  التشفير
# ═══════════════════════════════════════════════════════════
# لبيانات اعتماد بوابات الدفع المخزّنة في قاعدة البيانات (المرحلة ٥)

FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="")


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# drf-yasg — تعطيل العارضات المتوافقة القديمة
SWAGGER_USE_COMPAT_RENDERERS = False
