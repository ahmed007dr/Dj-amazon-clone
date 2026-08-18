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

# ⚠️  **الملف الأول يفوز.**
#
#     `read_env` لا يستبدل قيمة موجودة سلفًا في البيئة — ولا قيمةً
#     قرأها ملف سابق. فالترتيب أدناه هو سلّم الأسبقية بعينه:
#
#         بيئة التشغيل الحقيقية  >  .env (خاص)  >  .env.public (مشترك)
#
#     وهو معكوس ما يتوقّعه القارئ عادةً (أن يطغى الأخير)، ولذلك
#     يُذكر صراحةً: الحاوية تتجاوز الملفين، والملف الخاص يتجاوز
#     المشترك بلا أن يعدّله.
environ.Env.read_env(BASE_DIR / ".env")
environ.Env.read_env(BASE_DIR / ".env.public")


# ═══════════════════════════════════════════════════════════
#  الدومين — مصدر واحد يشتق منه الطرفان (ADR-73 · ADR-74)
# ═══════════════════════════════════════════════════════════
# ⚠️  الدومين يُكتب مرة واحدة في `.env.public`، ويقرأ الفرونت إند
#     **نفس الملف** (`web/vite.config.ts`).
#
#     قبل هذا كان الدومين موزّعًا على خمس قيم في ملفين:
#     `DJANGO_ALLOWED_HOSTS` (مضيف بلا مخطَّط) و`CORS_ALLOWED_ORIGINS`
#     (أصل كامل) و`FRONTEND_BASE_URL` (الفرونت) و`CSRF_TRUSTED_ORIGINS`
#     و`VITE_API_BASE_URL` (الخادم). أربعة أشكال لشيء واحد تعني أن
#     نسيان واحد ينتج فشلًا **صامتًا** — والاشتقاق يجعل النسيان
#     مستحيلًا لا نادرًا.
#
# ⚠️  والتجاوز الصريح يبقى ممكنًا: كل قيمة مشتقّة أدناه تقبل متغيّر
#     بيئة يعلوها، للحالات التي تخرج عن النمط (دومين ثانٍ · CDN ·
#     موازن حِمل يمرّر مضيفًا داخليًا).

PUBLIC_SCHEME = env("PUBLIC_SCHEME", default="http")
PUBLIC_SITE_DOMAIN = env("PUBLIC_SITE_DOMAIN", default="localhost:5173")
PUBLIC_API_DOMAIN = env("PUBLIC_API_DOMAIN", default="127.0.0.1:8000")
PUBLIC_API_PREFIX = env("PUBLIC_API_PREFIX", default="/api/v1")
PUBLIC_MEDIA_ORIGIN = env("PUBLIC_MEDIA_ORIGIN", default="")
PUBLIC_DEFAULT_LOCALE = env("PUBLIC_DEFAULT_LOCALE", default="ar")


def _origin(domain: str) -> str:
    """`shop.example.com` ← `https://shop.example.com`"""
    return f"{PUBLIC_SCHEME}://{domain}"


def _hostname(domain: str) -> str:
    """⚠️  `ALLOWED_HOSTS` يقارن بالمضيف وحده — والمنفذ فيه يُفشل المطابقة."""
    return domain.rsplit(":", 1)[0] if ":" in domain else domain


#: الموقع الذي يزوره الإنسان — تُبنى منه روابط البريد وخريطة الموقع
SITE_ORIGIN = _origin(PUBLIC_SITE_DOMAIN)

#: خادم الـ API
API_ORIGIN = _origin(PUBLIC_API_DOMAIN)

#: أصل الوسائط — يتبع الخادم ما لم يُضبط CDN صراحةً
MEDIA_ORIGIN = PUBLIC_MEDIA_ORIGIN or API_ORIGIN


# ═══════════════════════════════════════════════════════════
#  الأمان
# ═══════════════════════════════════════════════════════════

SECRET_KEY = env("DJANGO_SECRET_KEY")

# الافتراضي آمن — البيئات التي تحتاج التصحيح تفعّله صراحةً
DEBUG = env.bool("DJANGO_DEBUG", default=False)

