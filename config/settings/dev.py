"""
إعدادات التطوير المحلي.

    DJANGO_SETTINGS_MODULE=config.settings.dev
"""

from .base import *
from .base import INSTALLED_APPS, MIDDLEWARE, env

DEBUG = env.bool("DJANGO_DEBUG", default=True)

ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1", "[::1]"],
)


# ── شريط التصحيح — بيئة التطوير فقط ────────────────────────
# وجوده في الإنتاج تسريب معلومات

INSTALLED_APPS += ["debug_toolbar"]
MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")


# ── أدوات التطوير — بيئة التطوير وحدها ─────────────────────
# ⚠️  `seed_dev` تُنشئ حسابات بكلمة مرور معروفة ومنشورة.
#
#     عدم تثبيت التطبيق في الإنتاج يجعل الأمر **غير موجود** هناك —
#     وهذا أقوى من فحص `if DEBUG` داخله، لأن متغيّر بيئة خاطئًا
#     واحدًا يقلب الفحص بينما لا يخلق أمرًا من العدم.

INSTALLED_APPS += ["devtools"]


# ── CORS — خادم Vite ───────────────────────────────────────
# ⚠️  الفرونت إند على منفذ آخر، فكل نداء منه طلب عابر للأصل.
#
#     بلا هذا يحجب المتصفح **كل** استجابة بصمت — تصل ٢٠٠ من
#     الخادم ويرفض المتصفح تسليمها للكود. والخطأ يظهر في وحدة
#     تحكّم المتصفح لا في سجل Django، فيُبحث عنه في المكان الخطأ.
#
#     التطوير وحده. الإنتاج يضبطها من CORS_ALLOWED_ORIGINS صراحةً.

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS",
    default=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
)

INTERNAL_IPS = ["127.0.0.1"]


# ── البريد ─────────────────────────────────────────────────
# الافتراضي: الطباعة في الطرفية بدل الإرسال الفعلي

EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)


# ⚠️  مدققات كلمة المرور تبقى كاملة كما في الإنتاج.
#     تخفيفها هنا يخلق فجوة بين البيئتين تُخفي أخطاء حتى النشر.
