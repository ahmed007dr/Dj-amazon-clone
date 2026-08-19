"""عقود بوابة الموظفين — المبالغ نصًا (ADR-31)."""

from rest_framework import serializers

from employees.models import CustomerAssignment, EmployeeProfile, EmployeeRole


class PermissionCodesField(serializers.Field):
    """
    صلاحيات الدور بصيغة `app_label.codename`.

    ⚠️  **بالرمز لا بالمعرّف الرقمي.**

        معرّفات `auth.Permission` تُولَّد بترتيب الهجرات وتختلف بين
        التطوير والإنتاج؛ واجهة تحفظ الرقم تمنح في الإنتاج صلاحية
        غير التي اختارها الأدمن على شاشته. والرمز ثابت أبدًا.

    ⚠️  و**لا يُقبل إلا ما في الدليل**.

        الجدول يحمل مئتي صلاحية آلية بينها `delete_user`؛ قبول أي
        رمز يعني أن نداءً مصنوعًا يمنح ما لا تعرضه الشاشة أصلًا.
    """

    def to_representation(self, value):
        return sorted(
            f"{p.content_type.app_label}.{p.codename}"
            for p in value.select_related("content_type")
        )

    def to_internal_value(self, data):
        from django.contrib.auth.models import Permission

        from core.permissions import CATALOGUE_CODES

        if not isinstance(data, list):
            raise serializers.ValidationError("القيمة يجب أن تكون قائمة")

        unknown = [code for code in data if code not in CATALOGUE_CODES]
        if unknown:
            raise serializers.ValidationError(
                f"صلاحيات خارج الدليل: {'، '.join(map(str, unknown))}"
            )

        found = []
        for code in dict.fromkeys(data):
            app_label, codename = code.split(".")
            permission = Permission.objects.filter(
                content_type__app_label=app_label, codename=codename
            ).first()
            if permission is None:
                raise serializers.ValidationError(f"صلاحية غير موجودة: {code}")
            found.append(permission)

        return found


class EmployeeRoleSerializer(serializers.ModelSerializer):
    permission_count = serializers.IntegerField(read_only=True, default=0)

    # ⚠️  `required=False` — إنشاء دور بلا صلاحيات حالة صالحة:
    #     يُنشأ فارغًا ثم تُمنح صلاحياته على مهل.
    permissions = PermissionCodesField(required=False)

    class Meta:
        model = EmployeeRole
        fields = [
            "id",
            "code",
            "kind",
            "name_ar",
            "name_en",
            "is_active",
            "permission_count",
            "permissions",
        ]
        read_only_fields = ["id", "permission_count"]


class EmployeeProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.full_name", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    role_name_ar = serializers.CharField(source="role.name_ar", read_only=True)
    role_name_en = serializers.CharField(source="role.name_en", read_only=True)
    manager_name = serializers.CharField(
        source="manager.user.full_name", read_only=True, default=None
    )
    customers_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = EmployeeProfile
        fields = [
            "id",
            "employee_number",
            "full_name",
            "email",
            "role",
            "role_name_ar",
            "role_name_en",
            "manager",
            "manager_name",
            "phone_extension",
            "hired_on",
            "is_active",
            "customers_count",
        ]
        read_only_fields = ["id", "full_name", "email", "customers_count"]


class AssignedCustomerSerializer(serializers.Serializer):
    """
    عميل مُسنَد — **حمولة أضيق مما يراه الأدمن**.

    ⚠️  المندوب يرى ما يخدم متابعته: الاسم والهاتف وآخر طلب
        وإجمالي مشترياته. ولا يرى الملاحظات الداخلية ولا الرقم
        الضريبي ولا وثائق التوثيق — وهي بيانات مراجعة لا بيع.
    """

    id = serializers.UUIDField(read_only=True)
    customer_number = serializers.CharField(read_only=True)
    display_name = serializers.CharField(read_only=True)
    phone = serializers.CharField(source="user.phone", read_only=True, default="")
    email = serializers.EmailField(source="user.email", read_only=True)
    segment = serializers.CharField(read_only=True)
    total_orders = serializers.IntegerField(read_only=True)
    total_spent = serializers.DecimalField(
        max_digits=12, decimal_places=2, coerce_to_string=True, read_only=True
    )
    last_order_at = serializers.DateTimeField(read_only=True)


class CustomerAssignmentSerializer(serializers.ModelSerializer):
    employee_number = serializers.CharField(source="employee.employee_number", read_only=True)
    employee_name = serializers.CharField(source="employee.user.full_name", read_only=True)
    customer_number = serializers.CharField(source="customer.customer_number", read_only=True)

    class Meta:
        model = CustomerAssignment
        fields = [
            "id",
            "customer",
            "customer_number",
            "employee",
            "employee_number",
            "employee_name",
            "status",
            "started_at",
            "ended_at",
            "note",
        ]
        read_only_fields = ["id", "status", "started_at", "ended_at"]


class AssignCustomerSerializer(serializers.Serializer):
    customer = serializers.UUIDField()
    employee = serializers.UUIDField()
    note = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class EmployeeOrderLineSerializer(serializers.Serializer):
    """
    ⚠️  سطر **مُصرَّح الحقول** لا `DictField`.

        `DictField` كان يمرّر المعرّف **نصًّا**، فلا يطابق مفاتيح
        `in_bulk` التي هي كائنات UUID — فيُرفض كل منتج بـ«غير
        موجود» وهو موجود. والتصريح يحوّل النوع عند الحدّ.
    """

    product = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=9999)


class EmployeeOrderSerializer(serializers.Serializer):
    """
    ⚠️  **بلا حقول مبالغ** — الطلب يُسعَّر من المصدر.

        قبول إجمالي من الواجهة يعني أن المندوب يحدّد سعر بيعه،
        وهو أول ما يُستغَل حين تُربَط العمولة بالمبيعات.
    """

    customer = serializers.UUIDField()
    lines = EmployeeOrderLineSerializer(many=True, allow_empty=False)
    address_id = serializers.UUIDField(required=False, allow_null=True)
    address = serializers.DictField(required=False)
    shipping_method_code = serializers.CharField(max_length=50, required=False, allow_blank=True)
    payment_method = serializers.CharField(max_length=16)
    customer_note = serializers.CharField(required=False, allow_blank=True, max_length=1000)

    def validate(self, attrs):
        if not attrs.get("address_id") and not attrs.get("address"):
            raise serializers.ValidationError("أرسل `address_id` أو `address`")
        return attrs
