"""Identity domain routes — /api/v1/auth/"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from accounts import api

app_name = "accounts"

urlpatterns = [
    # Registration and activation
    path("register/", api.RegisterAPI.as_view(), name="register"),
    path("verify-email/", api.VerifyEmailAPI.as_view(), name="verify-email"),
    path("resend-verification/", api.ResendVerificationAPI.as_view(), name="resend-verification"),
    # Login and logout
    path("login/", api.LoginAPI.as_view(), name="login"),
    path("logout/", api.LogoutAPI.as_view(), name="logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    # Password
    path("password/reset/", api.PasswordResetRequestAPI.as_view(), name="password-reset"),
    path(
        "password/reset/confirm/",
        api.PasswordResetConfirmAPI.as_view(),
        name="password-reset-confirm",
    ),
    path("password/change/", api.PasswordChangeAPI.as_view(), name="password-change"),
    # Email change — confirmation from both addresses
    path("email/change/", api.EmailChangeRequestAPI.as_view(), name="email-change"),
    path(
        "email/change/confirm/",
        api.EmailChangeConfirmAPI.as_view(),
        name="email-change-confirm",
    ),
    # The current account
    path("me/", api.MeAPI.as_view(), name="me"),
    path("sessions/", api.SessionListAPI.as_view(), name="sessions"),
    path(
        "sessions/<int:session_id>/revoke/", api.SessionRevokeAPI.as_view(), name="session-revoke"
    ),
]
