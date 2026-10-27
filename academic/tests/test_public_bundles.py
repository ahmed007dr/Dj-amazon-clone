"""
The public bundles list — everyone sees every active bundle.

⚠️  Before this endpoint, `/me/bundles/` was the only list, and it was scoped to the
    caller's own faculty and year: a visitor, a student of another faculty, or a
    student who had not completed their profile saw nothing at all.

    The list is now public and unscoped; narrowing it is the visitor's choice,
    made with optional filters. These tests pin both halves — nothing hides by
    default, and every filter narrows exactly what it names.

⚠️  `catalog` is reached through `apps.get_model` — the two are independent siblings.
"""

import itertools
from decimal import Decimal

import pytest
from django.apps import apps
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

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

pytestmark = pytest.mark.django_db

PASSWORD = "Str0ng-Test-Pass!23"
URL = "v1:academic:bundles"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture(autouse=True)
def _products(db):
    category = apps.get_model("catalog", "Category").objects.create(
        name_ar="فئة", name_en="Category"
    )
    product_model = apps.get_model("catalog", "Product")
    return [
        product_model.objects.create(
            sku=f"PB-{i}",
            name_ar=f"صنف {i}",
            name_en=f"Item {i}",
            category=category,
            base_price=Decimal("10.00"),
        )
        for i in range(3)
    ]


@pytest.fixture
def cairo(db):
    return University.objects.create(code="cu", name_ar="القاهرة", name_en="Cairo")


@pytest.fixture
def ain_shams(db):
    return University.objects.create(code="asu", name_ar="عين شمس", name_en="Ain Shams")


@pytest.fixture
def pharmacy(cairo):
    return Faculty.objects.create(
        university=cairo, code="pharm", name_ar="الصيدلة", name_en="Pharmacy", years_count=5
    )


@pytest.fixture
def medicine(ain_shams):
    return Faculty.objects.create(
        university=ain_shams, code="med", name_ar="الطب", name_en="Medicine", years_count=6
    )


_counter = itertools.count(1)


def make_bundle(faculty, *, year=1, kind=BundleKind.RECOMMENDED, name="حزمة", **extra):
    # ⚠️  An ASCII English name: the slug is built from it, and the detail route
    #     only accepts `[-a-zA-Z0-9_]`.
    return StudyBundle.objects.create(
        faculty=faculty,
        academic_year=year,
        kind=kind,
        name_ar=name,
        name_en=f"Bundle {next(_counter)}",
        **extra,
    )


def ids(response) -> set[str]:
    return {row["id"] for row in response.json()}


# ═══════════════════════════════════════════════════════════
#  Everyone sees everything — by default
# ═══════════════════════════════════════════════════════════


