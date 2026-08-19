"""
واجهات بوابة الموظفين.

⚠️  **كل نقطة موظف مُصفّاة بإسناده — بلا استثناء واحد.**

    نسيان التصفية في نقطة واحدة يكشف قائمة العملاء كاملة لمندوب
    أُسند له ثلاثة. ولذلك المرور كله من `services.assigned_customers`
    و`assert_may_act_for`، لا من استعلام مكتوب في كل view.
"""

from __future__ import annotations

from datetime import date

from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from employees import serializers as s
from employees import services
from employees.models import (
    AssignmentStatus,
    CustomerAssignment,
    EmployeeProfile,
    EmployeeRole,
)
from employees.permissions import CanManageEmployees, HasEmployeeProfile


class EmployeeMixin:
    def get_employee(self) -> EmployeeProfile:
        profile = getattr(self.request.user, "employee_profile", None)
        if profile is None:
            raise BusinessError(
                ErrorCode.NOT_FOUND,
                detail="لا ملف موظف لهذا الحساب — تواصل مع الإدارة",
                status_code=404,
            )
        return profile


def _period_from(request) -> tuple[date, date]:
    """الشهر الحالي افتراضًا — وهو ما يقيس المندوب نفسه به."""
    today = timezone.localdate()

    raw_start = request.query_params.get("start")
    raw_end = request.query_params.get("end")

    start = date.fromisoformat(raw_start) if raw_start else today.replace(day=1)
    end = date.fromisoformat(raw_end) if raw_end else today

    if start > end:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="بداية الفترة بعد نهايتها")

    return start, end


# ═══════════════════════════════════════════════════════════
#  بوابة الموظف
# ═══════════════════════════════════════════════════════════


class MyProfileAPI(EmployeeMixin, APIView):
    permission_classes = [HasEmployeeProfile]
    serializer_class = s.EmployeeProfileSerializer

    def get(self, request):
        employee = self.get_employee()
        return Response(s.EmployeeProfileSerializer(employee).data)


class MyDashboardAPI(EmployeeMixin, APIView):
    """
    لوحة أداء المندوب.

    ⚠️  **الأداء وحده — بلا هدف ولا عمولة.**

        `targets` و`commissions` **فوق** هذا النطاق في ترتيب
        الطبقات، فلا يجوز أن يستوردهما. وضع حقول فارغة لهما هنا
        كان حلًّا مؤقتًا صار كذبًا بعد بنائهما: حقل اسمه `target`
        يعود `null` دائمًا يُقرأ «لا هدف» لا «اسأل مكانًا آخر».

        الشاشة تركّب من ثلاث نقاط: هذه و`/targets/me/`
        و`/commissions/me/` — ثلاثة استعلامات متوازية صغيرة.
    """

    permission_classes = [HasEmployeeProfile]

    def get(self, request):
        employee = self.get_employee()
        start, end = _period_from(request)

        result = services.performance(employee, start, end)

        return Response(
            {
                "employee_number": employee.employee_number,
                "full_name": employee.user.full_name,
                "role": employee.role.name_ar,
                "start": str(result.start),
                "end": str(result.end),
                "orders_count": result.orders_count,
                "gross_sales": str(result.gross_sales),
                "returns_total": str(result.returns_total),
                "net_sales": str(result.net_sales),
                "average_order": str(result.average_order),
                "customers_count": result.customers_count,
                "new_customers": result.new_customers,
                "history": services.monthly_history(employee),
            }
        )


class MyCustomersAPI(EmployeeMixin, generics.ListAPIView):
    """
    عملاء المندوب — **وحدهم**.

    ⚠️  البحث يعمل **داخل** المُسنَد لا فوقه.

        بحث يتجاوز التصفية يجعل المندوب يعثر على أي عميل باسمه،
        فيقرأ هاتفه وحجم مشترياته — وهي بالضبط بيانات المنافسة
        الداخلية بين المندوبين.
    """

    permission_classes = [HasEmployeeProfile]
    serializer_class = s.AssignedCustomerSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        employee = getattr(self.request.user, "employee_profile", None)
        queryset = services.assigned_customers(employee).select_related("user")

        if term := self.request.query_params.get("search"):
            queryset = queryset.filter(
                Q(display_name_ar__icontains=term)
                | Q(customer_number__iexact=term)
                | Q(user__phone__icontains=term)
                | Q(user__email__icontains=term)
            )

        return queryset.order_by("-last_order_at")


class MyCustomerOrdersAPI(EmployeeMixin, APIView):
    """طلبات عميل مُسنَد."""

    permission_classes = [HasEmployeeProfile]

    def get(self, request, pk):
        from customers.models import CustomerProfile
        from orders.serializers import OrderListSerializer

        employee = self.get_employee()
        customer = get_object_or_404(CustomerProfile, pk=pk)

        # ⚠️  الحارس قبل أي قراءة — لا بعد جلب البيانات.
        services.assert_may_act_for(employee, customer)

        from orders.models import Order

        orders = Order.objects.filter(customer=customer).order_by("-created_at")[:50]
        return Response(OrderListSerializer(orders, many=True).data)


