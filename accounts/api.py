"""
واجهات نطاق الهوية.

⚠️  رقيقة عمدًا: تحقق ← استدعاء خدمة ← استجابة.
    أي منطق عمل هنا انتهاك لتدفق الطلب الإلزامي.
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from accounts import serializers as s
from accounts import services
from accounts.models import TokenPurpose, UserSession
from core import mail
from core.errors import BusinessError, ErrorCode

User = get_user_model()


# ═══════════════════════════════════════════════════════════
#  تحديد المعدل
# ═══════════════════════════════════════════════════════════


class LoginThrottle(AnonRateThrottle):
    scope = "login"


class RegisterThrottle(AnonRateThrottle):
    scope = "register"


class PasswordResetThrottle(AnonRateThrottle):
    scope = "password_reset"


# ═══════════════════════════════════════════════════════════
#  التسجيل والتفعيل
# ═══════════════════════════════════════════════════════════


class RegisterAPI(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [RegisterThrottle]
    serializer_class = s.RegisterSerializer

    @transaction.atomic
    def post(self, request):
        serializer = s.RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = User.objects.create_user(
            email=data["email"],
            password=data["password"],
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            phone=data.get("phone") or None,
            account_type=data["account_type"],
            preferred_language=data["preferred_language"],
        )
        # ⚠️  غير مفعّل حتى تأكيد البريد.
        #     الكود القديم كان يحفظ مستخدمًا نشطًا فورًا ويتجاهل
        #     is_active=False — فكان نظام التفعيل زخرفيًا بالكامل.

        _, raw_token = services.issue_token(user, TokenPurpose.EMAIL_VERIFICATION, request=request)
        mail.send_to_user(
            mail.VERIFY_EMAIL.key,
            user,
            {"link": services.frontend_url(f"/auth/verify-email?token={raw_token}")},
        )

        return Response(
            {
                "message": "تم إنشاء الحساب. تفقّد بريدك لتفعيله.",
                "user": s.UserSerializer(user).data,
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyEmailAPI(APIView):
    permission_classes = [AllowAny]
    serializer_class = s.VerifyEmailSerializer

    def post(self, request):
        serializer = s.VerifyEmailSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = services.verify_email(serializer.validated_data["token"])
        tokens = services.issue_jwt(user)

        return Response({**tokens, "user": s.UserSerializer(user).data})


class ResendVerificationAPI(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle]
    serializer_class = s.PasswordResetRequestSerializer

    def post(self, request):
        serializer = s.PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.filter(
            email__iexact=serializer.validated_data["email"],
            email_verified_at__isnull=True,
        ).first()

        if user is not None:
            _, raw_token = services.issue_token(
                user, TokenPurpose.EMAIL_VERIFICATION, request=request
            )
            mail.send_to_user(
                mail.VERIFY_EMAIL.key,
                user,
                {"link": services.frontend_url(f"/auth/verify-email?token={raw_token}")},
            )

        # ⚠️  رد موحّد — لا يكشف أي بريد مسجل وأيه لا
        return Response({"message": "إن كان البريد مسجلًا وغير مفعّل فستصلك رسالة."})


# ═══════════════════════════════════════════════════════════
#  الدخول والخروج
# ═══════════════════════════════════════════════════════════


class LoginAPI(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]
    serializer_class = s.LoginSerializer

    def post(self, request):
        serializer = s.LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        tokens = services.issue_jwt(user)

        session = services.open_session(
            user,
            session_key=RefreshToken(tokens["refresh"])["jti"],
            request=request,
        )
        services.touch_activity(user.pk, session.session_key)

        user.last_login_at = timezone.now()
        user.save(update_fields=["last_login_at"])

        return Response({**tokens, "user": s.UserSerializer(user).data})


class LogoutAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="refresh مطلوب")

        try:
            token = RefreshToken(refresh)
            jti = token["jti"]
            token.blacklist()
        except Exception as exc:
            raise BusinessError(ErrorCode.TOKEN_INVALID) from exc

        session = UserSession.objects.filter(
            user=request.user, session_key=jti, logout_at__isnull=True
        ).first()
        if session is not None:
            services.close_session(session)

        return Response(status=status.HTTP_204_NO_CONTENT)


# ═══════════════════════════════════════════════════════════
#  كلمة المرور
# ═══════════════════════════════════════════════════════════


class PasswordResetRequestAPI(APIView):
    """
    ⚠️  يعيد `200` دائمًا — سواء كان البريد مسجلًا أو لا.

    رد مختلف لكل حالة يحوّل هذه النقطة إلى أداة لكشف الحسابات.
    """

    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetThrottle]
    serializer_class = s.PasswordResetRequestSerializer

    def post(self, request):
        serializer = s.PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.filter(email__iexact=serializer.validated_data["email"]).first()

        if user is not None:
            _, raw_token = services.issue_token(user, TokenPurpose.PASSWORD_RESET, request=request)
            mail.send_to_user(
                mail.PASSWORD_RESET.key,
                user,
                {"link": services.frontend_url(f"/auth/reset-password?token={raw_token}")},
            )

        return Response({"message": "إن كان البريد مسجلًا فستصلك رسالة."})


class PasswordResetConfirmAPI(APIView):
    permission_classes = [AllowAny]
    serializer_class = s.PasswordResetConfirmSerializer

    def post(self, request):
        serializer = s.PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = services.reset_password(
            serializer.validated_data["token"],
            serializer.validated_data["new_password"],
        )
        mail.send_to_user(mail.PASSWORD_CHANGED.key, user, {})

        return Response({"message": "تم تعيين كلمة المرور. سجّل الدخول من جديد."})


class PasswordChangeAPI(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = s.PasswordChangeSerializer

    @transaction.atomic
    def post(self, request):
        serializer = s.PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])

        # كل الجلسات تُنهى — من عرف القديمة يفقد وصوله
        services.revoke_all_tokens(user)
        services.close_all_sessions(user, revoked=True)
        mail.send_to_user(mail.PASSWORD_CHANGED.key, user, {})

        return Response({"message": "تم تغيير كلمة المرور. سجّل الدخول من جديد."})


# ═══════════════════════════════════════════════════════════
#  الحساب الحالي
# ═══════════════════════════════════════════════════════════


class MeAPI(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = s.UserSerializer

    def get(self, request):
        return Response(s.UserSerializer(request.user).data)

    def patch(self, request):
        serializer = s.UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class SessionListAPI(APIView):
    """جلسات المستخدم — ليرى أجهزته ويُنهي ما لا يعرفه."""

    permission_classes = [IsAuthenticated]
    serializer_class = s.UserSessionSerializer

    def get(self, request):
        sessions = UserSession.objects.filter(user=request.user, logout_at__isnull=True)
        return Response(
            s.UserSessionSerializer(
                sessions,
                many=True,
                context={"current_session_key": getattr(request.auth, "payload", {}).get("jti")},
            ).data
        )


class SessionRevokeAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, session_id):
        # ⚠️  الفلترة بالمستخدم إلزامية — بدونها IDOR
        session = UserSession.objects.filter(
            pk=session_id, user=request.user, logout_at__isnull=True
        ).first()

        if session is None:
            # ⚠️  404 لغير الموجود وغير المملوك معًا — الفرق أداة تعداد
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        services.close_session(session, revoked=True)
        return Response(status=status.HTTP_204_NO_CONTENT)
