"""
Student verification on the academic side.

⚠️  `StudentProfile.is_verified` is a **mirror** of `User.verification_status`, kept
    by one receiver (`academic.signals`). The approval itself happens in `customers`
    (see `customers/tests/test_document_review.py`); what is pinned here is that the
    mirror follows the account no matter who changes it, and that the admin student
    list — which used to have no pager at all and no names — now has both.

⚠️  `customers` is reached through `apps.get_model`: the two are independent siblings.
"""

import pytest
from django.apps import apps
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from academic import services
from academic.models import Faculty, StudentProfile, University
from accounts.models import AccountType, User, VerificationStatus
from core.testing import grant_all_domains

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


def make_user(email, account_type=AccountType.STUDENT, **extra) -> User:
    user = User.objects.create_user(
        email=email, password=PASSWORD, account_type=account_type, **extra
    )
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def faculty(db):
    university = University.objects.create(code="cu", name_ar="القاهرة", name_en="Cairo")
    return Faculty.objects.create(
        university=university, code="pharm", name_ar="الصيدلة", name_en="Pharmacy", years_count=5
    )


def make_profile(email, faculty, *, year=2, **user_extra) -> StudentProfile:
    user = make_user(email, **user_extra)
    return services.create_student_profile(
        user, university=faculty.university, faculty=faculty, academic_year=year
    )


@pytest.fixture
def admin_client(db):
    admin = make_user("acad-admin@test.local", AccountType.ADMIN)
    apps.get_model("administration", "AdminProfile").objects.create(user=admin)
    grant_all_domains(admin)
    client = APIClient()
    client.force_authenticate(user=admin)
    return client


# ═══════════════════════════════════════════════════════════
#  The mirror
# ═══════════════════════════════════════════════════════════


class TestMirror:
    def test_verifying_the_account_verifies_the_profile(self, faculty):
        profile = make_profile("a@test.local", faculty)
        user = profile.user

        user.verification_status = VerificationStatus.VERIFIED
        user.save(update_fields=["verification_status"])

        profile.refresh_from_db()
        assert profile.is_verified is True

    def test_it_follows_the_account_back_down(self, faculty):
        profile = make_profile("b@test.local", faculty)
        user = profile.user
        user.verification_status = VerificationStatus.VERIFIED
        user.save(update_fields=["verification_status"])

        user.verification_status = VerificationStatus.REJECTED
        user.save(update_fields=["verification_status"])

        profile.refresh_from_db()
        assert profile.is_verified is False

    def test_a_full_save_also_mirrors(self, faculty):
        """The Django admin saves the whole row."""
        profile = make_profile("c@test.local", faculty)
        user = profile.user

        user.verification_status = VerificationStatus.VERIFIED
        user.save()

        profile.refresh_from_db()
        assert profile.is_verified is True

    def test_a_save_that_cannot_change_it_costs_nothing(self, faculty):
        """
        ⚠️  `last_login` is written on every sign-in — it must not pay a profile lookup.
        """
        user = make_profile("d@test.local", faculty).user

        with CaptureQueriesContext(connection) as ctx:
            user.save(update_fields=["last_login"])

        assert not [q for q in ctx.captured_queries if "academic_studentprofile" in q["sql"]]

    def test_another_students_profile_is_untouched(self, faculty):
        one = make_profile("e1@test.local", faculty)
        two = make_profile("e2@test.local", faculty)

        one.user.verification_status = VerificationStatus.VERIFIED
        one.user.save(update_fields=["verification_status"])

        two.refresh_from_db()
        assert two.is_verified is False

    def test_a_user_without_a_profile_is_fine(self):
        user = make_user("noprofile@test.local")

        user.verification_status = VerificationStatus.VERIFIED
        user.save(update_fields=["verification_status"])

    def test_a_profile_created_for_an_already_verified_user_starts_verified(self, faculty):
        user = make_user("early@test.local")
        user.verification_status = VerificationStatus.VERIFIED
        user.save(update_fields=["verification_status"])

        profile = services.create_student_profile(
            user, university=faculty.university, faculty=faculty, academic_year=1
        )

        assert profile.is_verified is True

    def test_a_profile_created_for_an_unverified_user_starts_unverified(self, faculty):
        assert make_profile("late@test.local", faculty).is_verified is False


