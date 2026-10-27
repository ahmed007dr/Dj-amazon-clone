"""
Academic domain endpoints.

⚠️  These appear as sections inside the customer portal, not as a sixth portal. (ADR-18)
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from academic import serializers as s
from academic import services
from academic.models import (
    BundleItem,
    Department,
    Faculty,
    StudentProfile,
    StudyBundle,
    University,
)
from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from core.permissions import CanManageAcademic


class UniversityTreeAPI(generics.ListAPIView):
    """
    The university tree — for the registration form.

    ⚠️  Public: a student picks their university **before** creating an account.
    """

    permission_classes = [AllowAny]
    serializer_class = s.UniversitySerializer
    pagination_class = None

    def get_queryset(self):
        return services.universities_with_faculties()


class MyStudentProfileAPI(APIView):
    """The current user's academic profile."""

    permission_classes = [IsAuthenticated]
    serializer_class = s.StudentProfileSerializer

    def get(self, request):
        profile = getattr(request.user, "student_profile", None)
        if profile is None:
            # ⚠️  `null`, not `404` — a missing profile is normal for non-students
            return Response(None)
        return Response(s.StudentProfileSerializer(profile).data)

    def post(self, request):
        serializer = s.CreateStudentProfileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            profile = services.create_student_profile(
                request.user,
                university=get_object_or_404(University, pk=data["university"]),
                faculty=get_object_or_404(Faculty, pk=data["faculty"]),
                department=(
                    get_object_or_404(Department, pk=data["department"])
                    if data.get("department")
                    else None
                ),
                academic_year=data["academic_year"],
                student_number=data.get("student_number", ""),
            )
        except DjangoValidationError as exc:
            # ⚠️  Academic-hierarchy consistency errors are translated into field errors
            raise serializers.ValidationError(exc.message_dict) from exc

        return Response(s.StudentProfileSerializer(profile).data, status=201)

    def patch(self, request):
        profile = getattr(request.user, "student_profile", None)
        if profile is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        serializer = s.StudentProfileSerializer(profile, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save()

        try:
            updated.full_clean()
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict) from exc

        return Response(s.StudentProfileSerializer(updated).data)


