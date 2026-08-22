"""
Target endpoints.

⚠️  **A rep reads their target and does not write it.**

    A target set by the person it applies to is not a target. All writing sits
    behind an administrative permission.
"""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.pagination import AdminPageNumberPagination
from core.models.audit import AuditAction, AuditLog
from employees.permissions import CanManageEmployees, HasEmployeeProfile
from targets import serializers as s
from targets import services
from targets.models import MonthlyTarget


class MyTargetAPI(APIView):
    """
    The current month's target — **or `null`**.

    ⚠️  `null`, not 404: a missing target is a normal state at the start of the
        month before management sets it, and not an error to be shown as a fault screen.
    """

    permission_classes = [HasEmployeeProfile]

    def get(self, request):
        employee = request.user.employee_profile
        target = services.current_target(employee)

        if target is None:
            return Response(None)

        result = services.measure(target)

        return Response(
            {
                "target": s.MonthlyTargetSerializer(target).data,
                "achieved_value": str(result.achieved_value),
                "achievement_percent": str(result.achievement_percent),
                "meets_minimum": result.meets_minimum,
                "gross_sales": str(result.gross_sales),
                "returns_total": str(result.returns_total),
                "net_sales": str(result.net_sales),
                "gross_profit": str(result.gross_profit),
                "orders_count": result.orders_count,
                "customers_count": result.customers_count,
            }
        )


class AdminTargetListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [CanManageEmployees]
    serializer_class = s.MonthlyTargetSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = MonthlyTarget.objects.select_related("employee__user")
        params = self.request.query_params

        if value := params.get("year"):
            queryset = queryset.filter(year=value)
        if value := params.get("month"):
            queryset = queryset.filter(month=value)
        if value := params.get("employee"):
            queryset = queryset.filter(employee_id=value)
        if value := params.get("status"):
            queryset = queryset.filter(status=value)

        return queryset


class AdminTargetDetailAPI(generics.RetrieveUpdateAPIView):
    permission_classes = [CanManageEmployees]
    serializer_class = s.MonthlyTargetSerializer
    queryset = MonthlyTarget.objects.select_related("employee__user")

    def perform_update(self, serializer):
        # ⚠️  A closed one is not edited: its snapshot is the basis of a commission that may have
        # been paid.
        from core.errors import BusinessError, ErrorCode

        if serializer.instance.is_closed:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail="الهدف مقفل — لا يُعدَّل بعد إقفاله",
                status_code=409,
            )
        serializer.save()


class AdminActivateTargetAPI(APIView):
    permission_classes = [CanManageEmployees]

    def post(self, request, pk):
        target = get_object_or_404(MonthlyTarget, pk=pk)
        services.activate(target)
        return Response(s.MonthlyTargetSerializer(target).data)


class AdminCloseTargetAPI(APIView):
    """⚠️  Closing freezes the snapshot — and it is never repeated."""

    permission_classes = [CanManageEmployees]

    def post(self, request, pk):
        target = get_object_or_404(MonthlyTarget, pk=pk)
        services.close_target(target, by=request.user)

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"إقفال هدف {target}",
            changes={
                "achieved": str(target.achieved_value),
                "percent": str(target.achievement_percent),
            },
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(s.MonthlyTargetSerializer(target).data)


class AdminBulkTargetsAPI(APIView):
    """Create a month's targets for a team — existing ones are skipped, not overwritten."""

    permission_classes = [CanManageEmployees]
    serializer_class = s.BulkTargetSerializer

    def post(self, request):
        serializer = s.BulkTargetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        created = services.bulk_create_month(
            data["year"], data["month"], data["rows"], actor=request.user
        )

        return Response(
            {"created": created, "received": len(data["rows"])},
            status=status.HTTP_201_CREATED,
        )
