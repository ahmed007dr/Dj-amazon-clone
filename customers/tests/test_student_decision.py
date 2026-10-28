"""
Deciding a student from their data — the admin side, with no document needed.

⚠️  The review queue could only decide a student who had uploaded a card. A student
    who is `PENDING` with nothing uploaded (an import, a Django-admin edit, a
    deleted upload) — or one the reviewer simply knows — had no button anywhere.
    These tests pin the way out: verify, reject (reason mandatory) and revoke, all
    through the **same** account write the document review uses, so the student
    profile's mirror flag, the audit trail and the student's notification follow.

⚠️  `academic` is reached through `apps.get_model` — it and `customers` are
    independent siblings, and a test is part of the package, not an exception to it.
"""

import uuid

import pytest
from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountType, User, VerificationStatus
from conftest import PDF_BYTES
from core.models.audit import AuditAction, AuditLog
from core.testing import grant_all_domains
from customers.models import CustomerDocument, CustomerProfile, DocumentStatus, DocumentType

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


def make_user(email, account_type=AccountType.STUDENT, **extra) -> User:
    user = User.objects.create_user(
        email=email, password=PASSWORD, account_type=account_type, **extra
    )
    user.is_active = True
    user.save()
    return user


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def make_student_profile(user):
    university = apps.get_model("academic", "University").objects.create(
        code=f"u-{uuid.uuid4().hex[:8]}", name_ar="القاهرة", name_en="Cairo"
    )
    faculty = apps.get_model("academic", "Faculty").objects.create(
        university=university, code="pharm", name_ar="الصيدلة", name_en="Pharmacy"
    )
    return apps.get_model("academic", "StudentProfile").objects.create(
        user=user, university=university, faculty=faculty, academic_year=2
    )


def make_document(
    user, document_type=DocumentType.STUDENT_CARD, status=DocumentStatus.PENDING
) -> CustomerDocument:
    profile, _ = CustomerProfile.objects.get_or_create(user=user)
    return CustomerDocument.objects.create(
        customer=profile,
        document_type=document_type,
        status=status,
        file=SimpleUploadedFile("card.pdf", PDF_BYTES),
    )


def set_status(user, status):
    User.objects.filter(pk=user.pk).update(verification_status=status)


def status_of(user) -> str:
    return User.objects.get(pk=user.pk).verification_status


def mirror_of(user) -> bool:
    return apps.get_model("academic", "StudentProfile").objects.get(user=user).is_verified


@pytest.fixture
def reviewer(db):
    admin = make_user("reviewer@test.local", AccountType.ADMIN, first_name="مراجع")
    apps.get_model("administration", "AdminProfile").objects.create(user=admin)
    grant_all_domains(admin)
    return admin


@pytest.fixture
def admin_client(reviewer):
    return client_for(reviewer)


@pytest.fixture
def student(db):
    """⚠️  Waiting, with **nothing uploaded** — the case that had no button."""
    user = make_user("student@test.local", first_name="سلمى", last_name="أحمد")
    make_student_profile(user)
    set_status(user, VerificationStatus.PENDING)
    return user


def verify_url(user):
    return reverse("v1:customers:admin-student-verify", args=[user.pk])


def reject_url(user):
    return reverse("v1:customers:admin-student-reject", args=[user.pk])


# ═══════════════════════════════════════════════════════════
#  Who may reach it
# ═══════════════════════════════════════════════════════════


class TestPermissions:
    def _statuses(self, client, student):
        return {
            verify_url(student): client.post(verify_url(student)).status_code,
            reject_url(student): client.post(
                reject_url(student), {"reason": "سبب كافٍ"}, format="json"
            ).status_code,
        }

    def test_anonymous_gets_401(self, student):
        assert set(self._statuses(APIClient(), student).values()) == {401}

    def test_a_student_gets_403_and_nothing_changes(self, student):
        assert set(self._statuses(client_for(student), student).values()) == {403}
        assert status_of(student) == VerificationStatus.PENDING

    def test_a_staff_member_without_the_academic_permission_gets_403(self, student):
        staff = make_user("staff@test.local", AccountType.ADMIN)
        apps.get_model("administration", "AdminProfile").objects.create(user=staff)

        assert set(self._statuses(client_for(staff), student).values()) == {403}
        assert status_of(student) == VerificationStatus.PENDING

    def test_a_reviewer_gets_through(self, admin_client, student):
        assert admin_client.post(verify_url(student)).status_code == 200


