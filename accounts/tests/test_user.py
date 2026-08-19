"""
User model tests.

They live in `accounts/`, not `core/` — a test follows its own domain.
Putting them in `core/tests` broke the boundary contract and import-linter
caught it immediately.
"""

import pytest

from accounts.models import AccountStatus, AccountType, User


@pytest.mark.django_db
class TestUserModel:
    def test_email_is_unique(self):
        """
        ⛔ The legacy backend called `get(email=...)` on a non-unique field
           ⟵ MultipleObjectsReturned on a duplicate email.
        """
        assert User._meta.get_field("email").unique

    def test_user_stays_thin(self):
        """
        `User` is for identity only. Any business field belongs on the persona
        profile in its own domain.

        This test is the actual guard for ADR-11 — without it the first business
        field creeps in three months later and the drift never stops.
        """
        forbidden = {
            "address",
            "city",
            "loyalty_points",
            "target",
            "commission",
            "balance",
            "credit_limit",
            "tax_number",
            "company_name",
            "employee_number",
            "customer_number",
            "department",
        }
        actual = {f.name for f in User._meta.get_fields()}
        leaked = forbidden & actual
        assert not leaked, f"حقول تجارية تسللت إلى User: {leaked}"

    def test_account_status_separate_from_verification(self):
        """
        A verified doctor may be suspended for a violation,
        and an active account may still be pending verification. Conflating the
        two concepts is a common mistake.
        """
        names = {f.name for f in User._meta.get_fields()}
        assert "status" in names
        assert "verification_status" in names


@pytest.mark.django_db
class TestAuthenticationGating:
    """
    ⛔ The legacy backend called `check_password` directly with no status check
       ⟵ suspended and unactivated users could log in.
    """

    def test_suspended_user_cannot_authenticate(self):
        user = User.objects.create_user(email="suspended@test.local", password="pw-for-test-12345")
        user.is_active = True
        user.save()
        assert user.can_authenticate

        user.status = AccountStatus.SUSPENDED
        user.save()
        assert not user.can_authenticate

    def test_blocked_user_cannot_authenticate(self):
        user = User.objects.create_user(email="blocked@test.local", password="pw-for-test-12345")
        user.is_active = True
        user.status = AccountStatus.BLOCKED
        user.save()
        assert not user.can_authenticate

    def test_inactive_user_cannot_authenticate(self):
        user = User.objects.create_user(email="inactive@test.local", password="pw-for-test-12345")
        assert not user.is_active  # Default: inactive until the email is confirmed
        assert not user.can_authenticate

    def test_backend_rejects_suspended_user(self):
        """The check is at the backend level, not on the model alone."""
        from accounts.backend import EmailOrPhoneBackend

        user = User.objects.create_user(email="backend@test.local", password="pw-for-test-12345")
        user.is_active = True
        user.save()

        backend = EmailOrPhoneBackend()
        assert (
            backend.authenticate(None, username="backend@test.local", password="pw-for-test-12345")
            == user
        )

        user.status = AccountStatus.SUSPENDED
        user.save()
        assert (
            backend.authenticate(None, username="backend@test.local", password="pw-for-test-12345")
            is None
        )

    def test_backend_accepts_email_case_insensitively(self):
        user = User.objects.create_user(email="case@test.local", password="pw-for-test-12345")
        user.is_active = True
        user.save()

        from accounts.backend import EmailOrPhoneBackend

        assert (
            EmailOrPhoneBackend().authenticate(
                None, username="CASE@TEST.LOCAL", password="pw-for-test-12345"
            )
            == user
        )

    def test_backend_rejects_wrong_password(self):
        from accounts.backend import EmailOrPhoneBackend

        user = User.objects.create_user(email="wrong@test.local", password="pw-for-test-12345")
        user.is_active = True
        user.save()

        assert (
            EmailOrPhoneBackend().authenticate(
                None, username="wrong@test.local", password="not-the-password"
            )
            is None
        )

    def test_backend_handles_unknown_email(self):
        from accounts.backend import EmailOrPhoneBackend

        assert (
            EmailOrPhoneBackend().authenticate(
                None, username="nobody@test.local", password="pw-for-test-12345"
            )
            is None
        )


@pytest.mark.django_db
class TestUserManager:
    def test_superuser_creation(self):
        admin = User.objects.create_superuser(
            email="admin@test.local", password="pw-for-test-12345"
        )
        assert admin.is_staff
        assert admin.is_superuser
        assert admin.account_type == AccountType.ADMIN
        assert admin.status == AccountStatus.ACTIVE
        assert admin.can_authenticate
        assert admin.is_email_verified

    def test_email_is_required(self):
        with pytest.raises(ValueError, match="البريد الإلكتروني إلزامي"):
            User.objects.create_user(email="", password="pw-for-test-12345")

    def test_email_is_normalised(self):
        user = User.objects.create_user(email="Mixed@TEST.local", password="pw-for-test-12345")
        assert user.email == "Mixed@test.local"  # The domain is lower-cased, not the local part


@pytest.mark.django_db
class TestSecurityToken:
    def test_token_expiry_and_single_use(self):
        from datetime import timedelta

        from django.utils import timezone

        from accounts.models import SecurityToken, TokenPurpose
        from core.identifiers import hash_token, secure_token

        user = User.objects.create_user(email="token@test.local", password="pw-for-test-12345")
        raw = secure_token()
        token = SecurityToken.objects.create(
            user=user,
            purpose=TokenPurpose.PASSWORD_RESET,
            token_hash=hash_token(raw),
            expires_at=timezone.now() + timedelta(minutes=30),
        )
        assert token.is_valid

        # The plaintext token is never stored
        assert raw not in token.token_hash

        token.used_at = timezone.now()
        token.save()
        assert not token.is_valid

    def test_expired_token_is_invalid(self):
        from datetime import timedelta

        from django.utils import timezone

        from accounts.models import SecurityToken, TokenPurpose
        from core.identifiers import hash_token, secure_token

        user = User.objects.create_user(email="expired@test.local", password="pw-for-test-12345")
        token = SecurityToken.objects.create(
            user=user,
            purpose=TokenPurpose.EMAIL_VERIFICATION,
            token_hash=hash_token(secure_token()),
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        assert not token.is_valid
