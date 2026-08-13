"""عقود النطاق الأكاديمي."""

from rest_framework import serializers

from academic.models import (
    BundleItem,
    Department,
    Faculty,
    StudentProfile,
    StudyBundle,
    University,
)


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "code", "slug", "name_ar", "name_en"]


class FacultySerializer(serializers.ModelSerializer):
    departments = DepartmentSerializer(many=True, read_only=True)

    class Meta:
        model = Faculty
        fields = ["id", "code", "slug", "name_ar", "name_en", "years_count", "departments"]


class UniversitySerializer(serializers.ModelSerializer):
    """
    الجامعة بكلياتها وأقسامها.

    ⚠️  شجرة كاملة في استجابة واحدة — نموذج التسجيل يحتاجها كلها
        دفعةً، والتحميل التدريجي هنا يعني ثلاثة نداءات لكل طالب.
    """

    faculties = FacultySerializer(many=True, read_only=True)

    class Meta:
        model = University
        fields = ["id", "code", "slug", "name_ar", "name_en", "city", "logo", "faculties"]


class BundleItemSerializer(serializers.ModelSerializer):
    """
    ⚠️  **بلا سعر.**

        السعر يحسبه `pricing` لكل عميل حسب قائمته — إدراجه هنا
        يعني رقمًا يتقادم بصمت داخل الحزمة.
    """

    product_slug = serializers.CharField(source="product.slug", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name_ar = serializers.CharField(source="product.name_ar", read_only=True)
    product_name_en = serializers.CharField(source="product.name_en", read_only=True)

    class Meta:
        model = BundleItem
        fields = [
            "id",
            "product",
            "product_slug",
            "product_sku",
            "product_name_ar",
            "product_name_en",
            "variant",
            "quantity",
            "is_essential",
            "note_ar",
            "note_en",
        ]
        read_only_fields = fields


class StudyBundleSerializer(serializers.ModelSerializer):
    items = BundleItemSerializer(many=True, read_only=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = StudyBundle
        fields = [
            "id",
            "slug",
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "kind",
            "academic_year",
            "image",
            "items",
            "item_count",
        ]
        read_only_fields = fields

    def get_item_count(self, obj) -> int:
        # يقرأ من الـ prefetch — بلا استعلام إضافي
        return len(obj.items.all())


class StudentProfileSerializer(serializers.ModelSerializer):
    university_name = serializers.CharField(source="university.name_ar", read_only=True)
    faculty_name = serializers.CharField(source="faculty.name_ar", read_only=True)
    department_name = serializers.CharField(
        source="department.name_ar", read_only=True, default=None
    )

    class Meta:
        model = StudentProfile
        fields = [
            "id",
            "university",
            "university_name",
            "faculty",
            "faculty_name",
            "department",
            "department_name",
            "academic_year",
            "student_number",
            "is_verified",
            "expected_graduation_year",
        ]
        # ⚠️  التوثيق يحدده الأدمن بعد اعتماد الكارنيه لا الطالب
        read_only_fields = ["id", "is_verified"]


class CreateStudentProfileSerializer(serializers.Serializer):
    university = serializers.UUIDField()
    faculty = serializers.UUIDField()
    department = serializers.UUIDField(required=False, allow_null=True)
    academic_year = serializers.IntegerField(min_value=1, max_value=10)
    student_number = serializers.CharField(max_length=50, required=False, allow_blank=True)
