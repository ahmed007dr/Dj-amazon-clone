"""
Academic domain services.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Prefetch, Q

from academic.models import (
    BundleItem,
    BundleKind,
    Department,
    Faculty,
    StudentProfile,
    StudyBundle,
    University,
)
from core.errors import BusinessError, ErrorCode


def bundles_for_student(student: StudentProfile):
    """
    A student's bundles for their year.

    ⚠️  The department's bundles **and the faculty's general bundles** together.

        A bundle with no department belongs to every department in the faculty —
        excluding it means a student in a specialised department never sees the
        shared essentials.
    """
    queryset = StudyBundle.objects.filter(
        faculty=student.faculty,
        academic_year=student.academic_year,
        is_active=True,
    )

    if student.department_id:
        queryset = queryset.filter(Q(department=student.department) | Q(department__isnull=True))
    else:
        queryset = queryset.filter(department__isnull=True)

    return queryset.prefetch_related(
        Prefetch(
            "items",
            queryset=BundleItem.objects.select_related(
                "product", "product__category", "product__access_policy", "variant"
            ),
        )
    ).order_by("kind", "display_order")


def required_bundles_for_student(student: StudentProfile):
    return bundles_for_student(student).filter(kind=BundleKind.REQUIRED)


def catalog_filter_for_student(student: StudentProfile | None) -> Q:
    """
    The student catalogue filter.

    ⚠️  Combined with the policy filter, never a replacement for it.

        Academic context narrows the display for marketing reasons; access is
        decided by `access` alone. Conflating the two makes a marketing
        restriction look like a security decision.
    """
    if student is None:
        return Q()

    product_ids = BundleItem.objects.filter(
        bundle__faculty=student.faculty,
        bundle__academic_year=student.academic_year,
        bundle__is_active=True,
    ).values_list("product_id", flat=True)

    return Q(pk__in=product_ids)


@transaction.atomic
def create_student_profile(user, **data) -> StudentProfile:
    """Create an academic profile after verifying hierarchy consistency."""
    if hasattr(user, "student_profile"):
        raise BusinessError(
            ErrorCode.CONFLICT, detail="لهذا الحساب ملف أكاديمي بالفعل", status_code=409
        )

    profile = StudentProfile(user=user, **data)
    profile.full_clean(exclude=["slug"])
    profile.save()
    return profile


def universities_with_faculties():
    """The university tree — for registration forms. Two queries, no more."""
    return University.objects.filter(is_active=True).prefetch_related(
        Prefetch(
            "faculties",
            queryset=Faculty.objects.filter(is_active=True).prefetch_related(
                Prefetch(
                    "departments",
                    queryset=Department.objects.filter(is_active=True),
                )
            ),
        )
    )


def promote_students(faculty: Faculty) -> int:
    """
    Promote a faculty's students by one academic year.

    ⚠️  Anyone who has reached the graduation year is not promoted — unbounded
        promotion gives seventh-year students in a five-year faculty, so their
        bundles disappear.

    Run manually at the start of the academic year, never automatically: the
    start date differs between universities.
    """
    from django.db.models import F

    return StudentProfile.objects.filter(
        faculty=faculty, academic_year__lt=faculty.years_count
    ).update(academic_year=F("academic_year") + 1)
