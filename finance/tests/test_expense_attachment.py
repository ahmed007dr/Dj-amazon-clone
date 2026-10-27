"""
Expense attachments — a download that actually works, and only for those who may.

⚠️  The file lives under `private/expense-attachments/`, which the media route
    refuses on purpose. The serializer used to hand out the raw path, so the link
    on the screen was dead *and* told a reader where the file sits on disk. These
    tests guard both halves: the path is gone from the payload, and the
    authenticated endpoint is the one way to read the bytes.
"""

from datetime import date

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from administration.models import AdminProfile
from conftest import PDF_BYTES, pdf_upload
from core.models.audit import AuditAction, AuditLog
from finance.models import Expense, ExpenseCategory

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


def make_admin(email, *perms):
    user = User.objects.create_user(
        email=email, password=PASSWORD, account_type=AccountType.ADMIN
    )
    user.is_active = True
    user.save()
    AdminProfile.objects.create(user=user)
    for code in perms:
        app_label, codename = code.split(".")
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    return user


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def accountant():
    return make_admin("acct@test.local", "finance.add_expense")


@pytest.fixture
def category():
    return ExpenseCategory.objects.create(code="rent", name_ar="إيجار", name_en="Rent")


@pytest.fixture
def expense_with_file(accountant, category):
    response = client_for(accountant).post(
        reverse("v1:finance:expenses"),
        {
            "category": str(category.pk),
            "amount": "1500.00",
            "incurred_on": "2026-03-01",
            "reference": "INV 77/A",
            "attachment": pdf_upload("rent march.pdf"),
        },
        format="multipart",
    )
    assert response.status_code == 201, response.content
    return Expense.objects.get(pk=response.json()["id"])


def download_url(expense):
    return reverse("v1:finance:expense-attachment", args=[expense.pk])


class TestSerializer:
    def test_the_raw_file_path_is_not_exposed(self, accountant, expense_with_file):
        body = client_for(accountant).get(reverse("v1:finance:expenses")).json()["results"][0]

        assert "attachment" not in body
        assert "private/" not in str(body)
        assert body["has_attachment"] is True
        assert body["attachment_name"] == "expense-2026-03-01-INV-77-A.pdf"

    def test_detail_also_hides_the_path(self, accountant, expense_with_file):
        body = client_for(accountant).get(
            reverse("v1:finance:expense-detail", args=[expense_with_file.pk])
        ).json()

        assert "attachment" not in body
        assert body["has_attachment"] is True

    def test_expense_without_a_file(self, accountant, category):
        client_for(accountant).post(
            reverse("v1:finance:expenses"),
            {"category": str(category.pk), "amount": "10.00", "incurred_on": "2026-03-02"},
            format="json",
        )

        body = client_for(accountant).get(reverse("v1:finance:expenses")).json()["results"][0]
        assert body["has_attachment"] is False
        assert body["attachment_name"] is None

    def test_the_file_is_still_uploadable(self, expense_with_file):
        """`write_only`, not removed: the form still has to be able to attach one."""
        assert expense_with_file.attachment
        assert expense_with_file.attachment.name.startswith("private/expense-attachments/")


class TestDownload:
    def test_returns_the_bytes_as_a_download(self, accountant, expense_with_file):
        response = client_for(accountant).get(download_url(expense_with_file))

        assert response.status_code == 200
        assert b"".join(response.streaming_content) == PDF_BYTES
        assert response["Content-Type"] == "application/pdf"
        assert "attachment" in response["Content-Disposition"]
        assert "expense-2026-03-01-INV-77-A.pdf" in response["Content-Disposition"]

    def test_is_never_rendered_inline(self, accountant, expense_with_file):
        response = client_for(accountant).get(download_url(expense_with_file))

        assert response["X-Content-Type-Options"] == "nosniff"
        assert "no-store" in response["Cache-Control"]

    def test_the_superuser_may_download(self, expense_with_file):
        root = User.objects.create_superuser(email="root@test.local", password=PASSWORD)

        assert client_for(root).get(download_url(expense_with_file)).status_code == 200

    def test_requires_the_expenses_permission(self, expense_with_file):
        outsider = make_admin("nobody@test.local")

        assert client_for(outsider).get(download_url(expense_with_file)).status_code == 403

    def test_a_reports_only_permission_is_not_enough(self, expense_with_file):
        """Seeing profits is not reading invoices — same gate as the expense list itself."""
        viewer = make_admin("viewer@test.local", "finance.view_revenueentry")

        assert client_for(viewer).get(download_url(expense_with_file)).status_code == 403

    def test_anonymous_is_refused(self, expense_with_file):
        response = APIClient().get(download_url(expense_with_file))
        assert response.status_code in (401, 403)

    def test_the_private_media_route_still_refuses_it(self, expense_with_file):
        """The point of the endpoint: `/media/private/…` stays closed."""
        response = APIClient().get(f"/media/{expense_with_file.attachment.name}")
        assert response.status_code == 404

    def test_download_is_audited(self, accountant, expense_with_file):
        client_for(accountant).get(download_url(expense_with_file))

        entry = AuditLog.objects.get(action=AuditAction.EXPORT)
        assert entry.actor_id == accountant.pk
        assert entry.object_id == str(expense_with_file.pk)
        assert entry.changes == {"filename": "expense-2026-03-01-INV-77-A.pdf"}

    def test_expense_without_a_file_is_404(self, accountant, category):
        bare = Expense.objects.create(
            category=category,
            amount="5.00",
            incurred_on=date(2026, 3, 3),
            entered_by=accountant,
        )

        assert client_for(accountant).get(download_url(bare)).status_code == 404

    def test_file_missing_from_disk_is_404_not_500(self, accountant, expense_with_file):
        expense_with_file.attachment.delete(save=False)
        expense_with_file.attachment = "private/expense-attachments/zz/zz/gone.pdf"
        expense_with_file.save()

        assert client_for(accountant).get(download_url(expense_with_file)).status_code == 404
        assert not AuditLog.objects.filter(action=AuditAction.EXPORT).exists()

    def test_unknown_expense_is_404(self, accountant):
        import uuid

        response = client_for(accountant).get(
            reverse("v1:finance:expense-attachment", args=[uuid.uuid4()])
        )
        assert response.status_code == 404
