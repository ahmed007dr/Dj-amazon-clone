"""
Identity domain endpoints.

⚠️  Deliberately thin: validate ← call a service ← respond.
    Any business logic here violates the mandatory request flow.
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
from core.errors import BusinessError, ErrorCode
from mailing import services as mail_services
from mailing import templates as mail_templates

User = get_user_model()


# ═══════════════════════════════════════════════════════════
#  Rate limiting
# ═══════════════════════════════════════════════════════════


class LoginThrottle(AnonRateThrottle):
    scope = "login"


class RegisterThrottle(AnonRateThrottle):
    scope = "register"


class PasswordResetThrottle(AnonRateThrottle):
    scope = "password_reset"


# ═══════════════════════════════════════════════════════════
#  Registration and activation
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
        # ⚠️  Inactive until the email is confirmed.
        #     The legacy code saved an active user immediately and ignored
        #     is_active=False — making the activation system entirely decorative.

        _, raw_token = services.issue_token(user, TokenPurpose.EMAIL_VERIFICATION, request=request)
        mail_services.send_to_user(
            mail_templates.VERIFY_EMAIL.key,
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
            mail_services.send_to_user(
                mail_templates.VERIFY_EMAIL.key,
                user,
                {"link": services.frontend_url(f"/auth/verify-email?token={raw_token}")},
            )

        # ⚠️  A uniform response — it never reveals which email is registered and which is not
        return Response({"message": "إن كان البريد مسجلًا وغير مفعّل فستصلك رسالة."})


# ═══════════════════════════════════════════════════════════
#  Login and logout
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

        services.open_session(
            user,
            session_key=RefreshToken(tokens["refresh"])["jti"],
            request=request,
        )
        services.touch_activity(user.pk)

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
#  Password
# ═══════════════════════════════════════════════════════════


class PasswordResetRequestAPI(APIView):
    """
    ⚠️  Always returns `200` — whether the email is registered or not.

    A different response per case turns this endpoint into an account discovery tool.
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
            mail_services.send_to_user(
                mail_templates.PASSWORD_RESET.key,
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
        mail_services.send_to_user(mail_templates.PASSWORD_CHANGED.key, user, {})

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

        # Every session is ended — anyone who knew the old password loses access
        services.revoke_all_tokens(user)
        services.close_all_sessions(user, revoked=True)
        mail_services.send_to_user(mail_templates.PASSWORD_CHANGED.key, user, {})

        return Response({"message": "تم تغيير كلمة المرور. سجّل الدخول من جديد."})


# ═══════════════════════════════════════════════════════════
#  Email change — confirmation from both addresses
# ═══════════════════════════════════════════════════════════


class EmailChangeRequestAPI(APIView):
    """
    Request an email change.

    ⚠️  Two messages, not one:

        the old one  →  a warning: "a change to your email was requested". A
                        compromised account's owner finds out.
        the new one  →  a confirmation code. It proves the requester owns the address.

        Sending to the new address alone means an attacker changes the email
        silently and then takes over the account through "forgot password".
    """

    permission_classes = [IsAuthenticated]
    serializer_class = s.EmailChangeRequestSerializer

    def post(self, request):
        serializer = s.EmailChangeRequestSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        new_email = serializer.validated_data["new_email"]

        _, raw_token = services.issue_token(
            request.user,
            TokenPurpose.EMAIL_CHANGE,
            request=request,
            new_email=new_email,
        )

        # 1 — warning to the old address
        mail_services.send_to_user(
            mail_templates.EMAIL_CHANGE_ALERT.key, request.user, {"new_email": new_email}
        )

        # 2 — confirmation to the new address
        mail_services.send_mail(
            mail_templates.EMAIL_CHANGE_CONFIRM.key,
            to=new_email,
            language=request.user.preferred_language,
            context={
                "name": request.user.get_short_name(),
                "link": services.frontend_url(f"/auth/confirm-email?token={raw_token}"),
            },
        )

        return Response({"message": "أُرسل رابط التأكيد إلى بريدك الجديد."})


class EmailChangeConfirmAPI(APIView):
    permission_classes = [AllowAny]
    serializer_class = s.EmailChangeConfirmSerializer

    def post(self, request):
        serializer = s.EmailChangeConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        services.confirm_email_change(serializer.validated_data["token"])

        # Email is the identifier — changing it invalidates every session
        return Response({"message": "تم تغيير البريد. سجّل الدخول من جديد."})


# ═══════════════════════════════════════════════════════════
#  The current account
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
    """The user's sessions — so they can see their devices and end any they do not recognise."""

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
        # ⚠️  Filtering by user is mandatory — without it this is an IDOR
        session = UserSession.objects.filter(
            pk=session_id, user=request.user, logout_at__isnull=True
        ).first()

        if session is None:
            # ⚠️  404 for both nonexistent and not-owned — the difference is an enumeration tool
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        services.close_session(session, revoked=True)
        return Response(status=status.HTTP_204_NO_CONTENT)