class TestUnfiltered:
    def test_an_anonymous_visitor_is_allowed(self, client, pharmacy):
        make_bundle(pharmacy)

        response = client.get(reverse(URL))

        assert response.status_code == 200

    def test_returns_every_active_bundle_across_faculties_and_universities(
        self, client, pharmacy, medicine
    ):
        a = make_bundle(pharmacy, year=1, name="صيدلة ١")
        b = make_bundle(pharmacy, year=3, name="صيدلة ٣")
        c = make_bundle(medicine, year=2, name="طب ٢")

        response = client.get(reverse(URL))

        assert ids(response) == {str(a.pk), str(b.pk), str(c.pk)}

    def test_a_signed_in_student_of_another_faculty_sees_all_of_them_too(
        self, pharmacy, medicine, cairo
    ):
        """
        ⚠️  The profile is a shortcut for filling the filters, not a wall.
        """
        mine = make_bundle(pharmacy, year=2)
        theirs = make_bundle(medicine, year=2)
        user = User.objects.create_user(
            email="s@test.local", password=PASSWORD, account_type=AccountType.STUDENT
        )
        user.is_active = True
        user.save()
        services.create_student_profile(user, university=cairo, faculty=pharmacy, academic_year=2)
        authed = APIClient()
        authed.force_authenticate(user=user)

        response = authed.get(reverse(URL))

        assert ids(response) == {str(mine.pk), str(theirs.pk)}

    def test_a_user_without_a_student_profile_sees_them_too(self, pharmacy):
        bundle = make_bundle(pharmacy)
        user = User.objects.create_user(
            email="plain@test.local", password=PASSWORD, account_type=AccountType.DOCTOR
        )
        user.is_active = True
        user.save()
        authed = APIClient()
        authed.force_authenticate(user=user)

        assert ids(authed.get(reverse(URL))) == {str(bundle.pk)}

    def test_each_card_says_whose_bundle_it_is(self, client, pharmacy):
        dept = Department.objects.create(
            faculty=pharmacy, code="clin", name_ar="الصيدلة الإكلينيكية", name_en="Clinical"
        )
        make_bundle(pharmacy, year=4, department=dept)

        row = client.get(reverse(URL)).json()[0]

        assert row["faculty"] == str(pharmacy.pk)
        assert row["faculty_name_ar"] == "الصيدلة"
        assert row["faculty_name_en"] == "Pharmacy"
        assert row["university"] == str(pharmacy.university_id)
        assert row["university_name_ar"] == "القاهرة"
        assert row["university_name_en"] == "Cairo"
        assert row["department"] == str(dept.pk)
        assert row["department_name_en"] == "Clinical"

    def test_a_faculty_wide_bundle_has_no_department(self, client, pharmacy):
        make_bundle(pharmacy)

        row = client.get(reverse(URL)).json()[0]

        assert row["department"] is None
        assert row["department_name_ar"] is None

    def test_the_list_carries_a_count_not_the_items(self, client, pharmacy, _products):
        bundle = make_bundle(pharmacy)
        for product in _products:
            BundleItem.objects.create(bundle=bundle, product=product)

        row = client.get(reverse(URL)).json()[0]

        assert row["item_count"] == 3
        assert "items" not in row

    def test_ordered_by_year_then_required_first(self, client, pharmacy):
        """Required first within a year — the order a student buys in, not the alphabet's."""
        optional = make_bundle(pharmacy, year=1, kind=BundleKind.OPTIONAL, name="ج")
        recommended = make_bundle(pharmacy, year=1, kind=BundleKind.RECOMMENDED, name="ب")
        required = make_bundle(pharmacy, year=1, kind=BundleKind.REQUIRED, name="أ")
        second_year = make_bundle(pharmacy, year=2, kind=BundleKind.REQUIRED, name="د")

        order = [row["id"] for row in client.get(reverse(URL)).json()]

        assert order == [
            str(required.pk),
            str(recommended.pk),
            str(optional.pk),
            str(second_year.pk),
        ]

    def test_the_slug_route_is_not_shadowed_by_the_list(self, client, pharmacy):
        bundle = make_bundle(pharmacy)

        detail = client.get(reverse("v1:academic:bundle-detail", args=[bundle.slug]))

        assert detail.status_code == 200
        assert detail.json()["id"] == str(bundle.pk)

    def test_the_detail_names_the_faculty_too(self, client, pharmacy):
        bundle = make_bundle(pharmacy)

        body = client.get(reverse("v1:academic:bundle-detail", args=[bundle.slug])).json()

        assert body["faculty_name_en"] == "Pharmacy"
        assert body["university_name_en"] == "Cairo"
        assert "items" in body


# ═══════════════════════════════════════════════════════════
#  What is hidden
# ═══════════════════════════════════════════════════════════


