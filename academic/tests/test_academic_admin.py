"""
الشجرة الأكاديمية والحزم من اللوحة.

⚠️  **الشجرة شرط لتسجيل أي طالب**: يختار جامعته وكليته قبل إنشاء
    الحساب. ومتجر بلا شاشة جامعات لا يستقبل طالبًا واحدًا من لوحته.

⚠️  والمحروس: سنة الحزمة داخل سنوات كليتها · الكلية ذات الطلاب
    لا تُحذف · بنود الحزمة مُصفّاة بحزمتها.

⚠️  و`catalog` يُوصَل إليه بـ `apps.get_model` لا بالاستيراد.

    هو و`academic` صنوان في نفس الطبقة، ولا يستورد أحدهما الآخر —
    يفرضه import-linter، والاختبار جزء من الحزمة لا استثناء منها.
"""

import pytest
from django.apps import apps
from django.urls import reverse
from rest_framework.test import APIClient

from academic.models import Department, Faculty, StudyBundle, University
from accounts.models import AccountType, User

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_user(
        email="acad-admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    admin.is_active = True
    admin.save()
    apps.get_model("administration", "AdminProfile").objects.create(user=admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture
def university(db):
    return University.objects.create(code="cu", name_ar="القاهرة", name_en="Cairo")


@pytest.fixture
def faculty(university):
    return Faculty.objects.create(
        university=university, code="pharm", name_ar="الصيدلة", name_en="Pharmacy", years_count=5
    )


# ═══════════════════════════════════════════════════════════
#  الشجرة
# ═══════════════════════════════════════════════════════════


class TestTree:
    def test_a_university_is_created(self, admin_client):
        response = admin_client.post(
            reverse("v1:academic:admin-universities"),
            {"code": "asu", "name_ar": "عين شمس", "name_en": "Ain Shams"},
            format="json",
        )

        assert response.status_code == 201
        assert University.objects.filter(code="asu").exists()

    def test_a_faculty_belongs_to_a_university(self, admin_client, university):
        response = admin_client.post(
            reverse("v1:academic:admin-faculties"),
            {
                "university": str(university.pk),
                "code": "med",
                "name_ar": "الطب",
                "name_en": "Medicine",
                "years_count": 6,
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["university_name"] == "القاهرة"

    def test_zero_years_is_refused(self, admin_client, university):
        """
        ⚠️  عدد السنوات يحكم قوائم الحزم — والصفر يجعل كل حزمة غير
            قابلة للإسناد.
        """
        response = admin_client.post(
            reverse("v1:academic:admin-faculties"),
            {
                "university": str(university.pk),
                "code": "x",
                "name_ar": "كلية",
                "name_en": "Faculty",
                "years_count": 0,
            },
            format="json",
        )

        assert response.status_code == 400
        assert "years_count" in response.data["fields"]

    def test_faculties_can_be_filtered_by_university(self, admin_client, university, faculty):
        other = University.objects.create(code="alx", name_ar="الإسكندرية", name_en="Alex")
        Faculty.objects.create(
            university=other, code="eng", name_ar="الهندسة", name_en="Eng", years_count=5
        )

        response = admin_client.get(
            reverse("v1:academic:admin-faculties"), {"university": str(university.pk)}
        )
        assert [row["code"] for row in response.data] == ["pharm"]

    def test_a_university_with_faculties_is_not_deleted(self, admin_client, university, faculty):
        response = admin_client.delete(
            reverse("v1:academic:admin-university-detail", args=[university.pk])
        )

        assert response.status_code == 409
        assert "1" in response.data["detail"]

    def test_a_faculty_with_departments_is_not_deleted(self, admin_client, faculty):
        Department.objects.create(faculty=faculty, code="clin", name_ar="إكلينيكي", name_en="Clin")

        response = admin_client.delete(
            reverse("v1:academic:admin-faculty-detail", args=[faculty.pk])
        )
        assert response.status_code == 409


# ═══════════════════════════════════════════════════════════
#  الحزم
# ═══════════════════════════════════════════════════════════


class TestBundles:
    def test_a_bundle_is_created(self, admin_client, faculty):
        response = admin_client.post(
            reverse("v1:academic:admin-bundles"),
            {
                "faculty": str(faculty.pk),
                "academic_year": 1,
                "kind": "REQUIRED",
                "name_ar": "حزمة السنة الأولى",
                "name_en": "Year one",
            },
            format="json",
        )

        assert response.status_code == 201, response.data
        assert StudyBundle.objects.filter(faculty=faculty).exists()

    def test_a_year_beyond_the_faculty_length_is_refused(self, admin_client, faculty):
        """
        ⚠️  **حزمة لا يراها أحد.**

            السنة السادسة في كلية بخمس سنوات لا يصلها طالب أبدًا،
            وتُنشأ صامتة ثم يُسأل «لماذا لا يراها أحد؟» بعد أسابيع.
        """
        response = admin_client.post(
            reverse("v1:academic:admin-bundles"),
            {
                "faculty": str(faculty.pk),
                "academic_year": 6,
                "kind": "REQUIRED",
                "name_ar": "حزمة",
                "name_en": "Bundle",
            },
            format="json",
        )

        assert response.status_code == 400
        assert "academic_year" in response.data["fields"]
        # الرسالة تذكر مدة الكلية — الأدمن يصحّح بلا بحث
        assert "5" in str(response.data["fields"]["academic_year"])

    def test_bundle_items_are_scoped_to_their_bundle(self, admin_client, faculty):
        """قائمة كل البنود بلا سياق بلا معنى — والتصفية إلزامية."""
        category = apps.get_model("catalog", "Category").objects.create(
            name_ar="فئة", name_en="Cat"
        )
        product = apps.get_model("catalog", "Product").objects.create(
            sku="BK-1", name_ar="كتاب", name_en="Book", category=category
        )

        first = StudyBundle.objects.create(
            faculty=faculty, academic_year=1, name_ar="أولى", name_en="One"
        )
        second = StudyBundle.objects.create(
            faculty=faculty, academic_year=2, name_ar="ثانية", name_en="Two"
        )

        admin_client.post(
            reverse("v1:academic:admin-bundle-items", args=[first.pk]),
            {"product": str(product.pk), "quantity": 1, "is_essential": True},
            format="json",
        )

        in_first = admin_client.get(reverse("v1:academic:admin-bundle-items", args=[first.pk]))
        in_second = admin_client.get(reverse("v1:academic:admin-bundle-items", args=[second.pk]))

        assert len(in_first.data) == 1
        assert len(in_second.data) == 0

    def test_item_count_is_exposed(self, admin_client, faculty):
        """حزمة بلا بنود تظهر للطالب فارغة — والعدد يكشفها قبل ذلك."""
        StudyBundle.objects.create(
            faculty=faculty, academic_year=1, name_ar="فارغة", name_en="Empty"
        )

        response = admin_client.get(reverse("v1:academic:admin-bundles"))
        assert response.data[0]["item_count"] == 0


# ═══════════════════════════════════════════════════════════
#  الصلاحية
# ═══════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "route",
    [
        "v1:academic:admin-universities",
        "v1:academic:admin-faculties",
        "v1:academic:admin-bundles",
    ],
)
def test_customers_cannot_edit_the_academic_tree(route):
    """
    ⚠️  من يضيف جامعة يضيف بابًا لتسجيل الطلاب — بنية لا بيانات.
    """
    customer = User.objects.create_user(email="c@test.local", password=PASSWORD)
    customer.is_active = True
    customer.save()

    client = APIClient()
    client.force_authenticate(user=customer)

    assert client.get(reverse(route)).status_code == 403
