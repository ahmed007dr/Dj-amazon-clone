"""
اختبارات ملكية موارد العملاء.

⚠️  هذه الاختبارات تحرس ضد الثغرة الأشهر في الكود القديم:
    `queryset = Model.objects.all()` بلا فلترة، والهوية مأخوذة
    من الـ URL لا من التوكن.

    كل اختبار «لا يرى/لا يعدّل مورد غيره» هنا يمثّل ثغرة كانت
    قائمة فعلًا في `orders/api.py`.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from conftest import PDF_BYTES
from customers.models import CustomerAddress, CustomerProfile

PASSWORD = "Str0ng-Test-Pass!23"


def make_user(email: str) -> User:
    user = User.objects.create_user(email=email, password=PASSWORD)
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def alice(db):
    return make_user("alice@test.local")


@pytest.fixture
def bob(db):
    return make_user("bob@test.local")


@pytest.fixture
def alice_client(alice):
    client = APIClient()
    client.force_authenticate(user=alice)
    return client


def make_address(user, **kwargs) -> CustomerAddress:
    profile, _ = CustomerProfile.objects.get_or_create(user=user)
    defaults = {
        "recipient_name": "مستلم",
        "phone": "+201001234567",
        "governorate": "القاهرة",
        "city": "مدينة نصر",
        "street": "شارع ١",
    }
    return CustomerAddress.objects.create(customer=profile, **{**defaults, **kwargs})


@pytest.mark.django_db
class TestProfileIsolation:
    def test_profile_created_on_first_access(self, alice_client, alice):
        assert not CustomerProfile.objects.filter(user=alice).exists()

        response = alice_client.get(reverse("v1:customers:me"))

        assert response.status_code == 200
        assert response.data["customer_number"].startswith("CUS-")
        assert CustomerProfile.objects.filter(user=alice).exists()

    def test_internal_notes_never_exposed(self, alice_client, alice):
        profile, _ = CustomerProfile.objects.get_or_create(user=alice)
        profile.notes = "عميل متأخر في السداد"
        profile.save()

        response = alice_client.get(reverse("v1:customers:me"))
        assert "notes" not in response.data

    def test_segment_is_read_only(self, alice_client, alice):
        """التصنيف التجاري يحدده النظام لا العميل."""
        alice_client.patch(reverse("v1:customers:me"), {"segment": "VIP"}, format="json")
        profile = CustomerProfile.objects.get(user=alice)
        assert profile.segment == "NEW"


@pytest.mark.django_db
class TestAddressOwnership:
    def test_list_excludes_other_users_addresses(self, alice_client, alice, bob):
        make_address(alice, label="بيتي")
        make_address(bob, label="بيت بوب")

        response = alice_client.get(reverse("v1:customers:addresses"))

        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]["label"] == "بيتي"

    def test_cannot_read_another_users_address(self, alice_client, bob):
        """⚠️  404 لا 403 — الفرق بينهما أداة تعداد."""
        bob_address = make_address(bob)

        response = alice_client.get(reverse("v1:customers:address-detail", args=[bob_address.pk]))
        assert response.status_code == 404

    def test_cannot_update_another_users_address(self, alice_client, bob):
        bob_address = make_address(bob, recipient_name="بوب")

        response = alice_client.patch(
            reverse("v1:customers:address-detail", args=[bob_address.pk]),
            {"recipient_name": "مخترق"},
            format="json",
        )

        assert response.status_code == 404
        bob_address.refresh_from_db()
        assert bob_address.recipient_name == "بوب"

    def test_cannot_delete_another_users_address(self, alice_client, bob):
        bob_address = make_address(bob)

        response = alice_client.delete(
            reverse("v1:customers:address-detail", args=[bob_address.pk])
        )

        assert response.status_code == 404
        assert CustomerAddress.objects.filter(pk=bob_address.pk).exists()

    def test_cannot_set_another_users_address_as_default(self, alice_client, bob):
        bob_address = make_address(bob)

        response = alice_client.post(
            reverse("v1:customers:address-set-default", args=[bob_address.pk])
        )

        assert response.status_code == 404
        bob_address.refresh_from_db()
        assert not bob_address.is_default


@pytest.mark.django_db
class TestDefaultAddress:
    def test_first_address_becomes_default(self, alice_client, alice):
        response = alice_client.post(
            reverse("v1:customers:addresses"),
            {
                "recipient_name": "أحمد",
                "phone": "+201001234567",
                "governorate": "القاهرة",
                "city": "مدينة نصر",
                "street": "شارع ١",
            },
            format="json",
        )
        assert response.status_code == 201
        assert response.data["is_default"] is True

    def test_setting_default_clears_previous(self, alice_client, alice):
        first = make_address(alice, label="أول", is_default=True)
        second = make_address(alice, label="ثانٍ")

        alice_client.post(reverse("v1:customers:address-set-default", args=[second.pk]))

        first.refresh_from_db()
        second.refresh_from_db()
        assert not first.is_default
        assert second.is_default

    def test_only_one_default_enforced_by_database(self, alice):
        """
        القيد في قاعدة البيانات لا في الكود — منطق التطبيق قد
        يُتجاوز، والقيد لا يُتجاوز.
        """
        from django.db.utils import IntegrityError

        make_address(alice, is_default=True)
        with pytest.raises(IntegrityError):
            make_address(alice, is_default=True)


@pytest.mark.django_db
class TestDocumentSecurity:
    def _upload(self, client, name="license.pdf"):
        from django.core.files.uploadedfile import SimpleUploadedFile

        return client.post(
            reverse("v1:customers:documents"),
            {
                "document_type": "MEDICAL_LICENSE",
                "file": SimpleUploadedFile(name, PDF_BYTES, content_type="application/pdf"),
            },
            format="multipart",
        )

    def test_file_path_is_never_returned(self, alice_client):
        """
        ⚠️  المسار المباشر يُخمَّن ويُشارك بلا فحص صلاحية.
            التقديم عبر رابط موقّع بصلاحية زمنية حصرًا.
        """
        response = self._upload(alice_client)

        assert response.status_code == 201
        assert "file" not in response.data
        assert "signed-url" in response.data["signed_url_endpoint"]

    def test_signed_url_grants_access_to_owner(self, alice_client, alice):
        from customers.models import CustomerDocument

        self._upload(alice_client)
        document = CustomerDocument.objects.get(customer__user=alice)

        issued = alice_client.get(reverse("v1:customers:document-signed-url", args=[document.pk]))
        assert issued.status_code == 200
        assert issued.data["expires_in"] == 300

        download = alice_client.get(issued.data["url"])
        assert download.status_code == 200

    def test_signed_url_does_not_work_for_another_user(self, alice_client, alice, bob):
        """
        ⚠️  التوقيع يحمل معرّف المستخدم — مشاركة الرابط لا تمنح الوصول.
        """
        from customers.models import CustomerDocument

        self._upload(alice_client)
        document = CustomerDocument.objects.get(customer__user=alice)

        issued = alice_client.get(reverse("v1:customers:document-signed-url", args=[document.pk]))
        signed_url = issued.data["url"]

        bob_client = APIClient()
        bob_client.force_authenticate(user=bob)
        assert bob_client.get(signed_url).status_code == 404

    def test_signed_url_expires(self, alice_client, alice):
        from core import files
        from customers.models import CustomerDocument

        self._upload(alice_client)
        document = CustomerDocument.objects.get(customer__user=alice)

        signature = files.sign_file_access("customer-document", document.pk, alice.pk)

        # محاكاة انقضاء المدة
        original_ttl = files.SIGNED_URL_TTL
        files.SIGNED_URL_TTL = -1
        try:
            assert files.verify_file_access(signature, "customer-document", alice.pk) is None
        finally:
            files.SIGNED_URL_TTL = original_ttl

    def test_tampered_signature_is_rejected(self, alice_client, alice):
        response = alice_client.get(
            reverse("v1:customers:document-download", args=["forged-signature-value"])
        )
        assert response.status_code == 404

    def test_oversized_upload_is_rejected(self, alice_client):
        from django.core.files.uploadedfile import SimpleUploadedFile

        response = alice_client.post(
            reverse("v1:customers:documents"),
            {
                "document_type": "MEDICAL_LICENSE",
                "file": SimpleUploadedFile(
                    "huge.pdf",
                    PDF_BYTES + b"x" * (11 * 1024 * 1024),
                    content_type="application/pdf",
                ),
            },
            format="multipart",
        )
        assert response.status_code == 400
        assert "file" in response.data["fields"]

    def test_disallowed_file_type_is_rejected(self, alice_client):
        from django.core.files.uploadedfile import SimpleUploadedFile

        response = alice_client.post(
            reverse("v1:customers:documents"),
            {
                "document_type": "MEDICAL_LICENSE",
                "file": SimpleUploadedFile(
                    "script.exe", b"MZ", content_type="application/x-msdownload"
                ),
            },
            format="multipart",
        )
        assert response.status_code == 400

    def test_stored_filename_is_randomised(self, alice_client, alice):
        from customers.models import CustomerDocument

        self._upload(alice_client, name="my-license.pdf")
        document = CustomerDocument.objects.get(customer__user=alice)

        assert "my-license" not in document.file.name
        assert document.file.name.startswith("private/customer-documents/")

    def test_cannot_request_signed_url_for_another_users_document(self, alice_client, bob):
        from django.core.files.uploadedfile import SimpleUploadedFile

        from customers.models import CustomerDocument

        profile, _ = CustomerProfile.objects.get_or_create(user=bob)
        document = CustomerDocument.objects.create(
            customer=profile,
            document_type="MEDICAL_LICENSE",
            file=SimpleUploadedFile("secret.pdf", PDF_BYTES, content_type="application/pdf"),
        )

        response = alice_client.get(reverse("v1:customers:document-signed-url", args=[document.pk]))
        assert response.status_code == 404

    def test_approved_document_cannot_be_deleted(self, alice_client, alice):
        from customers.models import CustomerDocument, DocumentStatus

        self._upload(alice_client)
        document = CustomerDocument.objects.get(customer__user=alice)
        document.status = DocumentStatus.APPROVED
        document.save()

        response = alice_client.delete(reverse("v1:customers:document-delete", args=[document.pk]))

        assert response.status_code == 409
        assert CustomerDocument.objects.filter(pk=document.pk).exists()


@pytest.mark.django_db
class TestAnonymousAccess:
    def test_all_customer_endpoints_require_authentication(self, db):
        client = APIClient()
        for url in (
            reverse("v1:customers:me"),
            reverse("v1:customers:addresses"),
            reverse("v1:customers:documents"),
        ):
            assert client.get(url).status_code == 401, url