class TestHidden:
    def test_an_inactive_bundle_is_excluded(self, client, pharmacy):
        visible = make_bundle(pharmacy, name="ظاهرة")
        make_bundle(pharmacy, name="مخفية", is_active=False)

        assert ids(client.get(reverse(URL))) == {str(visible.pk)}

    def test_a_soft_deleted_bundle_is_excluded(self, client, pharmacy):
        visible = make_bundle(pharmacy, name="ظاهرة")
        gone = make_bundle(pharmacy, name="محذوفة")
        gone.delete()

        assert ids(client.get(reverse(URL))) == {str(visible.pk)}

    def test_a_bundle_of_an_inactive_faculty_is_excluded(self, client, pharmacy, medicine):
        """
        ⚠️  The bundle itself is active — it is the faculty that is switched off.
        """
        visible = make_bundle(pharmacy)
        make_bundle(medicine)
        medicine.is_active = False
        medicine.save()

        assert ids(client.get(reverse(URL))) == {str(visible.pk)}

    def test_a_bundle_of_an_inactive_university_is_excluded(self, client, pharmacy, medicine):
        visible = make_bundle(pharmacy)
        make_bundle(medicine)
        medicine.university.is_active = False
        medicine.university.save()

        assert ids(client.get(reverse(URL))) == {str(visible.pk)}

    def test_a_bundle_of_an_inactive_department_is_excluded(self, client, pharmacy):
        dept = Department.objects.create(
            faculty=pharmacy, code="x", name_ar="قسم", name_en="Dept", is_active=False
        )
        visible = make_bundle(pharmacy, name="عامة")
        make_bundle(pharmacy, name="قسم موقوف", department=dept)

        assert ids(client.get(reverse(URL))) == {str(visible.pk)}


# ═══════════════════════════════════════════════════════════
#  The filters
# ═══════════════════════════════════════════════════════════


class TestFilters:
    @pytest.fixture
    def catalogue(self, pharmacy, medicine):
        dept = Department.objects.create(
            faculty=pharmacy, code="clin", name_ar="إكلينيكية", name_en="Clinical"
        )
        return {
            "dept": dept,
            "ph1_req": make_bundle(pharmacy, year=1, kind=BundleKind.REQUIRED, name="١"),
            "ph2_rec": make_bundle(pharmacy, year=2, kind=BundleKind.RECOMMENDED, name="٢"),
            "ph2_dept": make_bundle(
                pharmacy, year=2, kind=BundleKind.OPTIONAL, name="٣", department=dept
            ),
            "md2_req": make_bundle(medicine, year=2, kind=BundleKind.REQUIRED, name="٤"),
        }

    def _get(self, client, **params):
        response = client.get(reverse(URL), params)
        assert response.status_code == 200, response.content
        return ids(response)

    def test_by_university(self, client, catalogue, medicine):
        got = self._get(client, university=str(medicine.university_id))

        assert got == {str(catalogue["md2_req"].pk)}

    def test_by_faculty(self, client, catalogue, pharmacy):
        got = self._get(client, faculty=str(pharmacy.pk))

        assert got == {str(catalogue[key].pk) for key in ("ph1_req", "ph2_rec", "ph2_dept")}

    def test_by_department_is_an_exact_match(self, client, catalogue):
        """Faculty-wide bundles have no department, so they are not part of it."""
        got = self._get(client, department=str(catalogue["dept"].pk))

        assert got == {str(catalogue["ph2_dept"].pk)}

    def test_by_academic_year(self, client, catalogue):
        got = self._get(client, academic_year=2)

        assert got == {str(catalogue[key].pk) for key in ("ph2_rec", "ph2_dept", "md2_req")}

    def test_by_kind(self, client, catalogue):
        got = self._get(client, kind="REQUIRED")

        assert got == {str(catalogue[key].pk) for key in ("ph1_req", "md2_req")}

    def test_filters_combine(self, client, catalogue, pharmacy):
        got = self._get(client, faculty=str(pharmacy.pk), academic_year=2, kind="RECOMMENDED")

        assert got == {str(catalogue["ph2_rec"].pk)}

    def test_a_filter_matching_nothing_is_an_empty_list_not_an_error(self, client, catalogue):
        assert self._get(client, academic_year=9) == set()

    def test_an_unknown_but_well_formed_faculty_is_an_empty_list(self, client, catalogue):
        assert self._get(client, faculty="00000000-0000-0000-0000-000000000000") == set()

    def test_blank_values_mean_no_filter(self, client, catalogue):
        """The client drops empty values, but `?kind=` must not become "kind is empty"."""
        got = self._get(client, university="", faculty="", academic_year="", kind="")

        assert len(got) == 4  # every bundle in the catalogue


