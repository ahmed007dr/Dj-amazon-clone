"""
اختبارات وضع معاينة الأدمن.

⚠️  المعاينة أداة خطرة بطبيعتها — تسمح لمستخدم بأن يُقيَّم كنوع
    حساب آخر. هذه الاختبارات تحرس القيود التي تمنعها من أن تصير
    جسرًا لانتحال الهوية.
"""

import pytest

from access.preview import (
    PREVIEW_HEADER,
    PREVIEW_VERIFIED_HEADER,
    AnonymousPreview,
    build_preview_user,
    resolve_preview,
)
from access.services import evaluate
from accounts.models import AccountType, User, VerificationStatus
from administration.models import AdminProfile

PASSWORD = "Str0ng-Test-Pass!23"


class FakeRequest:
    def __init__(self, user, method="GET", **headers):
        self.user = user
        self.method = method
        self.META = headers
        self.path = "/api/v1/catalog/products/"


@pytest.fixture
def admin(db):
    user = User.objects.create_user(
        email="admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    user.is_active = True
    user.save()
    AdminProfile.objects.create(user=user)
    return user


@pytest.fixture
def customer(db):
    user = User.objects.create_user(
        email="customer@test.local", password=PASSWORD, account_type=AccountType.STUDENT
    )
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def policies(db):
    from django.core.management import call_command

    from access.models import AccessPolicy

    call_command("seed_access_policies", verbosity=0)
    return {p.code: p for p in AccessPolicy.objects.all()}


@pytest.mark.django_db
class TestPreviewGuards:
    def test_non_admin_cannot_preview(self, customer):
        """⚠️  أخطر اختبار هنا — بدونه المعاينة انتحال هوية."""
        request = FakeRequest(customer, **{PREVIEW_HEADER: AccountType.PHARMACY})
        assert resolve_preview(request) is None

    def test_anonymous_cannot_preview(self, db):
        from django.contrib.auth.models import AnonymousUser

        request = FakeRequest(AnonymousUser(), **{PREVIEW_HEADER: AccountType.PHARMACY})
        assert resolve_preview(request) is None

    def test_write_methods_ignore_preview(self, admin):
        """
        ⚠️  المعاينة للقراءة فقط.

        السماح بالكتابة تحتها يعني أدمن ينشئ طلبات باسم نوع حساب
        آخر — ونسبة تجارية خاطئة في كل تقرير بعدها.
        """
        for method in ("POST", "PATCH", "PUT", "DELETE"):
            request = FakeRequest(admin, method=method, **{PREVIEW_HEADER: AccountType.PHARMACY})
            assert resolve_preview(request) is None, method

    def test_invalid_account_type_is_ignored(self, admin):
        request = FakeRequest(admin, **{PREVIEW_HEADER: "SUPER_ADMIN"})
        assert resolve_preview(request) is None

    def test_no_header_means_no_preview(self, admin):
        assert resolve_preview(FakeRequest(admin)) is None

    def test_preview_user_has_no_permissions(self, admin):
        """
        الأدمن لا «يستعير» صلاحياته للنوع الذي يعاينه — وإلا رأى
        ما لا يراه ذلك النوع فعلًا، فبطل معنى المعاينة.
        """
        preview = build_preview_user(AccountType.PHARMACY, verified=True)
        assert preview.has_perm("access.view_accesspolicy") is False


@pytest.mark.django_db
class TestPreviewEvaluation:
    def test_preview_as_guest_sees_public_only(self, policies):
        guest = AnonymousPreview()

        assert evaluate(guest, policies["public"]).allowed
        assert not evaluate(guest, policies["registered"]).allowed
        assert not evaluate(guest, policies["students"]).allowed

    def test_preview_as_student(self, policies):
        student = build_preview_user(AccountType.STUDENT)

        assert evaluate(student, policies["public"]).allowed
        assert evaluate(student, policies["students"]).allowed
        assert not evaluate(student, policies["professionals"]).allowed
        assert not evaluate(student, policies["wholesale"]).allowed

    def test_preview_verified_flag_matters(self, policies):
        unverified = build_preview_user(AccountType.PHARMACY, verified=False)
        verified = build_preview_user(AccountType.PHARMACY, verified=True)

        assert not evaluate(unverified, policies["pharmacy_only"]).allowed
        assert evaluate(verified, policies["pharmacy_only"]).allowed

    def test_admin_previewing_narrows_never_widens(self, admin, policies):
        """
        المعاينة **تُضيّق** الرؤية ولا توسّعها.

        الأدمن يرى كل شيء بصفته؛ وتحت المعاينة يرى ما يراه النوع
        المُعايَن فقط.
        """
        admin.verification_status = VerificationStatus.VERIFIED
        admin.save()

        student_preview = build_preview_user(AccountType.STUDENT)
        assert not evaluate(student_preview, policies["pharmacy_only"]).allowed


@pytest.mark.django_db
class TestPreviewAudit:
    def test_preview_is_logged(self, admin):
        from access.preview import log_preview
        from core.models.audit import AuditLog

        preview = build_preview_user(AccountType.PHARMACY, verified=True)
        request = FakeRequest(admin, REMOTE_ADDR="127.0.0.1")
        log_preview(request, preview)

        entry = AuditLog.objects.get(actor=admin)
        assert "PHARMACY" in entry.object_repr
        assert entry.changes["verified"] is True

    def test_verified_header_parsing(self, admin):
        for raw, expected in (
            ("1", True),
            ("true", True),
            ("yes", True),
            ("0", False),
            ("", False),
        ):
            request = FakeRequest(
                admin,
                **{PREVIEW_HEADER: AccountType.PHARMACY, PREVIEW_VERIFIED_HEADER: raw},
            )
            preview = resolve_preview(request)
            assert preview.is_verified is expected, raw
