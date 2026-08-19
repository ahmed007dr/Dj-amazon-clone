"""
Shared infrastructure middleware.
"""

from django.conf import settings
from django.utils import translation
from django.utils.deprecation import MiddlewareMixin

FALLBACK_LANGUAGE = "ar"

#: Set on the request when the language is determined by an explicit header —
#: at which point the user's preference must not override it.
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
    The first stage of language negotiation — **the header only**.

    ⚠️  Why two stages?

        With JWT, authentication happens in the DRF layer, that is **after** all
        middleware. So `request.user` here is always anonymous and its
        preference cannot be read.

        Hence:
          • here        → the explicit header (with no database query)
          • in the      → the user's preference, when there is no explicit header
            auth layer    (`accounts.authentication.apply_user_language`)

        The final order:
            explicit header  ←  user preference  ←  the default  ←  Arabic

    The header outranks the preference deliberately: someone opening the panel
    in English for a single session has their explicit request honoured.
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
