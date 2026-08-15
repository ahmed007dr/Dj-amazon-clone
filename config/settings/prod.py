"""
إعدادات الإنتاج.

    DJANGO_SETTINGS_MODULE=config.settings.prod

⚠️  كل متغير هنا إلزامي. غيابه يوقف الإقلاع عمدًا —
    أفضل من إقلاع صامت بإعداد غير آمن.
"""

from .base import *
from .base import env

DEBUG = False

# بلا قيمة افتراضية — الغياب يوقف الإقلاع
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

# ⚠️  مفتاح تشفير بيانات اعتماد البوابات — **إلزامي هنا**.
#
#     الافتراضي الفارغ في `base.py` يخدم التطوير والاختبار. أما في
#     الإنتاج فغيابه يعني إما رفض كل حفظ لمفتاح بوابة، أو — لو
#     تساهلنا — مفاتيح دفع نصًّا صريحًا في قاعدة بيانات حقيقية.
#     إيقاف الإقلاع أرخص من الاثنين.
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY")


# ═══════════════════════════════════════════════════════════
#  تشديد HTTPS
# ═══════════════════════════════════════════════════════════

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=31536000)  # سنة
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])


# ═══════════════════════════════════════════════════════════
#  السجلات
# ═══════════════════════════════════════════════════════════

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {process:d} {thread:d} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("DJANGO_LOG_LEVEL", default="INFO"),
    },
    "loggers": {
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
