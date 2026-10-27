"""Academic domain contracts."""

from rest_framework import serializers

from academic.models import (
    BundleItem,
    BundleKind,
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
    A university with its faculties and departments.

    ⚠️  The full tree in a single response — the registration form needs all of
        it at once, and lazy loading here means three calls per student.
    """

    faculties = FacultySerializer(many=True, read_only=True)

    class Meta:
        model = University
        fields = ["id", "code", "slug", "name_ar", "name_en", "city", "logo", "faculties"]


class BundleItemSerializer(serializers.ModelSerializer):
    """
    ⚠️  **No price.**

        `pricing` computes the price per customer from their price list —
        including it here means a number going silently stale inside the bundle.
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


#: Declared once so the two bundle contracts cannot drift apart
_BUNDLE_FIELDS = [
    "id",
    "slug",
    "name_ar",
    "name_en",
    "description_ar",
    "description_en",
    "kind",
    "academic_year",
    "image",
    "faculty",
    "faculty_name_ar",
    "faculty_name_en",
    "university",
    "university_name_ar",
    "university_name_en",
    "department",
    "department_name_ar",
    "department_name_en",
]


class _BundleSerializer(serializers.ModelSerializer):
    """
    What every public bundle contract shares — including **where it belongs**.

    ⚠️  The faculty and university are part of the bundle now.

        Bundles are public and unfiltered by the visitor's own profile, so a
        card has to say whose bundle it is: "Year 2 essentials" with no faculty
        beside it is meaningless once a Pharmacy and a Medicine bundle sit in
        the same list. Names come from the `select_related` of the queryset —
        a view that forgets it pays one query per card.
    """

    item_count = serializers.SerializerMethodField()

    faculty_name_ar = serializers.CharField(source="faculty.name_ar", read_only=True)
    faculty_name_en = serializers.CharField(source="faculty.name_en", read_only=True)
    university = serializers.UUIDField(source="faculty.university_id", read_only=True)
    university_name_ar = serializers.CharField(source="faculty.university.name_ar", read_only=True)
    university_name_en = serializers.CharField(source="faculty.university.name_en", read_only=True)
    department_name_ar = serializers.CharField(
        source="department.name_ar", read_only=True, default=None
    )
    department_name_en = serializers.CharField(
        source="department.name_en", read_only=True, default=None
    )

    def get_item_count(self, obj) -> int:
        # Read from the prefetch — no extra query
        return len(obj.items.all())


class StudyBundleSerializer(_BundleSerializer):
    items = BundleItemSerializer(many=True, read_only=True)

    class Meta:
        model = StudyBundle
        fields = [*_BUNDLE_FIELDS, "items", "item_count"]
        read_only_fields = fields


class BundleListSerializer(_BundleSerializer):
    """
    The bundles list — a card, not a page.

    ⚠️  **No `items`.** The full list of every bundle with every product inside
        it is the detail page's payload, repeated for each card; the card only
        shows how many items there are.
    """

    class Meta:
        model = StudyBundle
        fields = [*_BUNDLE_FIELDS, "item_count"]
        read_only_fields = fields


class BundleFilterSerializer(serializers.Serializer):
    """
    The public bundle filters — validated, never trusted.

    ⚠️  A malformed value is a `400`, not a `500` and not "no filter".

        `?faculty=abc` reaching the ORM raises a `ValidationError` deep inside a
        queryset, and silently ignoring it would show the visitor every faculty's
        bundles under a filter they believe is applied.
    """

    university = serializers.UUIDField(required=False)
    faculty = serializers.UUIDField(required=False)
    department = serializers.UUIDField(required=False)
    academic_year = serializers.IntegerField(required=False, min_value=1, max_value=10)
    kind = serializers.ChoiceField(required=False, choices=BundleKind.choices)


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
        # ⚠️  Verification is set by the admin after approving the student ID, not by the student
        read_only_fields = ["id", "is_verified"]


class AdminStudentProfileSerializer(StudentProfileSerializer):
    """
    The admin list of students — adds **who** the student is.

    ⚠️  Name, email and phone are for the admin screen only.

        The base contract is what a student receives about themselves, and it is
        also what the registration and account screens read. Putting contact data
        there would leak it into every response that reuses the base; extending it
        here keeps it behind `CanManageAcademic`.
    """

    user_id = serializers.UUIDField(read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_phone = serializers.CharField(source="user.phone", read_only=True)
    #: The account's authoritative state — `is_verified` above is only its mirror
    verification_status = serializers.CharField(source="user.verification_status", read_only=True)

    class Meta(StudentProfileSerializer.Meta):
        fields = [
            *StudentProfileSerializer.Meta.fields,
            "user_id",
            "user_name",
            "user_email",
            "user_phone",
            "verification_status",
            "created_at",
        ]
        read_only_fields = fields


class AdminStudentFilterSerializer(serializers.Serializer):
    """The admin student list filters — validated for the same reason as the public ones."""

    university = serializers.UUIDField(required=False)
    faculty = serializers.UUIDField(required=False)
    academic_year = serializers.IntegerField(required=False, min_value=1, max_value=10)
    # ⚠️  Not a `BooleanField`: on a query string DRF reads an absent checkbox
    #     as `False`, which would silently filter the list to unverified students.
    verified = serializers.ChoiceField(required=False, choices=["true", "false"])
    search = serializers.CharField(required=False, max_length=100)


class CreateStudentProfileSerializer(serializers.Serializer):
    university = serializers.UUIDField()
    faculty = serializers.UUIDField()
    department = serializers.UUIDField(required=False, allow_null=True)
    academic_year = serializers.IntegerField(min_value=1, max_value=10)
    student_number = serializers.CharField(max_length=50, required=False, allow_blank=True)


# ═══════════════════════════════════════════════════════════
#  Admin — the academic tree and bundles
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  The tree is **a precondition for registering any student**: they pick
#      their university and faculty before creating an account. It used to be managed from the
#      Django admin alone.


class AdminUniversitySerializer(serializers.ModelSerializer):
    faculty_count = serializers.SerializerMethodField()

    class Meta:
        model = University
        fields = [
            "id",
            "slug",
            "code",
            "name_ar",
            "name_en",
            "city",
            "governorate",
            "website",
            "is_active",
            "faculty_count",
        ]
        read_only_fields = ["id", "slug"]

    def get_faculty_count(self, obj) -> int:
        return obj.faculties.count()


class AdminFacultySerializer(serializers.ModelSerializer):
    university_name = serializers.CharField(source="university.name_ar", read_only=True)
    department_count = serializers.SerializerMethodField()
    student_count = serializers.SerializerMethodField()

    class Meta:
        model = Faculty
        fields = [
            "id",
            "slug",
            "university",
            "university_name",
            "code",
            "name_ar",
            "name_en",
            "years_count",
            "is_active",
            "department_count",
            "student_count",
        ]
        read_only_fields = ["id", "slug"]

    def get_department_count(self, obj) -> int:
        return obj.departments.count()

    def get_student_count(self, obj) -> int:
        return obj.students.count()

    def validate_years_count(self, value):
        """
        ⚠️  The year count governs **the bundle lists**: a fifth-year bundle in
            a four-year faculty is seen by nobody. And zero makes every bundle
            impossible to assign.
        """
        if value < 1:
            raise serializers.ValidationError("عدد السنوات لا يقل عن واحدة")
        return value


class AdminDepartmentSerializer(serializers.ModelSerializer):
    faculty_name = serializers.CharField(source="faculty.name_ar", read_only=True)

    class Meta:
        model = Department
        fields = [
            "id",
            "slug",
            "faculty",
            "faculty_name",
            "code",
            "name_ar",
            "name_en",
            "is_active",
        ]
        read_only_fields = ["id", "slug"]


class AdminBundleSerializer(serializers.ModelSerializer):
    faculty_name = serializers.CharField(source="faculty.name_ar", read_only=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = StudyBundle
        fields = [
            "id",
            "slug",
            "faculty",
            "faculty_name",
            "department",
            "academic_year",
            "kind",
            "name_ar",
            "name_en",
            "description_ar",
            "description_en",
            "display_order",
            "is_active",
            "item_count",
        ]
        read_only_fields = ["id", "slug"]

    def get_item_count(self, obj) -> int:
        return obj.items.count()

    def validate(self, attrs):
        """
        ⚠️  **A bundle's year must fall within its faculty's years.**

            A fifth-year bundle in a four-year faculty never reaches a student
            — it is created silently and then, weeks later, someone asks "why
            does nobody see it?".
        """
        instance = self.instance
        faculty = attrs.get("faculty", getattr(instance, "faculty", None))
        year = attrs.get("academic_year", getattr(instance, "academic_year", None))

        if faculty and year and year > faculty.years_count:
            raise serializers.ValidationError(
                {
                    "academic_year": (
                        f"كلية {faculty.name_ar} مدتها {faculty.years_count} سنوات — "
                        "لن يصل هذه الحزمة أي طالب"
                    )
                }
            )

        return attrs


class AdminBundleItemSerializer(serializers.ModelSerializer):
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name_ar", read_only=True)

    class Meta:
        model = BundleItem
        fields = [
            "id",
            "bundle",
            "product",
            "product_sku",
            "product_name",
            "variant",
            "quantity",
            # ⚠️  "Essential" separates what cannot be skipped from what is merely
            #     recommended — and a student buys only the essentials when money is tight.
            "is_essential",
            "note_ar",
            "note_en",
            "display_order",
        ]
        # ⚠️  The bundle comes from the path, not the payload: accepting it in the body
        #     allows adding an item to another bundle by guessing its id.
        read_only_fields = ["id", "bundle"]
