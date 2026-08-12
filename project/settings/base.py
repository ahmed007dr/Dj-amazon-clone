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
environ.Env.read_env(BASE_DIR / '.env')


# ═══════════════════════════════════════════════════════════
#  الأمان
# ═══════════════════════════════════════════════════════════

SECRET_KEY = env('DJANGO_SECRET_KEY')

# الافتراضي آمن — البيئات التي تحتاج التصحيح تفعّله صراحةً
DEBUG = env.bool('DJANGO_DEBUG', default=False)

ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS', default=[])


# ═══════════════════════════════════════════════════════════
#  التطبيقات
# ═══════════════════════════════════════════════════════════

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
]

THIRD_PARTY_APPS = [
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'dj_rest_auth',
    'dj_rest_auth.registration',
    'taggit',
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt',
    'django_filters',
    'drf_yasg',
    'django_bootstrap5',
]

LOCAL_APPS = [
    'accounts',
    'products',
    'settings',
    'orders',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS


# ═══════════════════════════════════════════════════════════
#  الوسائط (Middleware)
# ═══════════════════════════════════════════════════════════
# ملاحظة: ترتيب الكاش الحالي غير سليم ويُعالج في المرحلة 0.5
#         (CacheMiddleware وحده في منتصف السلسلة).

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'project.urls'
WSGI_APPLICATION = 'project.wsgi.application'


# ═══════════════════════════════════════════════════════════
#  القوالب
# ═══════════════════════════════════════════════════════════
# تُحذف بالكامل في المرحلة 0.5 (قرار SPA)

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'settings.settings_context_processor.get_settings',
                'orders.cart_context_processor.get_cart_data',
            ],
        },
    },
]


# ═══════════════════════════════════════════════════════════
#  قاعدة البيانات
# ═══════════════════════════════════════════════════════════
# تنتقل إلى PostgreSQL في المرحلة 0.5

DATABASES = {
    'default': env.db('DATABASE_URL', default=f'sqlite:///{BASE_DIR / "db.sqlite3"}'),
}


# ═══════════════════════════════════════════════════════════
#  المصادقة
# ═══════════════════════════════════════════════════════════

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

AUTHENTICATION_BACKENDS = [
    'accounts.backend.EmailOrUsernameLogin',
    'django.contrib.auth.backends.ModelBackend',
]

SITE_ID = 1
LOGIN_REDIRECT_URL = '/'

REST_AUTH = {
    'USE_JWT': True,
    'JWT_AUTH_COOKIE': 'jwt-auth',
}


# ═══════════════════════════════════════════════════════════
#  REST Framework
# ═══════════════════════════════════════════════════════════

REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.LimitOffsetPagination',
    'PAGE_SIZE': 100,
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}


# ═══════════════════════════════════════════════════════════
#  الكاش
# ═══════════════════════════════════════════════════════════
# بلا REDIS_URL يستخدم ذاكرة محلية — لا يفشل التطوير عند غياب Redis

_redis_url = env('REDIS_URL', default='')

if _redis_url:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': _redis_url,
        },
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'medical-commerce-locmem',
        },
    }


# ═══════════════════════════════════════════════════════════
#  اللغة والتوقيت
# ═══════════════════════════════════════════════════════════

LANGUAGE_CODE = env('LANGUAGE_CODE', default='ar')
TIME_ZONE = env('TIME_ZONE', default='Africa/Cairo')

USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ('ar', 'Arabic'),
    ('en', 'English'),
]

LOCALE_PATHS = [BASE_DIR / 'locale']


# ═══════════════════════════════════════════════════════════
#  الملفات الثابتة والوسائط
# ═══════════════════════════════════════════════════════════

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'


# ═══════════════════════════════════════════════════════════
#  البريد الإلكتروني
# ═══════════════════════════════════════════════════════════
# ⚠️  بيانات الاعتماد من البيئة حصرًا. لا كلمة مرور في الكود.

EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=False)
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@example.com')


# ═══════════════════════════════════════════════════════════
#  قواعد العمل القابلة للضبط
# ═══════════════════════════════════════════════════════════
# تنتقل إلى core/settings كإعدادات في قاعدة البيانات (المرحلة ١)

# العملة
DEFAULT_CURRENCY = env('DEFAULT_CURRENCY', default='EGP')
CURRENCY_DECIMAL_PLACES = env.int('CURRENCY_DECIMAL_PLACES', default=2)

# الضريبة — قابلة للضبط، غير مثبتة في الكود
TAX_ENABLED = env.bool('TAX_ENABLED', default=True)
TAX_DEFAULT_RATE = env('TAX_DEFAULT_RATE', default='14.00')
TAX_PRICES_INCLUDE_TAX = env.bool('TAX_PRICES_INCLUDE_TAX', default=False)


# ═══════════════════════════════════════════════════════════
#  الفرونت إند
# ═══════════════════════════════════════════════════════════

FRONTEND_BASE_URL = env('FRONTEND_BASE_URL', default='http://localhost:3000')
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[])


# ═══════════════════════════════════════════════════════════
#  التشفير
# ═══════════════════════════════════════════════════════════
# لبيانات اعتماد بوابات الدفع المخزّنة في قاعدة البيانات (المرحلة ٥)

FIELD_ENCRYPTION_KEY = env('FIELD_ENCRYPTION_KEY', default='')


DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
