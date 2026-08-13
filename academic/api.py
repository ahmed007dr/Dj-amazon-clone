"""
واجهات النطاق الأكاديمي.

⚠️  تظهر كأقسام داخل بوابة العميل لا كبوابة سادسة. (ADR-18)
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from academic import serializers as s
from academic import services
from academic.models import Department, Faculty, StudentProfile, StudyBundle, University
from core.errors import BusinessError, ErrorCode
from core.permissions import IsAdminAccount


class UniversityTreeAPI(generics.ListAPIView):
    """
    شجرة الجامعات — لنموذج التسجيل.

    ⚠️  عامة: الطالب يختار جامعته **قبل** إنشاء الحساب.
    """

    permission_classes = [AllowAny]
    serializer_class = s.UniversitySerializer
    pagination_class = None

    def get_queryset(self):
        return services.universities_with_faculties()


class MyStudentProfileAPI(APIView):
    """الملف الأكاديمي للمستخدم الحالي."""

    permission_classes = [IsAuthenticated]
    serializer_class = s.StudentProfileSerializer

    def get(self, request):
        profile = getattr(request.user, "student_profile", None)
        if profile is None:
            # ⚠️  `null` لا `404` — غياب الملف حالة عادية لغير الطلاب
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
            # ⚠️  أخطاء اتساق التسلسل تُترجم إلى أخطاء حقول
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
    حزم الطالب لسنته.

    ⚠️  حزم قسمه **وحزم كليته العامة** معًا — استبعاد الثانية يعني
        طالبًا في قسم متخصص لا يرى المستلزمات المشتركة.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = s.StudyBundleSerializer
    pagination_class = None

    def get_queryset(self):
        profile = getattr(self.request.user, "student_profile", None)
        if profile is None:
            return StudyBundle.objects.none()

        queryset = services.bundles_for_student(profile)
        if kind := self.request.query_params.get("kind"):
            queryset = queryset.filter(kind=kind)
        return queryset


class BundleDetailAPI(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = s.StudyBundleSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return StudyBundle.objects.filter(is_active=True).prefetch_related(
            "items__product", "items__variant"
        )


class AdminPromoteStudentsAPI(APIView):
    """
    ترقية طلاب كلية سنةً دراسية.

    ⚠️  يدوي لا تلقائي — تاريخ بدء العام يختلف بين الجامعات،
        والترقية التلقائية بتاريخ ثابت ترقّي طلابًا لم يبدأوا عامهم.
    """

    permission_classes = [IsAdminAccount]

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
    permission_classes = [IsAdminAccount]
    serializer_class = s.StudentProfileSerializer

    def get_queryset(self):
        queryset = StudentProfile.objects.select_related(
            "user", "university", "faculty", "department"
        )
        params = self.request.query_params

        if university := params.get("university"):
            queryset = queryset.filter(university_id=university)
        if faculty := params.get("faculty"):
            queryset = queryset.filter(faculty_id=faculty)
        if year := params.get("academic_year"):
            queryset = queryset.filter(academic_year=year)
        if params.get("verified") == "false":
            queryset = queryset.filter(is_verified=False)

        return queryset.order_by("-created_at")
