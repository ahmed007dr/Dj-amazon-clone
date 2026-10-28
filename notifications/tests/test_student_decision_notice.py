"""
The student hears that a reviewer decided them from their data.

⚠️  The document review already notifies through `document_reviewed`. A decision made
    from the student list with **no card to carry it** had no notice at all — the
    student found out by chance. It is in-app only (no mail template exists for a
    decision that is not about a document) and carries the reviewer's reason.
"""

import pytest

from accounts.models import AccountType, User, VerificationStatus
from customers import services
from customers.models import CustomerDocument, CustomerProfile, DocumentType
from notifications.models import Notification, NotificationPriority

pytestmark = pytest.mark.django_db


def make_user(email, account_type, **extra) -> User:
    user = User.objects.create_user(
        email=email, password="Str0ng-Pass!23", account_type=account_type, **extra
    )
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def reviewer(db):
    return make_user("reviewer@test.local", AccountType.ADMIN)


def make_student(language="ar") -> User:
    student = make_user(
        "student@test.local", AccountType.STUDENT, first_name="سلمى", preferred_language=language
    )
    User.objects.filter(pk=student.pk).update(verification_status=VerificationStatus.PENDING)
    student.refresh_from_db()
    return student


class TestStudentDecisionNotice:
    def test_a_verification_with_no_document_notifies_in_app(self, reviewer):
        student = make_student()

        services.decide_student_verification(student, verified=True, reviewer=reviewer)

        note = Notification.objects.get(user=student)
        assert note.reference_type == "student_verification"
        assert note.priority == NotificationPriority.NORMAL
        assert note.action_url == "/account/documents"

    def test_the_rejection_notice_carries_the_reason(self, reviewer):
        student = make_student()

        services.decide_student_verification(
            student, verified=False, reviewer=reviewer, reason="الاسم لا يطابق"
        )

        note = Notification.objects.get(user=student)
        assert note.body == "الاسم لا يطابق"
        assert note.priority == NotificationPriority.HIGH

    def test_the_notice_follows_the_students_language(self, reviewer):
        student = make_student(language="en")

        services.decide_student_verification(student, verified=True, reviewer=reviewer)

        assert (
            Notification.objects.get(user=student).title == "Your student verification was approved"
        )

    def test_a_decided_card_tells_the_student_once_not_twice(self, reviewer):
        """
        ⚠️  The card's own notice already carries the outcome and the reason.
        """
        student = make_student()
        profile = CustomerProfile.objects.create(user=student)
        CustomerDocument.objects.create(
            customer=profile, document_type=DocumentType.STUDENT_CARD, file="x.pdf"
        )

        services.decide_student_verification(student, verified=True, reviewer=reviewer)

        note = Notification.objects.get(user=student)
        assert note.reference_type == "customer_document"

    def test_a_failing_notification_does_not_undo_the_decision(self, reviewer, monkeypatch):
        from notifications import services as notification_services

        def broken(*args, **kwargs):
            raise RuntimeError("smtp down")

        monkeypatch.setattr(notification_services, "notify", broken)
        student = make_student()

        services.decide_student_verification(student, verified=True, reviewer=reviewer)

        student.refresh_from_db()
        assert student.verification_status == VerificationStatus.VERIFIED