class CreateOrderForCustomerAPI(EmployeeMixin, APIView):
    """
    إنشاء طلب نيابةً عن عميل مُسنَد.

    ⚠️  **`owner_employee` يُملأ هنا — وهو أساس العمولة لاحقًا.**

        تركه فارغًا يجعل الطلب بلا نسبة، فيسقط من أداء المندوب
        ومن حساب عمولته في المرحلة ١١ — ويُكتشف في نهاية الشهر.

    ⚠️  والسلة سلة **الموظف** لا العميل.

        استخدام سلة العميل يعني أن المندوب يعدّل ما يبنيه العميل
        على هاتفه في نفس اللحظة. الأسطر تُرسَل صراحةً هنا.
    """

    permission_classes = [HasEmployeeProfile]
    serializer_class = s.EmployeeOrderSerializer

    @transaction.atomic
    def post(self, request):
        from cart import services as cart_services
        from catalog.models import Product
        from customers.models import CustomerProfile
        from orders import serializers as order_serializers
        from orders import services as order_services
        from orders.models import OrderChannel

        serializer = s.EmployeeOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        employee = self.get_employee()
        customer = get_object_or_404(CustomerProfile, pk=data["customer"])
        services.assert_may_act_for(employee, customer)

        # ⚠️  سلة مؤقتة باسم العميل: التسعير يعتمد على **من يشتري**
        #     لا على من يكتب. بناؤها على المندوب كان يطبّق أسعار
        #     التجزئة على صيدلية.
        cart = cart_services.get_active_cart(user=customer.user)
        cart_services.clear(cart)

        products = Product.objects.in_bulk([line["product"] for line in data["lines"]])
        for line in data["lines"]:
            product = products.get(line["product"])
            if product is None:
                raise BusinessError(
                    ErrorCode.NOT_FOUND,
                    detail=f"منتج غير موجود: {line['product']}",
                    status_code=404,
                )
            cart_services.add_line(cart, product, line["quantity"])

        order = order_services.create_from_cart(
            cart,
            customer=customer,
            address=order_services.resolve_address(customer, data),
            shipping_method_code=data.get("shipping_method_code", ""),
            channel=OrderChannel.EMPLOYEE,
            created_by=request.user,
            customer_note=data.get("customer_note", ""),
        )

        # ⚠️  النسبة بعد الإنشاء مباشرةً وفي نفس المعاملة.
        order.owner_employee = request.user
        order.save(update_fields=["owner_employee", "updated_at"])

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.CREATE,
            object_repr=f"طلب موظف {order.number}",
            changes={"customer": customer.customer_number, "total": str(order.grand_total)},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(
            order_serializers.OrderDetailSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )


# ═══════════════════════════════════════════════════════════
#  الأدمن
# ═══════════════════════════════════════════════════════════


class AdminRoleListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [CanManageEmployees]
    serializer_class = s.EmployeeRoleSerializer
    pagination_class = None

    def get_queryset(self):
        return EmployeeRole.objects.annotate(permission_count=Count("permissions"))

    def perform_create(self, serializer):
        role = serializer.save()
        services.sync_role_permissions(role)


class AdminRoleDetailAPI(generics.RetrieveUpdateAPIView):
    """
    تعديل دور — **وصلاحياته**.

    ⚠️  **المزامنة بعد كل حفظ وإلا كانت الصلاحيات زينة.**

        `has_perm` يقرأ مجموعات المستخدم لا جدول `EmployeeRole`
        (ADR-53). الحفظ بلا `sync_role_permissions` يجعل الشاشة
        تعرض دورًا مضبوطًا وكل فحص صلاحية يفشل.

    ⚠️  و**بلا حذف**: الدور مفتاح إلزامي على كل موظف؛ حذفه يقطع
        انتماء من يحمله. التعطيل (`is_active`) هو المسار.
    """

    permission_classes = [CanManageEmployees]
    serializer_class = s.EmployeeRoleSerializer

    def get_queryset(self):
        return EmployeeRole.objects.annotate(permission_count=Count("permissions"))

    def perform_update(self, serializer):
        role = serializer.save()
        services.sync_role_permissions(role)

        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.UPDATE,
            object_repr=f"صلاحيات الدور {role.code}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
            changes={"permissions": sorted(
                f"{p.content_type.app_label}.{p.codename}"
                for p in role.permissions.select_related("content_type")
            )},
        )