class MyBundlesAPI(generics.ListAPIView):
    """
    A student's bundles for their year.

    ⚠️  Their department's bundles **and their faculty's general bundles**
        together — excluding the latter means a student in a specialised
        department never sees the shared essentials.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = s.StudyBundleSerializer
    pagination_class = None

    def get_queryset(self):
        profile = getattr(self.request.user, "student_profile", None)
        if profile is None:
            return StudyBundle.objects.none()

        # ⚠️  `select_related` is added here, not in `bundles_for_student`: the
        #     serializer now names each bundle's faculty and university, and that
        #     service stays exactly what the "my faculty" shortcut relies on.
        queryset = services.bundles_for_student(profile).select_related(
            "faculty__university", "department"
        )
        if kind := self.request.query_params.get("kind"):
            queryset = queryset.filter(kind=kind)
        return queryset


class PublicBundleListAPI(generics.ListAPIView):
    """
    Every active bundle — for visitors and students alike.

    ⚠️  Public, and **not scoped to the caller's faculty**.

        Which faculty's bundles to look at is the visitor's choice, made with the
        optional filters below; nothing is filtered by default. A student's own
        profile only pre-fills those filters on the client (see `MyBundlesAPI`).

        Filters: `university` · `faculty` · `department` (UUIDs) ·
        `academic_year` (1-10) · `kind`. A malformed value is `400`.
    """

    permission_classes = [AllowAny]
    serializer_class = s.BundleListSerializer
    pagination_class = None

    def get_queryset(self):
        filters = s.BundleFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)

        return services.public_bundles(**filters.validated_data)[: services.PUBLIC_BUNDLE_LIMIT]


class BundleDetailAPI(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = s.StudyBundleSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return (
            StudyBundle.objects.filter(is_active=True)
            .select_related("faculty__university", "department")
            .prefetch_related("items__product", "items__variant")
        )


class AdminPromoteStudentsAPI(APIView):
    """
    Promote a faculty's students by one academic year.

    ⚠️  Manual, not automatic — the start date of the year differs between
        universities, and automatic promotion on a fixed date promotes students
        who have not started their year.
    """

    permission_classes = [CanManageAcademic]

    def post(self, request, pk):
        faculty = get_object_or_404(Faculty, pk=pk)
        promoted = services.promote_students(faculty)

        return Response(
            {
                "faculty": faculty.name_ar,
                "promoted": promoted,
                "note": "من بلغ سنة التخرّج لم يُرقَّ",
            }
        )


class AdminStudentListAPI(generics.ListAPIView):
    """
    The students, with who they are.

    ⚠️  Paginated with `AdminPageNumberPagination`, not the project default.

        The default is cursor pagination without a total — its response has no
        `page` or `pages`, so the screen's pager had nothing to draw. Admin lists
        that show "page 2 of 9" use the page-number class.
    """

    permission_classes = [CanManageAcademic]
    serializer_class = s.AdminStudentProfileSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = StudentProfile.objects.select_related(
            "user", "university", "faculty", "department"
        )

        filters = s.AdminStudentFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        params = filters.validated_data

        if "university" in params:
            queryset = queryset.filter(university_id=params["university"])
        if "faculty" in params:
            queryset = queryset.filter(faculty_id=params["faculty"])
        if "academic_year" in params:
            queryset = queryset.filter(academic_year=params["academic_year"])
        if params.get("verified"):
            queryset = queryset.filter(is_verified=params["verified"] == "true")
        if term := params.get("search", "").strip():
            queryset = queryset.filter(
                Q(user__email__icontains=term)
                | Q(user__first_name__icontains=term)
                | Q(user__last_name__icontains=term)
                | Q(user__phone__icontains=term)
                | Q(student_number__icontains=term)
            )

        return queryset.order_by("-created_at", "id")


# ═══════════════════════════════════════════════════════════
#  Admin — the academic tree and bundles
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  **The tree is a precondition for registering any student**: they pick
#      their university and faculty before creating an account. A store with no
#      universities screen accepts not a single student from its panel.


class _AcademicAdmin:
    permission_classes = [CanManageAcademic]
    pagination_class = None
    label = ""

    def _audit(self, instance, action):
        AuditLog.objects.create(
            actor=self.request.user,
            action=action,
            object_repr=f"{self.label} {instance.name_ar}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )


class AdminUniversityListCreateAPI(_AcademicAdmin, generics.ListCreateAPIView):
    serializer_class = s.AdminUniversitySerializer
    queryset = University.objects.order_by("name_ar")
    label = "جامعة"

    def perform_create(self, serializer):
        self._audit(serializer.save(), AuditAction.CREATE)


class AdminUniversityDetailAPI(_AcademicAdmin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = s.AdminUniversitySerializer
    queryset = University.objects.all()
    label = "جامعة"

    def perform_update(self, serializer):
        self._audit(serializer.save(), AuditAction.SETTING_CHANGE)

    def perform_destroy(self, instance):
        faculties = instance.faculties.count()
        if faculties:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail=f"لهذه الجامعة {faculties} كلية — أوقفها بدل حذفها",
                status_code=409,
            )
        self._audit(instance, AuditAction.DELETE)
        instance.delete()


class AdminFacultyListCreateAPI(_AcademicAdmin, generics.ListCreateAPIView):
    serializer_class = s.AdminFacultySerializer
    label = "كلية"

    def get_queryset(self):
        queryset = Faculty.objects.select_related("university").order_by(
            "university__name_ar", "name_ar"
        )
        if university := self.request.query_params.get("university"):
            queryset = queryset.filter(university_id=university)
        return queryset

    def perform_create(self, serializer):
        self._audit(serializer.save(), AuditAction.CREATE)


class AdminFacultyDetailAPI(_AcademicAdmin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = s.AdminFacultySerializer
    queryset = Faculty.objects.select_related("university")
    label = "كلية"

    def perform_update(self, serializer):
        self._audit(serializer.save(), AuditAction.SETTING_CHANGE)

    def perform_destroy(self, instance):
        """
        ⚠️  A faculty with students is not deleted — their profiles point at it,
            and deleting it leaves every student unaffiliated, so their bundles vanish.
        """
        students = instance.students.count()
        departments = instance.departments.count()

        if students or departments:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail=f"لهذه الكلية {students} طالبًا و{departments} قسمًا — أوقفها بدل حذفها",
                status_code=409,
            )
        self._audit(instance, AuditAction.DELETE)
        instance.delete()


class AdminDepartmentListCreateAPI(_AcademicAdmin, generics.ListCreateAPIView):
    serializer_class = s.AdminDepartmentSerializer
    label = "قسم"

    def get_queryset(self):
        queryset = Department.objects.select_related("faculty").order_by("name_ar")
        if faculty := self.request.query_params.get("faculty"):
            queryset = queryset.filter(faculty_id=faculty)
        return queryset

    def perform_create(self, serializer):
        self._audit(serializer.save(), AuditAction.CREATE)


class AdminDepartmentDetailAPI(_AcademicAdmin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = s.AdminDepartmentSerializer
    queryset = Department.objects.select_related("faculty")
    label = "قسم"

    def perform_update(self, serializer):
        self._audit(serializer.save(), AuditAction.SETTING_CHANGE)

    def perform_destroy(self, instance):
        self._audit(instance, AuditAction.DELETE)
        instance.delete()


class AdminBundleListCreateAPI(_AcademicAdmin, generics.ListCreateAPIView):
    serializer_class = s.AdminBundleSerializer
    label = "حزمة"

    def get_queryset(self):
        queryset = StudyBundle.objects.select_related("faculty").order_by(
            "faculty__name_ar", "academic_year", "display_order"
        )
        params = self.request.query_params

        if faculty := params.get("faculty"):
            queryset = queryset.filter(faculty_id=faculty)
        if year := params.get("academic_year"):
            queryset = queryset.filter(academic_year=year)

        return queryset

    def perform_create(self, serializer):
        self._audit(serializer.save(), AuditAction.CREATE)


class AdminBundleDetailAPI(_AcademicAdmin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = s.AdminBundleSerializer
    queryset = StudyBundle.objects.select_related("faculty")
    label = "حزمة"

    def perform_update(self, serializer):
        self._audit(serializer.save(), AuditAction.SETTING_CHANGE)

    def perform_destroy(self, instance):
        self._audit(instance, AuditAction.DELETE)
        instance.delete()


class AdminBundleItemListCreateAPI(_AcademicAdmin, generics.ListCreateAPIView):
    """
    Bundle items.

    ⚠️  Filtering by bundle is mandatory — a list of all items with no context is meaningless.
    """

    serializer_class = s.AdminBundleItemSerializer

    def get_queryset(self):
        return (
            BundleItem.objects.filter(bundle_id=self.kwargs["pk"])
            .select_related("product")
            .order_by("display_order", "id")
        )

    def perform_create(self, serializer):
        bundle = StudyBundle.objects.filter(pk=self.kwargs["pk"]).first()
        if bundle is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)
        serializer.save(bundle=bundle)


class AdminBundleItemDetailAPI(_AcademicAdmin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = s.AdminBundleItemSerializer
    lookup_url_kwarg = "item_pk"

    def get_queryset(self):
        # ⚠️  Filtered by bundle — no deleting another bundle's item by guessing its id
        return BundleItem.objects.filter(bundle_id=self.kwargs["pk"])
