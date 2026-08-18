"""
إعدادات التطوير المحلي.

    DJANGO_SETTINGS_MODULE=config.settings.dev
"""

from .base import *
from .base import ALLOWED_HOSTS, CORS_ALLOWED_ORIGINS, INSTALLED_APPS, MIDDLEWARE, env

DEBUG = env.bool("DJANGO_DEBUG", default=True)

# ⚠️  الأسماء الثلاثة تُضاف إلى المشتقّ من `PUBLIC_API_DOMAIN` لا تحلّ محلّه.
#
#     المطوّر يفتح `localhost` تارة و`127.0.0.1` تارة — وهما مضيفان
#     مختلفان عند المتصفح وإن كانا نفس الجهاز.
ALLOWED_HOSTS = list(dict.fromkeys([*ALLOWED_HOSTS, "localhost", "127.0.0.1", "[::1]"]))


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
#     التطوير وحده. الإنتاج يبقى على الأصل المشتقّ من دومين الموقع.
#
# ⚠️  والتوأم مضاف هنا: `localhost` و`127.0.0.1` نفس الجهاز وأصلان
#     مختلفان عند المتصفح. المطوّر الذي يفتح أحدهما بينما الإعداد
#     يذكر الآخر يرى كل نداء محجوبًا بلا سطر واحد في سجل Django.

_CORS_TWINS = {"localhost": "127.0.0.1", "127.0.0.1": "localhost"}

CORS_ALLOWED_ORIGINS = list(
    dict.fromkeys(
        [
            *CORS_ALLOWED_ORIGINS,
            *(
                origin.replace(host, twin, 1)
                for origin in CORS_ALLOWED_ORIGINS
                for host, twin in _CORS_TWINS.items()
                if f"//{host}" in origin
            ),
        ]
    )
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