# ═══════════════════════════════════════════════════════════
#  The admin student list
# ═══════════════════════════════════════════════════════════


class TestAdminStudentList:
    URL = "v1:academic:admin-students"

    def _get(self, client, **params):
        response = client.get(reverse(self.URL), params)
        assert response.status_code == 200, response.content
        return response.data

    def test_it_is_paginated_with_a_total(self, admin_client, faculty):
        """
        ⚠️  The default cursor pagination has no `count`/`page`/`pages` — the screen's
            pager had nothing to draw.
        """
        for n in range(5):
            make_profile(f"s{n}@test.local", faculty)

        body = self._get(admin_client, limit=2, page=2)

        assert body["count"] == 5 and body["pages"] == 3 and body["page"] == 2
        assert len(body["results"]) == 2

    def test_a_row_says_who_the_student_is(self, admin_client, faculty):
        make_profile(
            "salma@test.local", faculty, first_name="سلمى", last_name="أحمد", phone="01001234567"
        )

        row = self._get(admin_client)["results"][0]

        assert row["user_name"] == "سلمى أحمد"
        assert row["user_email"] == "salma@test.local"
        assert row["user_phone"] == "01001234567"
        assert row["verification_status"] == "NOT_REQUIRED"
        assert row["faculty_name"] == "الصيدلة"
        assert row["is_verified"] is False

    def test_the_students_own_contract_does_not_leak_contact_data(self, faculty):
        """The admin fields are on the admin serializer only."""
        profile = make_profile("self@test.local", faculty)
        client = APIClient()
        client.force_authenticate(user=profile.user)

        body = client.get(reverse("v1:academic:me")).data

        assert "user_email" not in body and "user_phone" not in body and "user_name" not in body

    def test_search(self, admin_client, faculty):
        make_profile("zed@test.local", faculty, first_name="زياد")
        make_profile("other@test.local", faculty, first_name="منى")

        assert self._get(admin_client, search="zed")["count"] == 1
        assert self._get(admin_client, search="منى")["count"] == 1
        assert self._get(admin_client, search="nobody")["count"] == 0

    def test_verified_filter(self, admin_client, faculty):
        done = make_profile("done@test.local", faculty)
        done.user.verification_status = VerificationStatus.VERIFIED
        done.user.save(update_fields=["verification_status"])
        make_profile("waiting@test.local", faculty)

        assert self._get(admin_client, verified="true")["count"] == 1
        assert self._get(admin_client, verified="false")["count"] == 1
        assert self._get(admin_client)["count"] == 2

    def test_year_and_faculty_filters(self, admin_client, faculty):
        make_profile("y1@test.local", faculty, year=1)
        make_profile("y2@test.local", faculty, year=2)

        assert self._get(admin_client, academic_year=2)["count"] == 1
        assert self._get(admin_client, faculty=str(faculty.pk))["count"] == 2
        assert self._get(admin_client, university=str(faculty.university_id))["count"] == 2

    @pytest.mark.parametrize(
        "params",
        [{"faculty": "abc"}, {"university": "1"}, {"academic_year": "x"}, {"verified": "maybe"}],
    )
    def test_bad_filters_are_a_400_not_a_500(self, admin_client, params):
        assert admin_client.get(reverse(self.URL), params).status_code == 400

    def test_a_student_cannot_list_students(self, faculty):
        profile = make_profile("nosy@test.local", faculty)
        client = APIClient()
        client.force_authenticate(user=profile.user)

        assert client.get(reverse(self.URL)).status_code == 403

    def test_the_query_count_does_not_grow_with_the_students(self, admin_client, faculty):
        def queries():
            with CaptureQueriesContext(connection) as ctx:
                assert admin_client.get(reverse(self.URL)).status_code == 200
            return len(ctx)

        for n in range(2):
            make_profile(f"q{n}@test.local", faculty)
        queries()  # warms the reviewer's cached permission lookups
        small = queries()

        for n in range(2, 9):
            make_profile(f"q{n}@test.local", faculty)

        assert queries() == small
