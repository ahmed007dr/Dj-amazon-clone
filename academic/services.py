"""
خدمات النطاق الأكاديمي.
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
    حزم الطالب لسنته.

    ⚠️  حزم القسم **وحزم الكلية العامة** معًا.

        الحزمة بلا قسم تخص كل أقسام الكلية — استبعادها يعني طالبًا
        في قسم متخصص لا يرى المستلزمات المشتركة.
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
    مرشِّح كتالوج الطالب.

    ⚠️  يُدمج مع مرشِّح السياسات لا يستبدله.

        السياق الأكاديمي يضيّق العرض تسويقيًا؛ أما الوصول فيحسمه
        `access` وحده. الخلط بينهما يجعل تضييقًا تسويقيًا يبدو
        كقرار أمني.
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
    """إنشاء ملف أكاديمي بعد التحقق من اتساق التسلسل."""
    if hasattr(user, "student_profile"):
        raise BusinessError(
            ErrorCode.CONFLICT, detail="لهذا الحساب ملف أكاديمي بالفعل", status_code=409
        )

    profile = StudentProfile(user=user, **data)
    profile.full_clean(exclude=["slug"])
    profile.save()
    return profile


def universities_with_faculties():
    """شجرة الجامعات — لنماذج التسجيل. استعلامان لا أكثر."""
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
    ترقية طلاب كلية سنةً دراسية.

    ⚠️  من بلغ سنة التخرّج لا يُرقّى — الترقية بلا حد تعطي طلابًا
        في السنة السابعة بكلية من خمس سنوات، فتختفي حزمهم.

    يُشغَّل يدويًا في بداية العام الدراسي لا تلقائيًا: تاريخ بدء
    العام يختلف بين الجامعات.
    """
    from django.db.models import F

    return StudentProfile.objects.filter(
        faculty=faculty, academic_year__lt=faculty.years_count
    ).update(academic_year=F("academic_year") + 1)
