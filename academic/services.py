"""
Academic domain services.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Case, IntegerField, Prefetch, Q, Value, When

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


#: A sane ceiling for the public list.
#:
#: ⚠️  The list is unpaginated on purpose — a visitor browses it with filters, not
#:     page by page — so the ceiling is what keeps one anonymous request from
#:     loading every bundle of every faculty with its items.
PUBLIC_BUNDLE_LIMIT = 300

_KIND_RANK = Case(
    When(kind=BundleKind.REQUIRED, then=Value(0)),
    When(kind=BundleKind.RECOMMENDED, then=Value(1)),
    default=Value(2),
    output_field=IntegerField(),
)


def public_bundles(
    *,
    university=None,
    faculty=None,
    department=None,
    academic_year=None,
    kind=None,
):
    """
    Every bundle a visitor may browse — filtered only by what they asked for.

    ⚠️  **Not scoped to the visitor's own faculty.**

        Whoever is looking — a guest, a student of another faculty, a parent —
        chooses the university and faculty themselves; the student's own profile
        is only a shortcut for filling those filters (`bundles_for_student` keeps
        serving that shortcut).

    ⚠️  A bundle of an inactive faculty or university is hidden even when the
        bundle itself is active: the tree screens cannot offer that faculty, so a
        card pointing at it could never be reached by filtering.
    """
    queryset = StudyBundle.objects.filter(
        is_active=True,
        faculty__is_active=True,
        faculty__deleted_at__isnull=True,
        faculty__university__is_active=True,
        faculty__university__deleted_at__isnull=True,
    ).filter(
        # A faculty-wide bundle has no department; a department-bound one needs it active
        Q(department__isnull=True)
        | Q(department__is_active=True, department__deleted_at__isnull=True)
    )

    if university is not None:
        queryset = queryset.filter(faculty__university_id=university)
    if faculty is not None:
        queryset = queryset.filter(faculty_id=faculty)
    if department is not None:
        queryset = queryset.filter(department_id=department)
    if academic_year is not None:
        queryset = queryset.filter(academic_year=academic_year)
    if kind is not None:
        queryset = queryset.filter(kind=kind)

    return (
        queryset.select_related("faculty__university", "department")
        # ⚠️  Only to count them — the card shows "N items", not the items
        .prefetch_related(Prefetch("items", queryset=BundleItem.objects.only("id", "bundle_id")))
        .annotate(kind_rank=_KIND_RANK)
        .order_by(
            "faculty__university__name_ar",
            "faculty__name_ar",
            "academic_year",
            "kind_rank",
            "display_order",
            "name_ar",
            "id",
        )
    )


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

    # ⚠️  A student verified *before* creating the profile (the ID card is uploaded
    #     from the documents screen, which needs no profile) starts verified —
    #     `StudentProfile.is_verified` only mirrors `User.verification_status`.
    data.setdefault("is_verified", user.is_verified)

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
