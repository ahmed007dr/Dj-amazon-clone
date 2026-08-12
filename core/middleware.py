"""
وسائط البنية التحتية المشتركة.
"""

from django.conf import settings
from django.utils import translation
from django.utils.deprecation import MiddlewareMixin

FALLBACK_LANGUAGE = "ar"

#: تُوضع على الطلب حين تحدَّد اللغة من ترويسة صريحة —
#: عندها لا يجوز لتفضيل المستخدم أن يدهسها.
EXPLICIT_FLAG = "_language_from_header"


def supported_languages() -> set[str]:
    return {code for code, _name in settings.LANGUAGES}


def language_from_header(request) -> str | None:
    header = request.META.get("HTTP_ACCEPT_LANGUAGE", "")
    if not header:
        return None

    supported = supported_languages()
    for chunk in header.split(","):
        code = chunk.split(";")[0].strip().lower()[:2]
        if code in supported:
            return code
    return None


def default_language() -> str:
    default = getattr(settings, "LANGUAGE_CODE", FALLBACK_LANGUAGE)[:2]
    return default if default in supported_languages() else FALLBACK_LANGUAGE


class LanguageMiddleware(MiddlewareMixin):
    """
    المرحلة الأولى من تفاوض اللغة — **الترويسة فقط**.

    ⚠️  لماذا مرحلتان؟

        مع JWT تحدث المصادقة في طبقة DRF، أي **بعد** كل الوسائط.
        فـ `request.user` هنا مجهول دائمًا ولا يمكن قراءة تفضيله.

        لذا:
          • هنا      → الترويسة الصريحة (بلا استعلام قاعدة بيانات)
          • في طبقة  → تفضيل المستخدم، حين لا توجد ترويسة صريحة
            المصادقة   (`accounts.authentication.apply_user_language`)

        الترتيب النهائي:
            ترويسة صريحة  ←  تفضيل المستخدم  ←  الافتراضي  ←  العربية

    الترويسة تسبق التفضيل عمدًا: من يفتح اللوحة بالإنجليزية لجلسة
    واحدة، طلبه الصريح يُحترم.
    """

    def process_request(self, request):
        header_language = language_from_header(request)

        setattr(request, EXPLICIT_FLAG, header_language is not None)
        language = header_language or default_language()

        translation.activate(language)
        request.LANGUAGE_CODE = language

    def process_response(self, request, response):
        language = getattr(request, "LANGUAGE_CODE", None)
        if language:
            response.headers.setdefault("Content-Language", language)
        translation.deactivate()
        return response