# ═══════════════════════════════════════════════════════════
#  Verify
# ═══════════════════════════════════════════════════════════


class TestVerify:
    def test_a_student_with_no_document_is_verified_everywhere(self, admin_client, student):
        response = admin_client.post(verify_url(student))

        assert response.status_code == 200
        assert response.data == {"id": str(student.pk), "verification_status": "VERIFIED"}
        assert User.objects.get(pk=student.pk).is_verified is True
        # ⚠️  The profile flag is only a mirror — set by the receiver in `academic`
        assert mirror_of(student) is True

    @pytest.mark.parametrize(
        "before", [VerificationStatus.NOT_REQUIRED, VerificationStatus.REJECTED]
    )
    def test_a_student_who_never_asked_or_was_rejected_can_be_verified(
        self, admin_client, student, before
    ):
        set_status(student, before)

        assert admin_client.post(verify_url(student)).status_code == 200
        assert status_of(student) == VerificationStatus.VERIFIED

    def test_an_audit_row_records_who_and_the_change(self, admin_client, reviewer, student):
        admin_client.post(verify_url(student))

        row = AuditLog.objects.get(action=AuditAction.APPROVE)
        assert row.actor_id == reviewer.pk
        assert row.object_id == str(student.pk)
        assert row.changes["verification_status"] == {"old": "PENDING", "new": "VERIFIED"}
        assert row.changes["documents"] == []

    def test_a_verified_student_cannot_be_verified_again(self, admin_client, student):
        assert admin_client.post(verify_url(student)).status_code == 200

        again = admin_client.post(verify_url(student))

        assert again.status_code == 409
        # ⚠️  One decision, one audit row
        assert AuditLog.objects.filter(action=AuditAction.APPROVE).count() == 1

    def test_the_waiting_student_card_is_approved_with_the_student(
        self, admin_client, reviewer, student
    ):
        """
        ⚠️  No card is left `PENDING` under a decided account — it would stay in the
            queue and on the sidebar badge asking for a second answer.
        """
        card = make_document(student)

        admin_client.post(verify_url(student))

        card.refresh_from_db()
        assert card.status == DocumentStatus.APPROVED
        assert card.reviewed_by_id == reviewer.pk
        assert status_of(student) == VerificationStatus.VERIFIED
        row = AuditLog.objects.get(object_id=str(student.pk))
        assert row.changes["documents"] == [str(card.pk)]

    def test_other_document_types_are_left_alone(self, admin_client, student):
        national_id = make_document(student, DocumentType.NATIONAL_ID)

        admin_client.post(verify_url(student))

        national_id.refresh_from_db()
        assert national_id.status == DocumentStatus.PENDING

    def test_an_unknown_student_is_404(self, admin_client):
        url = reverse("v1:customers:admin-student-verify", args=[uuid.uuid4()])

        assert admin_client.post(url).status_code == 404


# ═══════════════════════════════════════════════════════════
#  Reject, and revoke
# ═══════════════════════════════════════════════════════════


