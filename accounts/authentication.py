"""
JWT authentication with an account status check.

⚠️  The third layer of the immediate revocation mechanism (ADR-16).

    Without it, suspending an account does not cut off access immediately — an
    already-issued token stays valid until it expires. The "suspend account"
    button becomes decorative.
"""

from django.utils import translation
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.models import AccountStatus
from accounts.services import is_suspended_cached, touch_activity
from core.errors import BusinessError, ErrorCode
from core.middleware import EXPLICIT_FLAG, supported_languages


def apply_user_language(request, user) -> None:
    """
    The second stage of language negotiation.

    Applied as soon as the user is known — a moment that, with JWT, only occurs
    after all middleware has finished. See `core.middleware.LanguageMiddleware`.

    ⚠️  An explicit header is never overridden.
    """
    if request is None:
        return

    # ⚠️  DRF wraps HttpRequest in its own Request.
    #     `process_response` in the middleware reads the original, so assigning to
    #     the wrapper alone never reaches it.
    http_request = getattr(request, "_request", request)

    if getattr(http_request, EXPLICIT_FLAG, False):
        return

    preferred = getattr(user, "preferred_language", None)
    if preferred and preferred in supported_languages():
        translation.activate(preferred)
        http_request.LANGUAGE_CODE = preferred


class StatefulJWTAuthentication(JWTAuthentication):
    """
    The check order is deliberate — cheapest first:

        1. the suspended set in the cache   O(1), no query
        2. the account status in the DB     the user is already loaded
        3. is_active                        the baseline condition
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            user = result[0]
            apply_user_language(request, user)

            # ⚠️  The presence heartbeat lives **here**, not in middleware.
            #
            #     With JWT, authentication happens in the DRF layer — that is, after all
            #     middleware; so `request.user` is always anonymous in any of them. This is
            #     the only point every authenticated request passes through knowing its owner.
            #
            #     And the heartbeat goes to the cache, not the database — see `touch_activity`.
            touch_activity(user.pk)
        return result

    def get_user(self, validated_token):
        user_id = validated_token.get("user_id")

        if user_id is not None and is_suspended_cached(user_id):
            raise BusinessError(ErrorCode.ACCOUNT_SUSPENDED, status_code=401)

        user = super().get_user(validated_token)

        if user.status == AccountStatus.BLOCKED:
            raise BusinessError(ErrorCode.ACCOUNT_BLOCKED, status_code=401)

        if user.status == AccountStatus.SUSPENDED:
            raise BusinessError(ErrorCode.ACCOUNT_SUSPENDED, status_code=401)

        if not user.is_active:
            raise BusinessError(ErrorCode.EMAIL_NOT_VERIFIED, status_code=401)

        return user