class AdminPermissionCatalogueAPI(APIView):
    """
    دليل الصلاحيات — **مُنتقى بأسماء تقول ما تفتحه**.

    ⚠️  عرض جدول `auth.Permission` كما هو يجعل الشاشة غير قابلة
        للاستعمال (مئتا سطر بأسماء تقنية)، والأخطر أنه يجعل منح
        `delete_user` سهوًا أمرًا وارد الحدوث بضغطة.
    """

    permission_classes = [CanManageEmployees]

    def get(self, request):
        from core.permissions import PERMISSION_CATALOGUE

        return Response(
            [
                {
                    "key": group["key"],
                    "label_ar": group["label_ar"],
                    "label_en": group["label_en"],
                    "permissions": [
                        {"code": code, "label_ar": label_ar, "label_en": label_en}
                        for code, label_ar, label_en in group["permissions"]
                    ],
                }
                for group in PERMISSION_CATALOGUE
            ]
        )


class AdminEmployeeListAPI(generics.ListAPIView):
    permission_classes = [CanManageEmployees]
    serializer_class = s.EmployeeProfileSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = EmployeeProfile.objects.select_related("user", "role", "manager__user").annotate(
            customers_count=Count(
                "assignments", filter=Q(assignments__status=AssignmentStatus.ACTIVE)
            )
        )
        params = self.request.query_params

        if value := params.get("role"):
            queryset = queryset.filter(role_id=value)
        if params.get("active") == "false":
            queryset = queryset.filter(is_active=False)
        elif params.get("active") == "true":
            queryset = queryset.filter(is_active=True)
        if value := params.get("search"):
            queryset = queryset.filter(
                Q(employee_number__icontains=value)
                | Q(user__first_name__icontains=value)
                | Q(user__last_name__icontains=value)
                | Q(user__email__icontains=value)
            )

        return queryset


class AdminEmployeeDetailAPI(generics.RetrieveUpdateAPIView):
    permission_classes = [CanManageEmployees]
    serializer_class = s.EmployeeProfileSerializer
    queryset = EmployeeProfile.objects.select_related("user", "role", "manager__user")


class AdminEmployeePerformanceAPI(APIView):
    permission_classes = [CanManageEmployees]

    def get(self, request, pk):
        employee = get_object_or_404(EmployeeProfile, pk=pk)
        start, end = _period_from(request)
        result = services.performance(employee, start, end)

        return Response(
            {
                "employee_number": employee.employee_number,
                "full_name": employee.user.full_name,
                "orders_count": result.orders_count,
                "gross_sales": str(result.gross_sales),
                "returns_total": str(result.returns_total),
                "net_sales": str(result.net_sales),
                "average_order": str(result.average_order),
                "customers_count": result.customers_count,
                "new_customers": result.new_customers,
                "history": services.monthly_history(employee),
            }
        )


class AdminAssignmentListAPI(generics.ListAPIView):
    permission_classes = [CanManageEmployees]
    serializer_class = s.CustomerAssignmentSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = CustomerAssignment.objects.select_related("customer", "employee__user")
        params = self.request.query_params

        if value := params.get("employee"):
            queryset = queryset.filter(employee_id=value)
        if value := params.get("customer"):
            queryset = queryset.filter(customer_id=value)
        if params.get("active") == "true":
            queryset = queryset.filter(status=AssignmentStatus.ACTIVE)

        return queryset


class AdminAssignCustomerAPI(APIView):
    """
    إسناد عميل إلى موظف.

    ⚠️  النقل يُنهي الإسناد السابق ولا يحذفه.

        العمولة تُحسب على من كان مسؤولًا **وقت البيع**؛ وحذف
        السجل القديم يجعل كل طلب سابق بلا نسبة.
    """

    permission_classes = [CanManageEmployees]
    serializer_class = s.AssignCustomerSerializer

    def post(self, request):
        from customers.models import CustomerProfile

        serializer = s.AssignCustomerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        customer = get_object_or_404(CustomerProfile, pk=data["customer"])
        employee = get_object_or_404(EmployeeProfile, pk=data["employee"])

        assignment = services.assign_customer(
            customer, employee, actor=request.user, note=data.get("note", "")
        )

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"إسناد {customer.customer_number} → {employee.employee_number}",
            changes={"note": data.get("note", "")},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(
            s.CustomerAssignmentSerializer(assignment).data,
            status=status.HTTP_201_CREATED,
        )


class AdminEndAssignmentAPI(APIView):
    permission_classes = [CanManageEmployees]

    def post(self, request, pk):
        from customers.models import CustomerProfile

        customer = get_object_or_404(CustomerProfile, pk=pk)
        ended = services.end_assignment(customer, actor=request.user)

        return Response({"ended": ended})


class AdminUnassignedCustomersAPI(generics.ListAPIView):
    """
    عملاء بلا مسؤول.

    ⚠️  الشاشة التي تمنع ضياع العملاء بين المندوبين.

        عميل بلا إسناد لا يتابعه أحد ولا يظهر في لوحة أي مندوب —
        ولا شيء ينبّه إليه إلا هذه القائمة.
    """

    permission_classes = [CanManageEmployees]
    serializer_class = s.AssignedCustomerSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        from customers.models import CustomerProfile

        return (
            CustomerProfile.objects.exclude(assignments__status=AssignmentStatus.ACTIVE)
            .select_related("user")
            .order_by("-total_spent")
        )