class TestReject:
    def _reject(self, client, student, reason="لم تثبت صفة الطالب"):
        return client.post(reject_url(student), {"reason": reason}, format="json")

    def test_a_student_with_no_document_is_rejected_everywhere(self, admin_client, student):
        response = self._reject(admin_client, student)

        assert response.status_code == 200
        assert response.data["verification_status"] == "REJECTED"
        assert status_of(student) == VerificationStatus.REJECTED
        assert mirror_of(student) is False

    @pytest.mark.parametrize("payload", [{}, {"reason": ""}, {"reason": "  "}, {"reason": "ab"}])
    def test_a_reason_is_mandatory(self, admin_client, student, payload):
        response = admin_client.post(reject_url(student), payload, format="json")

        assert response.status_code == 400
        assert status_of(student) == VerificationStatus.PENDING
        assert not AuditLog.objects.filter(action=AuditAction.REJECT).exists()

    def test_an_audit_row_carries_the_reason(self, admin_client, reviewer, student):
        self._reject(admin_client, student, "الاسم لا يطابق الكارنيه")

        row = AuditLog.objects.get(action=AuditAction.REJECT)
        assert row.actor_id == reviewer.pk
        assert row.object_id == str(student.pk)
        assert row.changes["reason"] == "الاسم لا يطابق الكارنيه"
        assert row.changes["verification_status"] == {"old": "PENDING", "new": "REJECTED"}

    def test_the_waiting_student_card_is_rejected_with_the_reason(self, admin_client, student):
        card = make_document(student)

        self._reject(admin_client, student, "الصورة غير واضحة")

        card.refresh_from_db()
        assert card.status == DocumentStatus.REJECTED
        assert card.rejection_reason == "الصورة غير واضحة"
        assert status_of(student) == VerificationStatus.REJECTED

    def test_two_waiting_cards_both_end_rejected_and_the_account_too(self, admin_client, student):
        cards = [make_document(student), make_document(student)]

        self._reject(admin_client, student)

        for card in cards:
            card.refresh_from_db()
            assert card.status == DocumentStatus.REJECTED
        assert status_of(student) == VerificationStatus.REJECTED

    def test_a_verified_student_can_be_revoked(self, admin_client, student):
        assert admin_client.post(verify_url(student)).status_code == 200
        assert mirror_of(student) is True

        response = self._reject(admin_client, student, "تبيّن أن الكارنيه منتهٍ")

        assert response.status_code == 200
        assert status_of(student) == VerificationStatus.REJECTED
        assert mirror_of(student) is False

    def test_a_revocation_does_not_rewrite_the_approved_cards(self, admin_client, student):
        approved = make_document(student, status=DocumentStatus.APPROVED)
        set_status(student, VerificationStatus.VERIFIED)

        self._reject(admin_client, student)

        approved.refresh_from_db()
        assert approved.status == DocumentStatus.APPROVED
        assert status_of(student) == VerificationStatus.REJECTED

    def test_a_waiting_card_of_a_verified_student_is_rejected_and_the_account_revoked(
        self, admin_client, student
    ):
        """
        ⚠️  `review_document` alone would leave a verified student verified when
            their newer card is rejected; revoking must end rejected regardless.
        """
        set_status(student, VerificationStatus.VERIFIED)
        card = make_document(student)

        self._reject(admin_client, student)

        card.refresh_from_db()
        assert card.status == DocumentStatus.REJECTED
        assert status_of(student) == VerificationStatus.REJECTED

    def test_a_rejected_student_cannot_be_rejected_again(self, admin_client, student):
        assert self._reject(admin_client, student).status_code == 200

        again = self._reject(admin_client, student)

        assert again.status_code == 409
        assert AuditLog.objects.filter(action=AuditAction.REJECT).count() == 1

    def test_a_student_who_never_asked_has_nothing_to_reject(self, admin_client, student):
        set_status(student, VerificationStatus.NOT_REQUIRED)

        assert self._reject(admin_client, student).status_code == 409
        assert status_of(student) == VerificationStatus.NOT_REQUIRED


# ═══════════════════════════════════════════════════════════
#  Who can be decided
# ═══════════════════════════════════════════════════════════


class TestOnlyStudents:
    @pytest.mark.parametrize("account_type", [AccountType.DOCTOR, AccountType.PHARMACY])
    def test_a_non_student_account_is_refused_and_untouched(self, admin_client, account_type):
        other = make_user("other@test.local", account_type)
        set_status(other, VerificationStatus.PENDING)

        verify = admin_client.post(verify_url(other))
        reject = admin_client.post(reject_url(other), {"reason": "سبب كافٍ"}, format="json")

        assert verify.status_code == 409 and reject.status_code == 409
        assert status_of(other) == VerificationStatus.PENDING
        assert not AuditLog.objects.filter(object_id=str(other.pk)).exists()

    def test_another_student_is_untouched(self, admin_client, student):
        bystander = make_user("bystander@test.local")
        make_student_profile(bystander)
        set_status(bystander, VerificationStatus.PENDING)

        admin_client.post(verify_url(student))

        assert status_of(bystander) == VerificationStatus.PENDING
        assert mirror_of(bystander) is False


# ═══════════════════════════════════════════════════════════
#  The review window's documents
# ═══════════════════════════════════════════════════════════


class TestDocumentsOfOneAccount:
    def test_the_queue_can_be_narrowed_to_one_account(self, admin_client, student):
        mine = make_document(student)
        make_document(make_user("other-student@test.local"))

        response = admin_client.get(
            reverse("v1:customers:admin-documents"), {"user": str(student.pk)}
        )

        assert response.status_code == 200
        assert [row["id"] for row in response.data["results"]] == [str(mine.pk)]

    def test_a_malformed_account_is_a_400(self, admin_client):
        response = admin_client.get(reverse("v1:customers:admin-documents"), {"user": "abc"})

        assert response.status_code == 400
