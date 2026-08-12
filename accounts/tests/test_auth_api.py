"""
اختبارات واجهات المصادقة.

تغطي دورة الحياة الكاملة: تسجيل ← تفعيل ← دخول ← نسيان ← استرجاع ← دخول
وتحرس الخصائص الأمنية التي كانت مكسورة في الكود القديم.
"""

import pytest
from django.core import mail as django_mail
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountStatus, SecurityToken, TokenPurpose, User, UserSession

PASSWORD = "Str0ng-Test-Pass!23"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture(autouse=True)
def _clear_throttles():
    """تحديد المعدل يُسقط اختبارات متتابعة لولا التفريغ."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def active_user(db):
    user = User.objects.create_user(email="active@test.local", password=PASSWORD)
    user.is_active = True
    user.email_verified_at = "2026-01-01T00:00:00Z"
    user.save()
    return user


# ═══════════════════════════════════════════════════════════
#  التسجيل والتفعيل
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRegistration:
    def test_register_creates_inactive_user(self, client):
        """
        ⛔ الكود القديم: `form.save()` بعد `commit=False` كان يحفظ
           مستخدمًا نشطًا ويتجاهل `is_active=False` — فكان نظام
           التفعيل زخرفيًا بالكامل ويمكن تجاوزه.
        """
        response = client.post(
            reverse("v1:accounts:register"),
            {"email": "new@test.local", "password": PASSWORD},
            format="json",
        )
        assert response.status_code == 201

        user = User.objects.get(email="new@test.local")
        assert not user.is_active
        assert not user.is_email_verified
        assert not user.can_authenticate

    def test_register_sends_verification_email(self, client):
        django_mail.outbox.clear()
        client.post(
            reverse("v1:accounts:register"),
            {"email": "mail@test.local", "password": PASSWORD},
            format="json",
        )
        assert len(django_mail.outbox) == 1
        assert "فعّل" in django_mail.outbox[0].subject

    def test_register_respects_preferred_language(self, client):
        """البريد يصل بلغة المستلم لا بلغة الطلب."""
        django_mail.outbox.clear()
        client.post(
            reverse("v1:accounts:register"),
            {"email": "en@test.local", "password": PASSWORD, "preferred_language": "en"},
            format="json",
            HTTP_ACCEPT_LANGUAGE="ar",
        )
        assert "Activate" in django_mail.outbox[0].subject

    def test_duplicate_email_rejected(self, client, active_user):
        response = client.post(
            reverse("v1:accounts:register"),
            {"email": "active@test.local", "password": PASSWORD},
            format="json",
        )
        assert response.status_code == 400
        assert response.data["code"] == "VALIDATION_ERROR"
        assert "email" in response.data["fields"]

    def test_weak_password_rejected(self, client):
        response = client.post(
            reverse("v1:accounts:register"),
            {"email": "weak@test.local", "password": "12345678"},
            format="json",
        )
        assert response.status_code == 400
        assert "password" in response.data["fields"]

    def test_verify_email_activates_and_returns_tokens(self, client):
        client.post(
            reverse("v1:accounts:register"),
            {"email": "verify@test.local", "password": PASSWORD},
            format="json",
        )
        user = User.objects.get(email="verify@test.local")

        # الرمز الصريح لا يُخزَّن — نصدر واحدًا جديدًا للاختبار
        from accounts import services

        _, raw = services.issue_token(user, TokenPurpose.EMAIL_VERIFICATION)

        response = client.post(reverse("v1:accounts:verify-email"), {"token": raw}, format="json")
        assert response.status_code == 200
        assert "access" in response.data

        user.refresh_from_db()
        assert user.is_active
        assert user.is_email_verified

    def test_verification_token_is_single_use(self, client, active_user):
        from accounts import services

        _, raw = services.issue_token(active_user, TokenPurpose.EMAIL_VERIFICATION)
        url = reverse("v1:accounts:verify-email")

        assert client.post(url, {"token": raw}, format="json").status_code == 200
        assert client.post(url, {"token": raw}, format="json").status_code == 400


# ═══════════════════════════════════════════════════════════
#  الدخول
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestLogin:
    def test_login_returns_tokens_and_opens_session(self, client, active_user):
        response = client.post(
            reverse("v1:accounts:login"),
            {"identifier": "active@test.local", "password": PASSWORD},
            format="json",
        )
        assert response.status_code == 200
        assert "access" in response.data
        assert "refresh" in response.data
        assert UserSession.objects.filter(user=active_user, logout_at__isnull=True).exists()

    def test_login_by_phone(self, client, active_user):
        active_user.phone = "+201001234567"
        active_user.save()

        response = client.post(
            reverse("v1:accounts:login"),
            {"identifier": "+201001234567", "password": PASSWORD},
            format="json",
        )
        assert response.status_code == 200

    def test_unverified_user_cannot_login(self, client, db):
        User.objects.create_user(email="unverified@test.local", password=PASSWORD)
        response = client.post(
            reverse("v1:accounts:login"),
            {"identifier": "unverified@test.local", "password": PASSWORD},
            format="json",
        )
        assert response.status_code == 400

    def test_suspended_user_cannot_login(self, client, active_user):
        """⛔ الباكند القديم لم يفحص الحالة إطلاقًا."""
        active_user.status = AccountStatus.SUSPENDED
        active_user.save()

        response = client.post(
            reverse("v1:accounts:login"),
            {"identifier": "active@test.local", "password": PASSWORD},
            format="json",
        )
        assert response.status_code == 400

    def test_failure_message_does_not_reveal_account_existence(self, client, active_user):
        """
        التمييز بين «بريد غير مسجل» و«كلمة مرور خاطئة» يحوّل شاشة
        الدخول إلى أداة لكشف الحسابات.
        """
        url = reverse("v1:accounts:login")

        unknown = client.post(
            url, {"identifier": "nobody@test.local", "password": PASSWORD}, format="json"
        )
        wrong_pw = client.post(
            url,
            {"identifier": "active@test.local", "password": "WrongPass!123"},
            format="json",
        )

        assert unknown.status_code == wrong_pw.status_code == 400
        assert unknown.data["fields"] == wrong_pw.data["fields"]


# ═══════════════════════════════════════════════════════════
#  استرجاع كلمة المرور
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPasswordReset:
    def test_response_is_identical_for_unknown_email(self, client, active_user):
        """⚠️  رد مختلف = أداة لكشف الحسابات المسجلة."""
        url = reverse("v1:accounts:password-reset")

        known = client.post(url, {"email": "active@test.local"}, format="json")
        unknown = client.post(url, {"email": "nobody@test.local"}, format="json")

        assert known.status_code == unknown.status_code == 200
        assert known.data == unknown.data

    def test_reset_flow_end_to_end(self, client, active_user):
        from accounts import services

        _, raw = services.issue_token(active_user, TokenPurpose.PASSWORD_RESET)
        new_password = "Brand-New-Pass!456"

        response = client.post(
            reverse("v1:accounts:password-reset-confirm"),
            {"token": raw, "new_password": new_password},
            format="json",
        )
        assert response.status_code == 200

        active_user.refresh_from_db()
        assert active_user.check_password(new_password)

        # الدخول بالجديدة يعمل
        assert (
            client.post(
                reverse("v1:accounts:login"),
                {"identifier": "active@test.local", "password": new_password},
                format="json",
            ).status_code
            == 200
        )

    def test_reset_revokes_all_sessions(self, client, active_user):
        """من عرف كلمة المرور القديمة يجب أن يفقد وصوله فورًا."""
        from accounts import services

        services.open_session(active_user, session_key="session-to-kill")

        _, raw = services.issue_token(active_user, TokenPurpose.PASSWORD_RESET)
        client.post(
            reverse("v1:accounts:password-reset-confirm"),
            {"token": raw, "new_password": "Brand-New-Pass!456"},
            format="json",
        )

        assert not UserSession.objects.filter(user=active_user, logout_at__isnull=True).exists()

    def test_token_is_single_use(self, client, active_user):
        from accounts import services

        _, raw = services.issue_token(active_user, TokenPurpose.PASSWORD_RESET)
        url = reverse("v1:accounts:password-reset-confirm")
        payload = {"token": raw, "new_password": "Brand-New-Pass!456"}

        assert client.post(url, payload, format="json").status_code == 200
        assert client.post(url, payload, format="json").status_code == 400

    def test_token_is_stored_hashed(self, active_user):
        """تسريب القاعدة يجب ألا يمنح القدرة على إعادة التعيين."""
        from accounts import services

        record, raw = services.issue_token(active_user, TokenPurpose.PASSWORD_RESET)
        assert raw not in record.token_hash
        assert not SecurityToken.objects.filter(token_hash=raw).exists()

    def test_issuing_new_token_invalidates_previous(self, active_user):
        from accounts import services

        _, first = services.issue_token(active_user, TokenPurpose.PASSWORD_RESET)
        _, second = services.issue_token(active_user, TokenPurpose.PASSWORD_RESET)

        from core.errors import BusinessError

        with pytest.raises(BusinessError):
            services.consume_token(first, TokenPurpose.PASSWORD_RESET)

        assert services.consume_token(second, TokenPurpose.PASSWORD_RESET)


# ═══════════════════════════════════════════════════════════
#  الإيقاف الفوري  (ADR-16)
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSuspensionIsImmediate:
    def test_suspension_blocks_existing_token_at_once(self, client, active_user):
        """
        ⚠️  جوهر ADR-16.

        بلا الطبقة الثالثة (مجموعة الكاش) يظل التوكن الصادر صالحًا
        حتى انتهاء عمره — أي أن الموقوف يواصل العمل ١٠ دقائق.
        """
        login = client.post(
            reverse("v1:accounts:login"),
            {"identifier": "active@test.local", "password": PASSWORD},
            format="json",
        )
        access = login.data["access"]
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        assert client.get(reverse("v1:accounts:me")).status_code == 200

        from accounts import services

        services.suspend_account(active_user, reason="مخالفة")

        # نفس التوكن — يجب أن يُرفض فورًا
        response = client.get(reverse("v1:accounts:me"))
        assert response.status_code == 401
        assert response.data["code"] == "ACCOUNT_SUSPENDED"

    def test_suspension_closes_sessions_and_logs_change(self, active_user):
        from accounts import services
        from accounts.models import AccountStatusChange

        services.open_session(active_user, session_key="live-session")
        services.suspend_account(active_user, reason="اختبار")

        assert not UserSession.objects.filter(user=active_user, logout_at__isnull=True).exists()

        change = AccountStatusChange.objects.get(user=active_user)
        assert change.to_status == AccountStatus.SUSPENDED
        assert change.reason == "اختبار"

    def test_reactivation_restores_access(self, client, active_user):
        from accounts import services

        services.suspend_account(active_user, reason="اختبار")
        services.activate_account(active_user, reason="انتهى السبب")

        assert not services.is_suspended_cached(active_user.pk)
        assert (
            client.post(
                reverse("v1:accounts:login"),
                {"identifier": "active@test.local", "password": PASSWORD},
                format="json",
            ).status_code
            == 200
        )


# ═══════════════════════════════════════════════════════════
#  الجلسات
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSessions:
    def test_user_sees_only_own_sessions(self, client, active_user):
        other = User.objects.create_user(email="other@test.local", password=PASSWORD)
        other.is_active = True
        other.save()

        from accounts import services

        services.open_session(active_user, session_key="mine")
        services.open_session(other, session_key="theirs")

        client.force_authenticate(user=active_user)
        response = client.get(reverse("v1:accounts:sessions"))

        assert response.status_code == 200
        assert len(response.data) == 1

    def test_cannot_revoke_another_users_session(self, client, active_user):
        """
        ⚠️  فحص الملكية — الثغرة الأشيع في الكود القديم (IDOR).
            و`404` لا `403` حتى لا يصير الفرق أداة تعداد.
        """
        other = User.objects.create_user(email="victim@test.local", password=PASSWORD)
        from accounts import services

        victim_session = services.open_session(other, session_key="victim")

        client.force_authenticate(user=active_user)
        response = client.post(reverse("v1:accounts:session-revoke", args=[victim_session.pk]))

        assert response.status_code == 404
        victim_session.refresh_from_db()
        assert victim_session.logout_at is None


# ═══════════════════════════════════════════════════════════
#  تفاوض اللغة
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestLanguageNegotiation:
    """
    ⚠️  تستخدم توكنًا حقيقيًا لا `force_authenticate`.

        تفضيل المستخدم يُطبَّق في طبقة المصادقة، و`force_authenticate`
        يتجاوزها — فيختبر مسارًا لا يسلكه أي طلب حقيقي.
    """

    @staticmethod
    def _authenticate(client, user):
        from accounts import services

        tokens = services.issue_jwt(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    def test_header_wins_over_user_preference(self, client, active_user):
        active_user.preferred_language = "ar"
        active_user.save()
        self._authenticate(client, active_user)

        response = client.get(reverse("v1:accounts:me"), HTTP_ACCEPT_LANGUAGE="en")
        assert response.headers["Content-Language"] == "en"

    def test_falls_back_to_user_preference(self, client, active_user):
        active_user.preferred_language = "en"
        active_user.save()
        self._authenticate(client, active_user)

        response = client.get(reverse("v1:accounts:me"))
        assert response.headers["Content-Language"] == "en"

    def test_unsupported_language_falls_back_to_preference(self, client, active_user):
        active_user.preferred_language = "en"
        active_user.save()
        self._authenticate(client, active_user)

        response = client.get(reverse("v1:accounts:me"), HTTP_ACCEPT_LANGUAGE="fr,de")
        assert response.headers["Content-Language"] == "en"

    def test_anonymous_request_uses_default(self, client):
        response = client.post(
            reverse("v1:accounts:password-reset"),
            {"email": "nobody@test.local"},
            format="json",
            HTTP_ACCEPT_LANGUAGE="fr",
        )
        assert response.headers["Content-Language"] == "ar"
