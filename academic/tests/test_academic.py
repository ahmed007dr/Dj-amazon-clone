"""
Academic domain tests.
"""

from decimal import Decimal

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError

from academic import services
from academic.models import (
    BundleItem,
    BundleKind,
    Department,
    Faculty,
    StudyBundle,
    University,
)
from accounts.models import AccountType, User
from core.errors import BusinessError

PASSWORD = "Str0ng-Test-Pass!23"


# ⚠️  Lazy string references.
#
#     `academic` and `catalog` are **independent** siblings on the same layer —
#     neither imports the other in any direction. And `apps.get_model` is a
#     registry lookup, so it creates no dependency for import-linter to catch.


def product_model():
    return apps.get_model("catalog", "Product")


def category_model():
    return apps.get_model("catalog", "Category")


@pytest.fixture
def university(db):
    return University.objects.create(code="cu", name_ar="القاهرة", name_en="Cairo")


@pytest.fixture
def pharmacy(university):
    return Faculty.objects.create(
        university=university,
        code="pharm",
        name_ar="الصيدلة",
        name_en="Pharmacy",
        years_count=5,
    )


@pytest.fixture
def medicine(university):
    return Faculty.objects.create(
        university=university,
        code="med",
        name_ar="الطب",
        name_en="Medicine",
        years_count=6,
    )


@pytest.fixture
def student_user(db):
    user = User.objects.create_user(
        email="student@test.local", password=PASSWORD, account_type=AccountType.STUDENT
    )
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def student(student_user, university, pharmacy):
    return services.create_student_profile(
        student_user, university=university, faculty=pharmacy, academic_year=2
    )


@pytest.fixture
def products(db):
    category = category_model().objects.create(name_ar="فئة", name_en="Category")
    return [
        product_model().objects.create(
            sku=f"B-{i}",
            name_ar=f"صنف {i}",
            name_en=f"Item {i}",
            category=category,
            base_price=Decimal("50.00"),
        )
        for i in range(3)
    ]


# ═══════════════════════════════════════════════════════════
#  Academic hierarchy consistency
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestHierarchyConsistency:
    def test_faculty_must_belong_to_the_chosen_university(self, student_user, university, db):
        """
        ⚠️  A faculty not belonging to the chosen university gives a student bundles that are not
            theirs.
        """
        other = University.objects.create(code="asu", name_ar="عين شمس", name_en="ASU")
        foreign = Faculty.objects.create(
            university=other, code="pharm", name_ar="صيدلة", name_en="Pharmacy"
        )

        with pytest.raises(ValidationError) as exc:
            services.create_student_profile(
                student_user, university=university, faculty=foreign, academic_year=1
            )
        assert "faculty" in exc.value.message_dict

    def test_department_must_belong_to_the_chosen_faculty(
        self, student_user, university, pharmacy, medicine
    ):
        foreign_dept = Department.objects.create(
            faculty=medicine, code="surgery", name_ar="جراحة", name_en="Surgery"
        )

        with pytest.raises(ValidationError) as exc:
            services.create_student_profile(
                student_user,
                university=university,
                faculty=pharmacy,
                department=foreign_dept,
                academic_year=1,
            )
        assert "department" in exc.value.message_dict

    def test_year_cannot_exceed_faculty_duration(self, student_user, university, pharmacy):
        """A five-year faculty does not accept a seventh-year student."""
        with pytest.raises(ValidationError) as exc:
            services.create_student_profile(
                student_user, university=university, faculty=pharmacy, academic_year=7
            )
        assert "academic_year" in exc.value.message_dict

    def test_department_is_optional(self, student_user, university, pharmacy):
        """Many faculties have no departments in their early years."""
        profile = services.create_student_profile(
            student_user, university=university, faculty=pharmacy, academic_year=1
        )
        assert profile.department is None

    def test_one_profile_per_user(self, student, student_user, university, pharmacy):
        with pytest.raises(BusinessError) as exc:
            services.create_student_profile(
                student_user, university=university, faculty=pharmacy, academic_year=1
            )
        assert exc.value.status_code == 409


