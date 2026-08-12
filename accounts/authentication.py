"""
مصادقة JWT مع فحص حالة الحساب.

⚠️  الطبقة الثالثة من آلية الإبطال الفوري (ADR-16).

    بدونها، إيقاف حساب لا يقطع وصوله فورًا — التوكن الصادر يبقى
    صالحًا حتى انتهاء عمره. زر «إيقاف الحساب» يصير زخرفيًا.
"""

from django.utils import translation
from rest_framework_simplejwt.authentication import JWTAuthentication

from accounts.models import AccountStatus
from accounts.services import is_suspended_cached
from core.errors import BusinessError, ErrorCode
from core.middleware import EXPLICIT_FLAG, supported_languages


def apply_user_language(request, user) -> None:
    """
    المرحلة الثانية من تفاوض اللغة.

    تُطبَّق فور معرفة المستخدم — وهي مع JWT لحظة لا تقع إلا بعد
    انتهاء كل الوسائط. انظر `core.middleware.LanguageMiddleware`.

    ⚠️  الترويسة الصريحة لا تُدهَس أبدًا.
    """
    if request is None:
        return

    # ⚠️  DRF يغلّف HttpRequest في Request خاص به.
    #     `process_response` في الوسيط يقرأ الأصلي، فالإسناد على
    #     الغلاف وحده لا يصل إليه.
    http_request = getattr(request, "_request", request)

    if getattr(http_request, EXPLICIT_FLAG, False):
        return

    preferred = getattr(user, "preferred_language", None)
    if preferred and preferred in supported_languages():
        translation.activate(preferred)
        http_request.LANGUAGE_CODE = preferred


class StatefulJWTAuthentication(JWTAuthentication):
    """
    ترتيب الفحص مقصود — الأرخص أولًا:

        1. مجموعة الموقوفين في الكاش   O(1) بلا استعلام
        2. حالة الحساب في القاعدة       المستخدم محمَّل أصلًا
        3. is_active                    الشرط الأساسي
    """

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is not None:
            apply_user_language(request, result[0])
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