#: علامة الإنتاج — تقرأها فحوص الإقلاع في `core/checks.py`.
#:
#: ⚠️  **لا تُشتقّ من `DEBUG`.**
#:
#:     `DEBUG=False` حالة مشروعة خارج الإنتاج: مشغّل الاختبارات
#:     يفرضها، والمطوّر يشغّلها ليختبر سلوكًا إنتاجيًا محليًا. وربط
#:     فحوص «الدومين ليس localhost» و«المخطَّط https» بها كان يُفشل
#:     الاختبارات على إعداد صحيح تمامًا في مكانه.
IS_PRODUCTION = False

# ⚠️  دومين الموقع مُدرَج مع دومين الخادم.
#
#     `seo/` يخدم `robots.txt` و`sitemap.xml` على **الجذر** لأن
#     المزحف يطلبهما حرفيًا من الدومين الذي يزوره الإنسان. وأي وكيل
#     يمرّرهما إلى Django يصل بترويسة `Host` تحمل دومين الموقع —
#     فغيابه هنا يعطي 400 لطلبَي المزحف وحدهما، وهو عطل لا يلاحظه
#     أحد إلا حين تختفي الصفحات من نتائج البحث.
ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=list(dict.fromkeys([_hostname(PUBLIC_API_DOMAIN), _hostname(PUBLIC_SITE_DOMAIN)])),
)


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
    # ⚠️  `mailing` بجوار `branding`: يعتمد على `core` وحده ولا يعرف
    #     أي نطاق عمل. و`accounts` فوقه لأنه يرسل بريد التفعيل.
    "mailing",
    # L1 — الهوية
    "accounts",
    # L1.5 — سياسات الوصول: تعتمد على accounts فقط ويستهلكها الجميع
    "access",
    # ⚠️  `analytics` شقيق `access` فوق `accounts`.
    #
    #     يقيس الحركة ويصنّف الأجهزة بـ`accounts.services`، ولا يعرف
    #     أي نطاق عمل: المتجر والسلة والطلب كلها «طلب HTTP» عنده.
    #     ووضعه أعلى كان سيمنع `administration` من قراءة رقم الزوار.
    "analytics",
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
    # ⚠️  الأرشفة تجمع `catalog` و`academic` وترشّحهما بـ `access` —
    #     ولا نطاق منها يجوز أن يستورد الآخر.
    "seo",
    # ⚠️  نقطة البيع **قناة** لا نظام موازٍ: كل بيعة تُنتج `Order`
    #     بـ `channel=POS`. فوق `orders` لأنها تستدعيه.
    "pos",
    # ⚠️  المالية **تستمع ولا تُستدعى**: تلتقط الإيراد من أحداث
    #     `orders` وحالاته، وتحسب التكلفة من حركات `inventory`.
    #     ولا نطاق عمل يستوردها.
    "finance",
    # ⚠️  B2B فوق `orders`: الآجل يقيّد الطلب على حساب العميل
    #     ويُصدر فاتورته. و`orders` لا يعرف بوجوده.
    "b2b",
    # ⚠️  `employees` فوق `customers`: الإسناد يملكه الطرف الأعلى
    #     (ADR-12)، و`customers` لا يعرف بوجود الموظفين إطلاقًا.
    "employees",
    # ⚠️  الأهداف فوق `employees`، والعمولات فوق الأهداف و`finance`
    #     معًا: العمولة على الربح تحتاج تكلفة البضاعة المباعة.
    "targets",
    "commissions",
    # ⚠️  الولاء فوق `orders` و`promotions` معًا: يستمع لاكتمال
    #     الطلب ليمنح النقاط، ويُنتج **كوبونًا** عند الاستبدال بدل
    #     أن يلمس السلة أو الطلب — وكلاهما تحته.
    "loyalty",
    # ⚠️  `suppliers` فوق `inventory` و`catalog`: الاستلام يُنشئ
    #     دفعة عبر `inventory.services.receive` لا بكتابة مباشرة.
    "suppliers",
    # ⚠️  `reporting` **يقرأ ولا يكتب** — بلا موديل ولا migrations.
    #     الطبقة العليا: يعرف الجميع ولا يعرفه أحد.
    "reporting",
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
    # ⚠️  **الأخير عمدًا** — القياس على الاستجابة الجاهزة.
    #
    #     وسائط الاستجابة تعمل بالترتيب المعكوس، فموضعه هنا يعني أنه
    #     أول من يرى الاستجابة النهائية برمزها الصحيح. وضعه في الأعلى
    #     كان سيعدّ طلبات ردّها CORS أو CSRF بالرفض استخدامًا حقيقيًا.
    "analytics.middleware.TrafficMiddleware",
]


