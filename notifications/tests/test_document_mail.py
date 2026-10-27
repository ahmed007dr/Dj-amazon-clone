"""
The student hears the outcome of a document review.

⚠️  An approved card is good news they would otherwise discover by chance, and a
    rejection with no reason sends them back to upload the same photo. The message
    carries the reason, goes out in the **recipient's** language, and is in the
    mandatory `ACCOUNT` category — muting marketing does not mute it.
"""

import pytest
from django.core import mail as django_mail
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import AccountType, User
from conftest import PDF_BYTES
from customers import services
from customers.models import CustomerDocument, CustomerProfile, DocumentType
from mailing import templates as mail_templates
from notifications.models import Notification, NotificationCategory, NotificationPriority

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_outbox():
    django_mail.outbox.clear()
    yield


@pytest.fixture
def reviewer(db):
    user = User.objects.create_user(
        email="reviewer@test.local", password="Str0ng-Pass!23", account_type=AccountType.ADMIN
    )
    user.is_active = True
    user.save()
    return user


def make_student(language="ar") -> User:
    user = User.objects.create_user(
        email="student@test.local",
        password="Str0ng-Pass!23",
        account_type=AccountType.STUDENT,
        first_name="سلمى",
        preferred_language=language,
    )
    user.is_active = True
    user.save()
    return user


def make_document(user, document_type=DocumentType.STUDENT_CARD) -> CustomerDocument:
    profile, _ = CustomerProfile.objects.get_or_create(user=user)
    return CustomerDocument.objects.create(
        customer=profile,
        document_type=document_type,
        file=SimpleUploadedFile("card.pdf", PDF_BYTES),
    )


class TestTemplates:
    @pytest.mark.parametrize(
        "template", [mail_templates.DOCUMENT_APPROVED, mail_templates.DOCUMENT_REJECTED]
    )
    def test_both_languages_are_filled_and_registered(self, template):
        assert template.key in mail_templates.TEMPLATES
        for text in (template.subject_ar, template.subject_en, template.body_ar, template.body_en):
            assert text.strip()

    def test_the_rejection_carries_the_reason_in_both_languages(self):
        template = mail_templates.DOCUMENT_REJECTED

        assert "{reason}" in template.body_ar and "{reason}" in template.body_en

    def test_nothing_is_left_unfilled(self):
        context = {"name": "سلمى", "document_type": "X", "reason": "R", "link": "http://x/y"}

        for template in (mail_templates.DOCUMENT_APPROVED, mail_templates.DOCUMENT_REJECTED):
            for language in ("ar", "en"):
                subject, body = template.render(language, context)
                assert "{" not in subject and "{" not in body


class TestApproved:
    def test_an_in_app_notification_and_an_email(
        self, reviewer, django_capture_on_commit_callbacks
    ):
        student = make_student()
        document = make_document(student)

        with django_capture_on_commit_callbacks(execute=True):
            services.review_document(document, approved=True, reviewer=reviewer)

        note = Notification.objects.get(user=student)
        assert note.category == NotificationCategory.ACCOUNT
        assert note.action_url == "/account/documents"
        assert note.reference_id == str(document.pk)
        assert len(django_mail.outbox) == 1
        assert django_mail.outbox[0].to == ["student@test.local"]
        assert "اعتماد" in django_mail.outbox[0].subject

    def test_the_email_follows_the_recipients_language(
        self, reviewer, django_capture_on_commit_callbacks
    ):
        student = make_student(language="en")
        document = make_document(student)

        with django_capture_on_commit_callbacks(execute=True):
            services.review_document(document, approved=True, reviewer=reviewer)

        assert django_mail.outbox[0].subject == "Your document was approved"
        assert "Student ID card" in django_mail.outbox[0].body
        assert Notification.objects.get(user=student).title == "Your document was approved"


class TestRejected:
    def test_the_reason_reaches_the_student(self, reviewer, django_capture_on_commit_callbacks):
        student = make_student()
        document = make_document(student)

        with django_capture_on_commit_callbacks(execute=True):
            services.review_document(
                document, approved=False, reviewer=reviewer, reason="الصورة غير واضحة"
            )

        note = Notification.objects.get(user=student)
        assert note.body == "الصورة غير واضحة"
        assert note.priority == NotificationPriority.HIGH
        assert "الصورة غير واضحة" in django_mail.outbox[0].body

    def test_the_english_email_names_the_document_in_english(
        self, reviewer, django_capture_on_commit_callbacks
    ):
        student = make_student(language="en")
        document = make_document(student)

        with django_capture_on_commit_callbacks(execute=True):
            services.review_document(
                document, approved=False, reviewer=reviewer, reason="Blurry photo"
            )

        body = django_mail.outbox[0].body
        assert "Blurry photo" in body and "Student ID card" in body

    def test_other_document_types_notify_too(self, reviewer, django_capture_on_commit_callbacks):
        student = make_student()
        document = make_document(student, DocumentType.NATIONAL_ID)

        with django_capture_on_commit_callbacks(execute=True):
            services.review_document(document, approved=True, reviewer=reviewer)

        assert Notification.objects.filter(user=student).count() == 1
        assert "بطاقة الرقم القومي" in django_mail.outbox[0].body


class TestResilience:
    def test_a_failing_notification_does_not_undo_the_decision(self, reviewer, monkeypatch):
        """
        ⚠️  An email that was not sent must not cancel a verification that happened.
        """
        from notifications import services as notification_services

        def broken(*args, **kwargs):
            raise RuntimeError("smtp down")

        monkeypatch.setattr(notification_services, "notify", broken)
        document = make_document(make_student())

        services.review_document(document, approved=True, reviewer=reviewer)

        document.refresh_from_db()
        assert document.status == "APPROVED"