# ═══════════════════════════════════════════════════════════
#  Bundles
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestBundles:
    def test_student_sees_bundles_for_their_year_only(self, student, pharmacy):
        for year in (1, 2, 3):
            StudyBundle.objects.create(
                faculty=pharmacy,
                academic_year=year,
                name_ar=f"حزمة {year}",
                name_en=f"Bundle {year}",
            )

        bundles = services.bundles_for_student(student)
        assert bundles.count() == 1
        assert bundles.first().academic_year == 2

    def test_faculty_wide_bundles_are_included_for_department_students(
        self, student_user, university, pharmacy
    ):
        """
        ⚠️  A bundle with no department belongs to every department in the faculty.

        Excluding it means a student in a specialised department never sees the
        shared essentials.
        """
        department = Department.objects.create(
            faculty=pharmacy, code="clinical", name_ar="إكلينيكي", name_en="Clinical"
        )
        profile = services.create_student_profile(
            student_user,
            university=university,
            faculty=pharmacy,
            department=department,
            academic_year=1,
        )

        StudyBundle.objects.create(
            faculty=pharmacy,
            academic_year=1,
            name_ar="عامة",
            name_en="General",
        )
        StudyBundle.objects.create(
            faculty=pharmacy,
            department=department,
            academic_year=1,
            name_ar="متخصصة",
            name_en="Specialised",
        )

        assert services.bundles_for_student(profile).count() == 2

    def test_required_bundles_are_filterable(self, student, pharmacy):
        StudyBundle.objects.create(
            faculty=pharmacy,
            academic_year=2,
            kind=BundleKind.REQUIRED,
            name_ar="مطلوبة",
            name_en="Required",
        )
        StudyBundle.objects.create(
            faculty=pharmacy,
            academic_year=2,
            kind=BundleKind.RECOMMENDED,
            name_ar="موصى بها",
            name_en="Recommended",
        )

        assert services.required_bundles_for_student(student).count() == 1

    def test_bundles_load_without_n_plus_one(
        self, student, pharmacy, products, django_assert_max_num_queries
    ):
        bundle = StudyBundle.objects.create(
            faculty=pharmacy, academic_year=2, name_ar="حزمة", name_en="Bundle"
        )
        for product in products:
            BundleItem.objects.create(bundle=bundle, product=product, quantity=2)

        with django_assert_max_num_queries(4):
            for entry in services.bundles_for_student(student):
                for item in entry.items.all():
                    _ = item.product.name_ar


# ═══════════════════════════════════════════════════════════
#  Promotion
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPromotion:
    def test_students_advance_one_year(self, student, pharmacy):
        assert services.promote_students(pharmacy) == 1

        student.refresh_from_db()
        assert student.academic_year == 3

    def test_final_year_students_are_not_promoted(self, student_user, university, pharmacy):
        """
        ⚠️  Unbounded promotion gives seventh-year students in a five-year
            faculty — and their bundles disappear entirely.
        """
        profile = services.create_student_profile(
            student_user, university=university, faculty=pharmacy, academic_year=5
        )

        assert services.promote_students(pharmacy) == 0

        profile.refresh_from_db()
        assert profile.academic_year == 5


# ═══════════════════════════════════════════════════════════
#  Domain boundaries
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestDomainBoundaries:
    def test_academic_does_not_import_cart(self):
        """
        ⚠️  `academic` is in L2 and `cart` is in L5.

        The "add a bundle to the cart" orchestration lives in `cart` —
        `import-linter` caught it being placed here the moment it was written.
        """
        import inspect

        from academic import services as academic_services

        source = inspect.getsource(academic_services)
        assert "from cart" not in source
        assert "import cart" not in source

    def test_bundle_item_stores_no_price(self):
        """`pricing` computes the price per customer — storing it goes silently stale."""
        names = {f.name for f in BundleItem._meta.get_fields()}

        assert "price" not in names
        assert "unit_price" not in names