class TestBadInput:
    @pytest.mark.parametrize(
        "params",
        [
            {"university": "not-a-uuid"},
            {"faculty": "123"},
            {"department": "abc"},
            {"academic_year": "x"},
            {"academic_year": "0"},
            {"academic_year": "11"},
            {"kind": "BOGUS"},
        ],
    )
    def test_a_malformed_value_is_a_400(self, client, pharmacy, params):
        make_bundle(pharmacy)

        response = client.get(reverse(URL), params)

        assert response.status_code == 400
        assert response.data["code"] == "VALIDATION_ERROR"
        assert next(iter(params)) in response.data["fields"]


# ═══════════════════════════════════════════════════════════
#  Cost
# ═══════════════════════════════════════════════════════════


class TestCost:
    def _fill(self, faculty, count, products):
        for n in range(count):
            bundle = make_bundle(faculty, year=(n % 5) + 1, name=f"حزمة {n}")
            for product in products:
                BundleItem.objects.create(bundle=bundle, product=product)

    def _queries(self, client):
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(reverse(URL))
        assert response.status_code == 200
        return len(ctx), len(response.json())

    def test_the_query_count_does_not_grow_with_the_number_of_bundles(
        self, client, pharmacy, medicine, _products
    ):
        self._fill(pharmacy, 2, _products)
        small_queries, small_rows = self._queries(client)

        self._fill(pharmacy, 8, _products)
        self._fill(medicine, 6, _products)
        large_queries, large_rows = self._queries(client)

        assert small_rows == 2 and large_rows == 16
        assert large_queries == small_queries
        # bundles + their items; the faculty/university/department come with the first
        assert large_queries <= 3

    def test_the_list_is_capped(self, client, pharmacy, monkeypatch):
        monkeypatch.setattr(services, "PUBLIC_BUNDLE_LIMIT", 3)
        for n in range(5):
            make_bundle(pharmacy, year=1, name=f"حزمة {n}")

        assert len(client.get(reverse(URL)).json()) == 3


class TestMyBundlesUnchanged:
    """`/me/bundles/` is still the "my faculty" source — scoped, and not slower."""

    @pytest.fixture
    def student_client(self, cairo, pharmacy):
        user = User.objects.create_user(
            email="mine@test.local", password=PASSWORD, account_type=AccountType.STUDENT
        )
        user.is_active = True
        user.save()
        services.create_student_profile(user, university=cairo, faculty=pharmacy, academic_year=2)
        authed = APIClient()
        authed.force_authenticate(user=user)
        return authed

    def test_still_scoped_to_the_students_faculty_and_year(
        self, student_client, pharmacy, medicine
    ):
        mine = make_bundle(pharmacy, year=2)
        make_bundle(pharmacy, year=3)
        make_bundle(medicine, year=2)

        response = student_client.get(reverse("v1:academic:my-bundles"))

        assert ids(response) == {str(mine.pk)}

    def test_the_new_location_fields_cost_no_extra_queries(
        self, student_client, pharmacy, _products
    ):
        for n in range(6):
            bundle = make_bundle(pharmacy, year=2, name=f"حزمة {n}")
            BundleItem.objects.create(bundle=bundle, product=_products[0])

        with CaptureQueriesContext(connection) as ctx:
            response = student_client.get(reverse("v1:academic:my-bundles"))

        assert response.status_code == 200
        assert response.json()[0]["faculty_name_en"] == "Pharmacy"
        # auth user, profile, bundles, items (+ product joins) — independent of the six cards
        assert len(ctx) <= 6
