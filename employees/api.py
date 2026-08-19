"""
Staff portal endpoints.

⚠️  **Every staff endpoint is filtered by their assignment — without a single exception.**

    Forgetting the filter on one endpoint exposes the entire customer list to a
    rep assigned three. That is why everything goes through
    `services.assigned_customers` and `assert_may_act_for`, rather than a query
    written in each view.
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
    """The current month by default — which is what the rep measures themselves by."""
    today = timezone.localdate()

    raw_start = request.query_params.get("start")
    raw_end = request.query_params.get("end")

    start = date.fromisoformat(raw_start) if raw_start else today.replace(day=1)
    end = date.fromisoformat(raw_end) if raw_end else today

    if start > end:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="بداية الفترة بعد نهايتها")

    return start, end


# ═══════════════════════════════════════════════════════════
#  The employee portal
# ═══════════════════════════════════════════════════════════


class MyProfileAPI(EmployeeMixin, APIView):
    permission_classes = [HasEmployeeProfile]
    serializer_class = s.EmployeeProfileSerializer

    def get(self, request):
        employee = self.get_employee()
        return Response(s.EmployeeProfileSerializer(employee).data)


class MyDashboardAPI(EmployeeMixin, APIView):
    """
    The rep's performance dashboard.

    ⚠️  **Performance alone — no target and no commission.**

        `targets` and `commissions` sit **above** this domain in the layer
        order, so it must not import them. Putting empty fields for them here
        was a stopgap that became a lie once they were built: a field called
        `target` that always returns `null` reads as "no target", not "ask
        somewhere else".

        The screen composes three endpoints: this one, `/targets/me/` and
        `/commissions/me/` — three small parallel queries.
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
    The rep's customers — **theirs alone**.

    ⚠️  Search works **inside** the assignment, never above it.

        A search that bypasses the filter lets the rep find any customer by
        name, reading their phone number and purchase volume — which is exactly
        the data reps compete over internally.
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
    """An assigned customer's orders."""

    permission_classes = [HasEmployeeProfile]

    def get(self, request, pk):
        from customers.models import CustomerProfile
        from orders.serializers import OrderListSerializer

        employee = self.get_employee()
        customer = get_object_or_404(CustomerProfile, pk=pk)

        # ⚠️  The guard comes before any read — not after fetching the data.
        services.assert_may_act_for(employee, customer)

        from orders.models import Order

        orders = Order.objects.filter(customer=customer).order_by("-created_at")[:50]
        return Response(OrderListSerializer(orders, many=True).data)


class CreateOrderForCustomerAPI(EmployeeMixin, APIView):
    """
    Create an order on behalf of an assigned customer.

    ⚠️  **`owner_employee` is filled in here — and it is the basis of the commission later.**

        Leaving it empty makes the order unattributed, so it drops out of the
        rep's performance and out of their commission calculation in phase 11 —
        and it is discovered at the end of the month.

    ⚠️  And the cart is the **employee's** cart, not the customer's.

        Using the customer's cart means the rep edits what the customer is
        building on their phone at that very moment. The lines are sent
        explicitly here.
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

        # ⚠️  A temporary cart in the customer's name: pricing depends on **who buys**,
        #     not on who types. Building it on the rep applied retail prices
        #     to a pharmacy.
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

        # ⚠️  The attribution happens immediately after creation and in the same transaction.
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
#  Admin
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
    Edit a role — **and its permissions**.

    ⚠️  **Synchronise after every save, or the permissions are decoration.**

        `has_perm` reads the user's groups, not the `EmployeeRole` table
        (ADR-53). Saving without `sync_role_permissions` makes the screen show a
        configured role while every permission check fails.

    ⚠️  And **no deletion**: the role is a mandatory key on every employee;
        deleting it severs the affiliation of whoever holds it. Deactivation
        (`is_active`) is the path.
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
    The permission catalogue — **curated, under names that say what they open**.

    ⚠️  Displaying the `auth.Permission` table as-is makes the screen unusable
        (two hundred rows of technical names), and worse, it makes granting
        `delete_user` by oversight a real possibility, one click away.
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
    Assign a customer to an employee.

    ⚠️  A transfer ends the previous assignment rather than deleting it.

        Commission is calculated on whoever was responsible **at the time of
        sale**; deleting the old record leaves every previous order unattributed.
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
    Customers with no owner.

    ⚠️  The screen that stops customers being lost between reps.

        An unassigned customer is followed up by nobody and appears on no rep's
        dashboard — and nothing draws attention to them but this list.
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
