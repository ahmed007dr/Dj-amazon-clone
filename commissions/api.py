"""
واجهات العمولات.

⚠️  **المندوب يرى عمولته هو — من السجل لا بإعادة حساب.**

    الرقم الذي يقرأه هو الذي سيُصرَف. إعادة حسابه عند كل فتح يجعله
    يتغيّر بين يوم وآخر بلا سبب ظاهر للمندوب.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from commissions import serializers as s
from commissions import services
from commissions.models import CommissionRecord, CommissionScheme
from commissions.permissions import CanManageCommissions
from core.api.pagination import AdminPageNumberPagination
from core.models.audit import AuditAction, AuditLog
from employees.permissions import HasEmployeeProfile


class MyCommissionsAPI(generics.ListAPIView):
    """عمولاتي — سجلّاتي وحدها."""

    permission_classes = [HasEmployeeProfile]
    serializer_class = s.CommissionRecordSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        return CommissionRecord.objects.filter(
            employee=self.request.user.employee_profile
        ).select_related("employee__user", "scheme")


class MyCommissionExplainAPI(APIView):
    """
    تفسير عمولة — **كل مدخلاتها**.

    ⚠️  هذا ما يجعل «كيف حُسبت؟» سؤالًا له جواب واحد ثابت لا
        يتغيّر بتغيّر البيانات بعد الحساب.
    """

    permission_classes = [HasEmployeeProfile]

    def get(self, request, pk):
        record = get_object_or_404(CommissionRecord, pk=pk, employee=request.user.employee_profile)
        return Response(services.explain(record))


class AdminSchemeListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [CanManageCommissions]
    serializer_class = s.CommissionSchemeSerializer
    pagination_class = None
    queryset = CommissionScheme.objects.prefetch_related("tiers").select_related("role")


class AdminCommissionListAPI(generics.ListAPIView):
    permission_classes = [CanManageCommissions]
    serializer_class = s.CommissionRecordSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = CommissionRecord.objects.select_related("employee__user", "scheme")
        params = self.request.query_params

        if value := params.get("year"):
            queryset = queryset.filter(year=value)
        if value := params.get("month"):
            queryset = queryset.filter(month=value)
        if value := params.get("status"):
            queryset = queryset.filter(status=value)
        if value := params.get("employee"):
            queryset = queryset.filter(employee_id=value)

        return queryset


class AdminCalculateMonthAPI(APIView):
    """
    حساب عمولات شهر.

    ⚠️  فشل موظف لا يوقف البقية — والنتيجة تُبلّغ النجاح والتخطّي
        معًا لا رقمًا واحدًا يُقرأ نجاحًا كاملًا.
    """

    permission_classes = [CanManageCommissions]
    serializer_class = s.CalculateMonthSerializer

    def post(self, request):
        serializer = s.CalculateMonthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result = services.calculate_month(data["year"], data["month"])

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"حساب عمولات {data['year']}-{data['month']:02d}",
            changes=result,
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(result)


class AdminCommissionDecisionAPI(APIView):
    permission_classes = [CanManageCommissions]
    serializer_class = s.CommissionDecisionSerializer

    def post(self, request, pk):
        serializer = s.CommissionDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        record = get_object_or_404(CommissionRecord, pk=pk)

        if data["decision"] == "APPROVE":
            services.approve(record, by=request.user)
        elif data["decision"] == "PAY":
            services.mark_paid(record, by=request.user)
        else:
            services.reject(record, by=request.user, reason=data["reason"])

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"عمولة {record.employee.employee_number} {record.year}-{record.month:02d}",
            changes={"decision": data["decision"], "amount": str(record.amount)},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(s.CommissionRecordSerializer(record).data)


class AdminExplainAPI(APIView):
    permission_classes = [CanManageCommissions]

    def get(self, request, pk):
        record = get_object_or_404(CommissionRecord, pk=pk)
        return Response(services.explain(record))
