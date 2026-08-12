"""
اختبارات نطاق إدارة النظام.

⚠️  يسكن هنا لا في `accounts/`.

    اختبار «المالك لا يُوقَف» يمس النطاقين، لكنه يستورد
    `administration.models`. وضعه في `accounts` استيراد صاعد
    (L1 ← L2) وقد أمسكه import-linter فورًا.

    القاعدة: الاختبار يسكن في النطاق **الأعلى** بين ما يلمسه —
    فالتبعية تبقى نازلة.
"""

import pytest

from accounts.models import AccountStatus, User
from administration.models import AdminProfile, AdminRole, AdminRoleAssignment

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

        other = User.objects.create_user(email="admin2@test.local", password=PASSWORD)
        second = AdminProfile.objects.create(user=other)

        assert first.admin_number.startswith("ADM-")
        assert first.admin_number != second.admin_number

    def test_only_one_owner_allowed(self, admin_user):
        """المالك واحد — تعدّده يجعل «من يملك النظام» سؤالًا بلا إجابة."""
        from django.db.utils import IntegrityError

        AdminProfile.objects.create(user=admin_user, is_owner=True)

        other = User.objects.create_user(email="admin3@test.local", password=PASSWORD)
        with pytest.raises(IntegrityError):
            AdminProfile.objects.create(user=other, is_owner=True)


@pytest.mark.django_db
class TestOwnerProtection:
    def test_owner_cannot_be_suspended(self, admin_user):
        """
        إيقاف المالك يقفل النظام على الجميع بلا طريق للعودة.
        """
        from accounts import services
        from core.errors import BusinessError

        AdminProfile.objects.create(user=admin_user, is_owner=True)

        with pytest.raises(BusinessError) as exc:
            services.suspend_account(admin_user, reason="محاولة")

        # الرسالة عامة ومترجمة؛ السياق يسكن في `detail` — وهذا مقصود:
        # منطق الفرونت يبني على `code` الثابت لا على النص المترجم.
        assert exc.value.code == "PERMISSION_DENIED"
        assert "مالك النظام" in exc.value.error_detail

        admin_user.refresh_from_db()
        assert admin_user.status == AccountStatus.ACTIVE

    def test_non_owner_admin_can_be_suspended(self, admin_user):
        from accounts import services

        AdminProfile.objects.create(user=admin_user, is_owner=False)
        services.suspend_account(admin_user, reason="مخالفة")

        admin_user.refresh_from_db()
        assert admin_user.status == AccountStatus.SUSPENDED


@pytest.mark.django_db
class TestAdminRoles:
    def test_role_assignment_tracks_period(self, admin_user):
        """
        الإسناد المنتهي يبقى محفوظًا — التدقيق يحتاج معرفة مَن كان
        يملك أي صلاحية وقت وقوع حدث ما.
        """
        from datetime import timedelta

        from django.utils import timezone

        profile = AdminProfile.objects.create(user=admin_user)
        role = AdminRole.objects.create(
            name_ar="مدير مالي", name_en="Finance Manager", code="finance_manager"
        )
        assignment = AdminRoleAssignment.objects.create(admin=profile, role=role)

        assert assignment.is_current

        assignment.to_date = timezone.now().date() - timedelta(days=1)
        assignment.save()
        assert not assignment.is_current

    def test_role_in_use_cannot_be_deleted(self, admin_user):
        """PROTECT — حذف دور مُسنَد يترك مديرين بصلاحيات معلّقة."""
        from django.db.models import ProtectedError

        profile = AdminProfile.objects.create(user=admin_user)
        role = AdminRole.objects.create(name_ar="مدقّق", name_en="Auditor", code="auditor")
        AdminRoleAssignment.objects.create(admin=profile, role=role)

        with pytest.raises(ProtectedError):
            role.hard_delete()
