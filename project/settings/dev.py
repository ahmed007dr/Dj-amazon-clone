"""
إعدادات التطوير المحلي.

    DJANGO_SETTINGS_MODULE=project.settings.dev
"""

from .base import *  # noqa: F403
from .base import INSTALLED_APPS, MIDDLEWARE, env

DEBUG = env.bool('DJANGO_DEBUG', default=True)

ALLOWED_HOSTS = env.list(
    'DJANGO_ALLOWED_HOSTS',
    default=['localhost', '127.0.0.1', '[::1]'],
)


# ── شريط التصحيح — بيئة التطوير فقط ────────────────────────
# وجوده في الإنتاج تسريب معلومات

INSTALLED_APPS += ['debug_toolbar']
MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')

INTERNAL_IPS = ['127.0.0.1']


# ── البريد ─────────────────────────────────────────────────
# الافتراضي: الطباعة في الطرفية بدل الإرسال الفعلي

EMAIL_BACKEND = env(
    'EMAIL_BACKEND',
    default='django.core.mail.backends.console.EmailBackend',
)


# ── تخفيف قيود كلمة المرور أثناء التطوير ───────────────────

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
]