# ═══════════════════════════════════════════════════════════
#  CORS — الفرونت إند منفصل (ADR-03)
# ═══════════════════════════════════════════════════════════

#: الأصل الوحيد المسموح — مشتقّ من دومين الموقع لا مكتوبًا بجانبه
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[SITE_ORIGIN])

# ⚠️  الموقع **والخادم** معًا في الأصول الموثوقة لـ CSRF.
#
#     لوحة إدارة Django تُقدَّم من دومين الخادم وتعتمد على الجلسة
#     والتوكن معًا؛ وحذفه منها يجعل كل حفظ في `/admin/` يفشل بـ 403
#     خلف وكيل HTTPS.
CSRF_TRUSTED_ORIGINS = env.list(
    "CSRF_TRUSTED_ORIGINS",
    default=list(dict.fromkeys([SITE_ORIGIN, API_ORIGIN])),
)

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
        # ⚠️  أحداث البوابات — نطاق منفصل ومرتفع.
        #
        #     الحارس هنا التوقيع لا العدّاد. والحدّ المنخفض يُسقط
        #     ذروة حقيقية، وكل حدث مفقود طلب مدفوع لا يعرف أحد
        #     أنه دُفع. وفصله عن `anon` يمنع بوابةً نشطة من
        #     استهلاك حصة الزوّار وإسقاط تصفّح المتجر.
        "webhook": "600/minute",
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

# ⚠️  اللغة الافتراضية تُكتب مرة واحدة في `.env.public` ويقرأها
#     الطرفان: الخادم هنا، والواجهة عبر `VITE_DEFAULT_LOCALE`.
#     قيمتان منفصلتان كانتا تعنيان خادمًا يردّ بالعربية وواجهةً
#     تبدأ بالإنجليزية — تناقضٌ يظهر في أول تحميل صفحة.
LANGUAGE_CODE = env("LANGUAGE_CODE", default=PUBLIC_DEFAULT_LOCALE)
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
# ⚠️  مشتقّ من `PUBLIC_SITE_DOMAIN` — لا قيمة مكتوبة.
#
#     كان افتراضيه `localhost:3000` وهو بقيّة من زمن Next.js بينما
#     خادم Vite على ٥١٧٣. ولأنه مصدر روابط البريد وخريطة الموقع
#     (`seo/sitemaps.py`)، كان الافتراضي الخاطئ ينتج روابط تفعيل
#     ميتة وخريطة موقع تشير إلى منفذ لا أحد عليه — بلا خطأ واحد
#     في أي سجل.
FRONTEND_BASE_URL = env("FRONTEND_BASE_URL", default=SITE_ORIGIN)


# ═══════════════════════════════════════════════════════════
#  الأرشفة
# ═══════════════════════════════════════════════════════════
# ⚠️  الافتراضي **مغلق**.
#
#     بيئة تجريبية مفهرسة تنافس الموقع الحقيقي على نفس الكلمات
#     وتعرض بيانات اختبار كأنها منتجات. والافتراضي المغلق يجعل
#     نسيان الضبط خطأً آمنًا؛ العكس يجعله كارثة تسويقية صامتة.

SEO_INDEXING_ENABLED = env.bool("SEO_INDEXING_ENABLED", default=False)


# ═══════════════════════════════════════════════════════════
#  التشفير
# ═══════════════════════════════════════════════════════════
# لبيانات اعتماد بوابات الدفع المخزّنة في قاعدة البيانات (المرحلة ٥)

FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="")


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# drf-yasg — تعطيل العارضات المتوافقة القديمة
SWAGGER_USE_COMPAT_RENDERERS = False
