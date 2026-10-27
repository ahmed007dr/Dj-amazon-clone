"""
Reviewing verification documents — the admin side of student verification.

⚠️  Before this, a student could upload an ID card and nothing on earth could ever
    approve it: `review_document` existed and was never called, and every
    `customers` endpoint was owner-only. These tests pin the whole loop:

    upload → `PENDING` → reviewer opens the file → approve / reject → the account's
    verification, the student profile's mirror flag, the audit trail and the
    student's notification all move together.

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
from conftest import PDF_BYTES, PNG_BYTES
from core.models.audit import AuditAction, AuditLog
from core.testing import grant_all_domains
from customers import services
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


def make_student_profile(user, *, year=2, number="2024001", is_verified=False):
    university = apps.get_model("academic", "University").objects.create(
        code=f"u-{uuid.uuid4().hex[:8]}", name_ar="القاهرة", name_en="Cairo"
    )
    faculty = apps.get_model("academic", "Faculty").objects.create(
        university=university, code="pharm", name_ar="الصيدلة", name_en="Pharmacy"
    )
    return apps.get_model("academic", "StudentProfile").objects.create(
        user=user,
        university=university,
        faculty=faculty,
        academic_year=year,
        student_number=number,
        is_verified=is_verified,
    )


def make_document(
    user,
    document_type=DocumentType.STUDENT_CARD,
    status=DocumentStatus.PENDING,
    content=PDF_BYTES,
    name="card.pdf",
) -> CustomerDocument:
    profile, _ = CustomerProfile.objects.get_or_create(user=user)
    return CustomerDocument.objects.create(
        customer=profile,
        document_type=document_type,
        status=status,
        file=SimpleUploadedFile(name, content),
    )


def upload(client, document_type="STUDENT_CARD"):
    return client.post(
        reverse("v1:customers:documents"),
        {
            "document_type": document_type,
            "file": SimpleUploadedFile("card.pdf", PDF_BYTES, content_type="application/pdf"),
        },
        format="multipart",
    )


def status_of(user) -> str:
    return User.objects.get(pk=user.pk).verification_status


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
    user = make_user("student@test.local", first_name="سلمى", last_name="أحمد", phone="01001234567")
    make_student_profile(user)
    return user


# ═══════════════════════════════════════════════════════════
#  Uploading puts the student in the queue
# ═══════════════════════════════════════════════════════════


class TestPendingOnUpload:
    def test_uploading_a_student_card_makes_the_account_pending(self, student):
        assert status_of(student) == VerificationStatus.NOT_REQUIRED

        assert upload(client_for(student)).status_code == 201

        assert status_of(student) == VerificationStatus.PENDING

    def test_another_document_type_does_not(self, student):
        assert upload(client_for(student), "NATIONAL_ID").status_code == 201

        assert status_of(student) == VerificationStatus.NOT_REQUIRED

    def test_a_non_student_account_is_not_touched(self):
        doctor = make_user("doc@test.local", AccountType.DOCTOR)

        assert upload(client_for(doctor)).status_code == 201

        assert status_of(doctor) == VerificationStatus.NOT_REQUIRED

    def test_a_verified_student_keeps_their_access_when_renewing(self, student):
        """
        ⚠️  Dropping them to `PENDING` would take their student prices away for a
            routine renewal.
        """
        User.objects.filter(pk=student.pk).update(verification_status=VerificationStatus.VERIFIED)

        upload(client_for(student))

        assert status_of(student) == VerificationStatus.VERIFIED

    def test_a_rejected_student_goes_back_to_pending_on_reupload(self, student):
        User.objects.filter(pk=student.pk).update(verification_status=VerificationStatus.REJECTED)

        upload(client_for(student))

        assert status_of(student) == VerificationStatus.PENDING

    def test_withdrawing_the_only_pending_card_clears_the_wait(self, student):
        client = client_for(student)
        upload(client)
        document = CustomerDocument.objects.get(customer__user=student)

        assert (
            client.delete(reverse("v1:customers:document-delete", args=[document.pk])).status_code
            == 204
        )

        assert status_of(student) == VerificationStatus.NOT_REQUIRED

    def test_withdrawing_one_of_two_pending_cards_keeps_the_wait(self, student):
        client = client_for(student)
        upload(client)
        upload(client)
        first = CustomerDocument.objects.filter(customer__user=student).first()

        client.delete(reverse("v1:customers:document-delete", args=[first.pk]))

        assert status_of(student) == VerificationStatus.PENDING


# ═══════════════════════════════════════════════════════════
#  Who may reach it
# ═══════════════════════════════════════════════════════════


class TestPermissions:
    def _urls(self, document):
        return {
            "get": [
                reverse("v1:customers:admin-documents"),
                reverse("v1:customers:admin-document-counts"),
                reverse("v1:customers:admin-document-file", args=[document.pk]),
            ],
            "post": [
                reverse("v1:customers:admin-document-approve", args=[document.pk]),
                reverse("v1:customers:admin-document-reject", args=[document.pk]),
                reverse("v1:customers:admin-document-bulk-approve"),
            ],
        }

    def _statuses(self, client, document):
        urls = self._urls(document)
        got = {url: client.get(url).status_code for url in urls["get"]}
        got.update(
            {
                url: client.post(url, {"reason": "سبب", "ids": []}, format="json").status_code
                for url in urls["post"]
            }
        )
        return got

    def test_anonymous_gets_401(self, student):
        document = make_document(student)

        assert set(self._statuses(APIClient(), document).values()) == {401}

    def test_a_student_gets_403_everywhere(self, student):
        document = make_document(student)

        assert set(self._statuses(client_for(student), document).values()) == {403}

    def test_a_staff_member_without_the_academic_permission_gets_403(self, student):
        staff = make_user("staff@test.local", AccountType.ADMIN)
        apps.get_model("administration", "AdminProfile").objects.create(user=staff)
        document = make_document(student)

        assert set(self._statuses(client_for(staff), document).values()) == {403}
        document.refresh_from_db()
        assert document.status == DocumentStatus.PENDING

    def test_a_reviewer_gets_through(self, admin_client, student):
        document = make_document(student)

        statuses = self._statuses(admin_client, document)

        assert 403 not in statuses.values() and 401 not in statuses.values()

    def test_another_students_card_is_still_invisible_to_a_student(self, student):
        other = make_user("other@test.local")
        theirs = make_document(other)

        response = client_for(student).get(reverse("v1:customers:documents"))

        assert response.status_code == 200
        assert str(theirs.pk) not in {row["id"] for row in response.data}
        assert (
            client_for(student)
            .get(reverse("v1:customers:document-signed-url", args=[theirs.pk]))
            .status_code
            == 404
        )


# ═══════════════════════════════════════════════════════════
#  The queue
# ═══════════════════════════════════════════════════════════


class TestQueue:
    def _get(self, client, **params):
        response = client.get(reverse("v1:customers:admin-documents"), params)
        assert response.status_code == 200, response.content
        return response.data

    def test_a_row_says_who_and_where(self, admin_client, student):
        document = make_document(student)

        body = self._get(admin_client, status="PENDING")

        assert body["count"] == 1 and body["page"] == 1 and body["pages"] == 1
        row = body["results"][0]
        assert row["id"] == str(document.pk)
        assert row["document_type"] == "STUDENT_CARD"
        assert row["status"] == "PENDING"
        assert row["user"]["name"] == "سلمى أحمد"
        assert row["user"]["email"] == "student@test.local"
        assert row["user"]["phone"] == "01001234567"
        assert row["student"]["university_name_en"] == "Cairo"
        assert row["student"]["faculty_name_ar"] == "الصيدلة"
        assert row["student"]["academic_year"] == 2
        assert row["student"]["student_number"] == "2024001"

    def test_the_file_is_never_in_the_list(self, admin_client, student):
        make_document(student)

        row = self._get(admin_client)["results"][0]

        assert "file" not in row and "url" not in row

    def test_a_document_without_a_student_profile_has_a_null_student(self, admin_client):
        make_document(make_user("doc@test.local", AccountType.DOCTOR), DocumentType.MEDICAL_LICENSE)

        row = self._get(admin_client)["results"][0]

        assert row["student"] is None
        assert row["user"]["account_type"] == "DOCTOR"

    def test_filter_by_status(self, admin_client, student):
        pending = make_document(student)
        make_document(student, status=DocumentStatus.APPROVED)
        make_document(student, status=DocumentStatus.REJECTED)

        got = self._get(admin_client, status="PENDING")

        assert [row["id"] for row in got["results"]] == [str(pending.pk)]

    def test_filter_by_document_type(self, admin_client, student):
        card = make_document(student)
        make_document(student, DocumentType.NATIONAL_ID)

        got = self._get(admin_client, document_type="STUDENT_CARD")

        assert [row["id"] for row in got["results"]] == [str(card.pk)]

    def test_search_by_email_name_phone_and_student_number(self, admin_client, student):
        make_document(student)
        other = make_user("zed@test.local", first_name="زياد")
        make_student_profile(other, number="999")
        make_document(other)

        assert self._get(admin_client, search="student@test")["count"] == 1
        assert self._get(admin_client, search="سلمى")["count"] == 1
        assert self._get(admin_client, search="0100123")["count"] == 1
        assert self._get(admin_client, search="999")["count"] == 1
        assert self._get(admin_client, search="nobody")["count"] == 0

    def test_pending_is_oldest_first_and_history_newest_first(self, admin_client):
        first = make_document(make_user("a@test.local"))
        second = make_document(make_user("b@test.local"))

        pending = [row["id"] for row in self._get(admin_client, status="PENDING")["results"]]
        everything = [row["id"] for row in self._get(admin_client)["results"]]

        assert pending == [str(first.pk), str(second.pk)]
        assert everything == [str(second.pk), str(first.pk)]

    def test_paginated_with_a_total(self, admin_client):
        for n in range(5):
            make_document(make_user(f"p{n}@test.local"))

        body = self._get(admin_client, limit=2, page=2)

        assert body["count"] == 5 and body["pages"] == 3 and body["page"] == 2
        assert len(body["results"]) == 2

    @pytest.mark.parametrize("params", [{"status": "BOGUS"}, {"document_type": "NOPE"}])
    def test_a_bad_filter_is_a_400(self, admin_client, params):
        response = admin_client.get(reverse("v1:customers:admin-documents"), params)

        assert response.status_code == 400

    def test_counts_per_status_ignore_the_status_filter(self, admin_client, student):
        make_document(student)
        make_document(student)
        make_document(student, status=DocumentStatus.APPROVED)

        response = admin_client.get(
            reverse("v1:customers:admin-document-counts"), {"status": "APPROVED"}
        )

        assert response.status_code == 200
        assert response.data == {"PENDING": 2, "APPROVED": 1, "REJECTED": 0}

    def test_counts_respect_the_document_type(self, admin_client, student):
        make_document(student)
        make_document(student, DocumentType.NATIONAL_ID)

        response = admin_client.get(
            reverse("v1:customers:admin-document-counts"), {"document_type": "NATIONAL_ID"}
        )

        assert response.data["PENDING"] == 1

    def test_the_query_count_does_not_grow_with_the_queue(self, admin_client):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def queries():
            with CaptureQueriesContext(connection) as ctx:
                assert admin_client.get(reverse("v1:customers:admin-documents")).status_code == 200
            return len(ctx)

        for n in range(2):
            user = make_user(f"q{n}@test.local")
            make_student_profile(user)
            make_document(user)
        # ⚠️  The first request warms the reviewer's cached permission lookups
        queries()
        small = queries()

        for n in range(2, 9):
            user = make_user(f"q{n}@test.local")
            make_student_profile(user)
            make_document(user)

        assert queries() == small


# ═══════════════════════════════════════════════════════════
#  The file
# ═══════════════════════════════════════════════════════════


class TestFile:
    def _url(self, document):
        return reverse("v1:customers:admin-document-file", args=[document.pk])

    def test_inline_by_default_with_the_real_type(self, admin_client, student):
        document = make_document(student)

        response = admin_client.get(self._url(document))

        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert response["Content-Disposition"].startswith("inline")
        assert b"".join(response.streaming_content) == PDF_BYTES

    def test_attachment_on_request(self, admin_client, student):
        document = make_document(student)

        response = admin_client.get(self._url(document), {"download": "1"})

        assert response["Content-Disposition"].startswith("attachment")
        assert ".pdf" in response["Content-Disposition"]

    def test_the_type_comes_from_the_bytes_not_the_name(self, admin_client, student):
        """A PNG named `.pdf` is still served as a PNG."""
        document = make_document(student, content=PNG_BYTES, name="lying.pdf")

        response = admin_client.get(self._url(document))

        assert response["Content-Type"] == "image/png"
        assert ".png" in response["Content-Disposition"]

    def test_never_cached(self, admin_client, student):
        response = admin_client.get(self._url(make_document(student)))

        assert "no-store" in response["Cache-Control"]
        assert response["X-Content-Type-Options"] == "nosniff"

    def test_every_opening_is_audited(self, admin_client, reviewer, student):
        document = make_document(student)

        admin_client.get(self._url(document))
        admin_client.get(self._url(document), {"download": "1"})

        rows = AuditLog.objects.filter(action=AuditAction.EXPORT, object_id=str(document.pk))
        assert rows.count() == 2
        assert all(row.actor_id == reviewer.pk for row in rows)
        assert {row.changes["disposition"] for row in rows} == {"inline", "attachment"}

    def test_an_unknown_document_is_404(self, admin_client):
        response = admin_client.get(
            reverse(
                "v1:customers:admin-document-file", args=["00000000-0000-0000-0000-000000000000"]
            )
        )

        assert response.status_code == 404

    def test_a_missing_file_on_disk_is_404_not_500(self, admin_client, student):
        document = make_document(student)
        document.file.storage.delete(document.file.name)

        assert admin_client.get(self._url(document)).status_code == 404


# ═══════════════════════════════════════════════════════════
#  Approving
# ═══════════════════════════════════════════════════════════


class TestApprove:
    def _approve(self, client, document):
        return client.post(reverse("v1:customers:admin-document-approve", args=[document.pk]))

    def test_approving_a_student_card_verifies_the_student_everywhere(
        self, admin_client, reviewer, student
    ):
        document = make_document(student)
        User.objects.filter(pk=student.pk).update(verification_status=VerificationStatus.PENDING)

        response = self._approve(admin_client, document)

        assert response.status_code == 200
        assert response.data["status"] == "APPROVED"
        document.refresh_from_db()
        assert document.status == DocumentStatus.APPROVED
        assert document.reviewed_by_id == reviewer.pk
        assert document.reviewed_at is not None
        assert document.rejection_reason == ""

        user = User.objects.get(pk=student.pk)
        assert user.verification_status == VerificationStatus.VERIFIED
        assert user.is_verified is True
        # ⚠️  The profile flag is only a mirror — set by the receiver in `academic`
        assert apps.get_model("academic", "StudentProfile").objects.get(user=student).is_verified

    def test_an_audit_row_is_written_with_the_account_change(self, admin_client, reviewer, student):
        document = make_document(student)

        self._approve(admin_client, document)

        row = AuditLog.objects.get(action=AuditAction.APPROVE)
        assert row.actor_id == reviewer.pk
        assert row.object_id == str(document.pk)
        assert row.changes["status"] == {"old": "PENDING", "new": "APPROVED"}
        assert row.changes["verification_status"]["new"] == "VERIFIED"

    def test_a_decided_document_cannot_be_decided_twice(self, admin_client, student):
        document = make_document(student)
        assert self._approve(admin_client, document).status_code == 200

        again = self._approve(admin_client, document)

        assert again.status_code == 409
        assert AuditLog.objects.filter(action=AuditAction.APPROVE).count() == 1

    def test_other_document_types_are_approved_but_do_not_verify_the_account(
        self, admin_client, student
    ):
        document = make_document(student, DocumentType.NATIONAL_ID)

        self._approve(admin_client, document)

        document.refresh_from_db()
        assert document.status == DocumentStatus.APPROVED
        assert status_of(student) == VerificationStatus.NOT_REQUIRED
        assert (
            not apps.get_model("academic", "StudentProfile").objects.get(user=student).is_verified
        )

    def test_a_student_card_on_a_non_student_account_does_not_verify_it(self, admin_client):
        """
        ⚠️  `User.is_verified` is read by access policies far beyond student prices.
        """
        doctor = make_user("doc@test.local", AccountType.DOCTOR)
        document = make_document(doctor)

        self._approve(admin_client, document)

        document.refresh_from_db()
        assert document.status == DocumentStatus.APPROVED
        assert status_of(doctor) == VerificationStatus.NOT_REQUIRED

    def test_an_unknown_document_is_404(self, admin_client):
        response = admin_client.post(
            reverse(
                "v1:customers:admin-document-approve",
                args=["00000000-0000-0000-0000-000000000000"],
            )
        )

        assert response.status_code == 404


class TestBulkApprove:
    URL = "v1:customers:admin-document-bulk-approve"

    def test_approves_all_pending_rows(self, admin_client, reviewer):
        users = [make_user(f"b{n}@test.local") for n in range(3)]
        documents = [make_document(user) for user in users]

        response = admin_client.post(
            reverse(self.URL), {"ids": [str(d.pk) for d in documents]}, format="json"
        )

        assert response.status_code == 200
        assert set(response.data["approved"]) == {str(d.pk) for d in documents}
        assert response.data["skipped"] == []
        assert all(status_of(user) == VerificationStatus.VERIFIED for user in users)
        assert AuditLog.objects.filter(action=AuditAction.APPROVE, actor=reviewer).count() == 3

    def test_one_bad_row_does_not_fail_the_batch(self, admin_client, student):
        fresh = make_document(student)
        decided = make_document(student, status=DocumentStatus.APPROVED)
        ghost = "00000000-0000-0000-0000-000000000000"

        response = admin_client.post(
            reverse(self.URL),
            {"ids": [str(fresh.pk), str(decided.pk), ghost, str(fresh.pk)]},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["approved"] == [str(fresh.pk)]
        skipped = {row["id"]: row["code"] for row in response.data["skipped"]}
        assert skipped == {str(decided.pk): "CONFLICT", ghost: "NOT_FOUND"}
        assert AuditLog.objects.filter(action=AuditAction.APPROVE).count() == 1

    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"ids": []},
            {"ids": ["nope"]},
            {"ids": ["0" * 8 + "-0000-0000-0000-" + "0" * 12] * 101},
        ],
    )
    def test_a_bad_payload_is_a_400(self, admin_client, payload):
        assert admin_client.post(reverse(self.URL), payload, format="json").status_code == 400


# ═══════════════════════════════════════════════════════════
#  Rejecting
# ═══════════════════════════════════════════════════════════


class TestReject:
    def _reject(self, client, document, reason="الصورة غير واضحة"):
        payload = {} if reason is None else {"reason": reason}
        return client.post(
            reverse("v1:customers:admin-document-reject", args=[document.pk]),
            payload,
            format="json",
        )

    @pytest.mark.parametrize("reason", [None, "", "  ", "ab"])
    def test_a_reason_of_at_least_three_characters_is_mandatory(
        self, admin_client, student, reason
    ):
        document = make_document(student)

        response = self._reject(admin_client, document, reason)

        assert response.status_code == 400
        assert "reason" in response.data["fields"]
        document.refresh_from_db()
        assert document.status == DocumentStatus.PENDING

    def test_rejecting_keeps_the_reason_and_marks_the_account_rejected(
        self, admin_client, reviewer, student
    ):
        document = make_document(student)
        User.objects.filter(pk=student.pk).update(verification_status=VerificationStatus.PENDING)

        response = self._reject(admin_client, document, "الصورة غير واضحة")

        assert response.status_code == 200
        document.refresh_from_db()
        assert document.status == DocumentStatus.REJECTED
        assert document.rejection_reason == "الصورة غير واضحة"
        assert document.reviewed_by_id == reviewer.pk
        assert status_of(student) == VerificationStatus.REJECTED
        assert (
            not apps.get_model("academic", "StudentProfile").objects.get(user=student).is_verified
        )

    def test_the_student_can_read_the_reason_on_their_own_documents(self, admin_client, student):
        document = make_document(student)
        self._reject(admin_client, document, "اقتصّ الكارنيه من الأطراف")

        rows = client_for(student).get(reverse("v1:customers:documents")).data

        assert rows[0]["status"] == "REJECTED"
        assert rows[0]["rejection_reason"] == "اقتصّ الكارنيه من الأطراف"

    def test_an_audit_row_carries_the_reason(self, admin_client, reviewer, student):
        document = make_document(student)

        self._reject(admin_client, document, "بيانات غير مطابقة")

        row = AuditLog.objects.get(action=AuditAction.REJECT)
        assert row.actor_id == reviewer.pk
        assert row.changes["reason"] == "بيانات غير مطابقة"
        assert row.changes["status"] == {"old": "PENDING", "new": "REJECTED"}

    def test_another_card_still_waiting_keeps_the_account_pending(self, admin_client, student):
        first = make_document(student)
        make_document(student)
        User.objects.filter(pk=student.pk).update(verification_status=VerificationStatus.PENDING)

        self._reject(admin_client, first)

        assert status_of(student) == VerificationStatus.PENDING

    def test_a_verified_student_stays_verified_when_a_newer_card_is_rejected(
        self, admin_client, student
    ):
        """
        ⚠️  An approved card already stands behind their verification — a bad
            renewal photo must not undo it.
        """
        make_document(student, status=DocumentStatus.APPROVED)
        User.objects.filter(pk=student.pk).update(verification_status=VerificationStatus.VERIFIED)
        renewal = make_document(student)

        self._reject(admin_client, renewal)

        assert status_of(student) == VerificationStatus.VERIFIED

    def test_a_decided_document_cannot_be_rejected(self, admin_client, student):
        document = make_document(student, status=DocumentStatus.APPROVED)

        assert self._reject(admin_client, document).status_code == 409


class TestReviewDocumentService:
    def test_the_service_is_atomic_when_the_listener_side_fails(self, reviewer, student):
        """A failure after the writes rolls the writes back — no half-applied decision."""
        from customers import events

        document = make_document(student)

        def boom(sender, **kwargs):
            raise RuntimeError("downstream failure")

        events.document_reviewed.connect(boom, weak=False, dispatch_uid="boom")
        try:
            with pytest.raises(RuntimeError):
                services.review_document(document, approved=True, reviewer=reviewer)
        finally:
            events.document_reviewed.disconnect(dispatch_uid="boom")

        document.refresh_from_db()
        assert document.status == DocumentStatus.PENDING
        assert status_of(student) == VerificationStatus.NOT_REQUIRED
        assert not AuditLog.objects.filter(action=AuditAction.APPROVE).exists()
