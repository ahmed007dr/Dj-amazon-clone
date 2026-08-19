"""
System administration domain tests.

⚠️  These live here, not in `accounts/`.

    The "the owner is never suspended" test touches both domains, but it
    imports `administration.models`. Putting it in `accounts` is an upward
    import (L1 ← L2) and import-linter caught it immediately.

    The rule: a test lives in the **highest** domain among those it touches —
    so the dependency stays downward.
"""

import pytest

from accounts.models import AccountStatus, User
from administration.models import AdminProfile, AdminRole, AdminRoleAssignment
from core.testing import grant_all_domains

PASSWORD = "Str0ng-Test-Pass!23"


@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(email="admin@test.local", password=PASSWORD)
    user.is_active = True
    user.save()
    return user


@pytest.mark.django_db
class TestAdminProfile:
    def test_admin_number_is_generated_and_unique(self, admin_user):
        first = AdminProfile.objects.create(user=admin_user)
        grant_all_domains(admin_user)

        other = User.objects.create_user(email="admin2@test.local", password=PASSWORD)
        second = AdminProfile.objects.create(user=other)
        grant_all_domains(other)

        assert first.admin_number.startswith("ADM-")
        assert first.admin_number != second.admin_number

    def test_only_one_owner_allowed(self, admin_user):
        """There is exactly one owner — several make "who owns the system" a question with no answer."""
        from django.db.utils import IntegrityError

        AdminProfile.objects.create(user=admin_user, is_owner=True)

        grant_all_domains(admin_user)

        other = User.objects.create_user(email="admin3@test.local", password=PASSWORD)
        with pytest.raises(IntegrityError):
            AdminProfile.objects.create(user=other, is_owner=True)
            grant_all_domains(other)


@pytest.mark.django_db
class TestOwnerProtection:
    def test_owner_cannot_be_suspended(self, admin_user):
        """
        Suspending the owner locks the system away from everyone with no way back.
        """
        from accounts import services
        from core.errors import BusinessError

        AdminProfile.objects.create(user=admin_user, is_owner=True)

        grant_all_domains(admin_user)

        with pytest.raises(BusinessError) as exc:
            services.suspend_account(admin_user, reason="محاولة")

        # The message is generic and translated; the context lives in `detail` — deliberately:
        # frontend logic builds on the stable `code`, not on the translated text.
        assert exc.value.code == "PERMISSION_DENIED"
        assert "مالك النظام" in exc.value.error_detail

        admin_user.refresh_from_db()
        assert admin_user.status == AccountStatus.ACTIVE

    def test_non_owner_admin_can_be_suspended(self, admin_user):
        from accounts import services

        AdminProfile.objects.create(user=admin_user, is_owner=False)

        grant_all_domains(admin_user)
        services.suspend_account(admin_user, reason="مخالفة")

        admin_user.refresh_from_db()
        assert admin_user.status == AccountStatus.SUSPENDED


@pytest.mark.django_db
class TestAdminRoles:
    def test_role_assignment_tracks_period(self, admin_user):
        """
        An expired assignment is retained — auditing needs to know who held
        which permission at the moment an event occurred.
        """
        from datetime import timedelta

        from django.utils import timezone

        profile = AdminProfile.objects.create(user=admin_user)

        grant_all_domains(admin_user)
        role = AdminRole.objects.create(
            name_ar="مدير مالي", name_en="Finance Manager", code="finance_manager"
        )
        assignment = AdminRoleAssignment.objects.create(admin=profile, role=role)

        assert assignment.is_current

        assignment.to_date = timezone.localdate() - timedelta(days=1)
        assignment.save()
        assert not assignment.is_current

    def test_role_in_use_cannot_be_deleted(self, admin_user):
        """PROTECT — deleting an assigned role leaves administrators with dangling permissions."""
        from django.db.models import ProtectedError

        profile = AdminProfile.objects.create(user=admin_user)

        grant_all_domains(admin_user)
        role = AdminRole.objects.create(name_ar="مدقّق", name_en="Auditor", code="auditor")
        AdminRoleAssignment.objects.create(admin=profile, role=role)

        with pytest.raises(ProtectedError):
            role.hard_delete()
