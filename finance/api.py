"""
Finance endpoints — admin only (business rule 14).

⚠️  **Not one customer-facing endpoint.**

    Nothing here concerns a buyer. Putting any of it behind a customer
    permission — even by mistake — exposes profit margins and purchase costs to
    a competitor with a free account.
"""

from __future__ import annotations

from datetime import date

from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from finance import serializers as s
from finance import services
from finance.models import Expense, ExpenseCategory, ExpenseStatus, FiscalPeriod
from finance.permissions import CanApproveExpenses, CanManageExpenses, CanViewFinance


def _period_from(request) -> tuple[date, date]:
    """
    The period from the query parameters — the current month by default.

    ⚠️  A start after the end is rejected explicitly.

        Letting it through produces a report of zeros that looks **genuine**: no
        error, no rows, so it reads as a month with no sales rather than an
        inverted range.
    """
    # ⚠️  `localdate()`, not `now().date()`: a "today" report on the UTC date
    #     shows yesterday's sales during the first hours of the day in Cairo time.
    today = timezone.localdate()

    raw_start = request.query_params.get("start")
    raw_end = request.query_params.get("end")

    start = date.fromisoformat(raw_start) if raw_start else today.replace(day=1)
    end = date.fromisoformat(raw_end) if raw_end else today

    if start > end:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="بداية الفترة بعد نهايتها")

    return start, end


# ═══════════════════════════════════════════════════════════
#  Reports
# ═══════════════════════════════════════════════════════════


class ProfitAndLossAPI(APIView):
    """
    The profit and loss statement.

    ⚠️  Every number here is **a sum of rows that can be opened**, not a
        black-box calculation.
    """

    permission_classes = [CanViewFinance]

    def get(self, request):
        start, end = _period_from(request)
        report = services.profit_and_loss(start, end)

        return Response(
            {
                "start": str(report.start),
                "end": str(report.end),
                "revenue": str(report.revenue),
                "refunds": str(report.refunds),
                "discounts": str(report.discounts),
                "tax_collected": str(report.tax_collected),
                "net_sales": str(report.net_sales),
                "cogs": str(report.cogs),
                "gross_profit": str(report.gross_profit),
                "gross_margin": str(report.gross_margin),
                "expenses": str(report.expenses),
                "net_profit": str(report.net_profit),
                # ⚠️  Both are always sent, not only when present: a frontend that
                #     reads absence as zero shows an incomplete report as though it were complete.
                "unknown_cost_units": report.unknown_cost_units,
                "is_reliable": report.is_reliable,
                "pending_expenses": str(report.pending_expenses),
                "by_category": services.expenses_by_category(start, end),
                "by_channel": services.revenue_by_channel(start, end),
            }
        )


class CashFlowAPI(APIView):
    permission_classes = [CanViewFinance]

    def get(self, request):
        start, end = _period_from(request)
        flow = services.cash_flow(start, end)

        return Response(
            {
                "start": str(flow.start),
                "end": str(flow.end),
                "cash_in": str(flow.cash_in),
                "cash_out": str(flow.cash_out),
                "net": str(flow.net),
            }
        )


# ═══════════════════════════════════════════════════════════
#  Expense categories
# ═══════════════════════════════════════════════════════════


class ExpenseCategoryListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [CanManageExpenses]
    serializer_class = s.ExpenseCategorySerializer
    pagination_class = None

    def get_queryset(self):
        return ExpenseCategory.objects.annotate(expense_count=Count("expenses"))


class ExpenseCategoryDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [CanManageExpenses]
    serializer_class = s.ExpenseCategorySerializer
    queryset = ExpenseCategory.objects.all()

    def perform_destroy(self, instance):
        """
        ⚠️  A category in use is **never deleted** — it is disabled.

            Deleting it leaves expenses with no category, so they vanish from
            the "where did the money go" breakdown while their sum remains in
            the total. The difference between the two is precisely the number
            nobody can explain later.
        """
        if instance.expenses.exists():
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail="البند مستخدَم في مصروفات — عطّله بدل حذفه",
                status_code=409,
            )
        if instance.children.exists():
            raise BusinessError(ErrorCode.CONFLICT, detail="البند له بنود فرعية", status_code=409)
        instance.delete()


# ═══════════════════════════════════════════════════════════
#  Expenses
# ═══════════════════════════════════════════════════════════


class ExpenseListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [CanManageExpenses]
    serializer_class = s.ExpenseSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = Expense.objects.select_related("category", "entered_by", "approved_by")
        params = self.request.query_params

        if value := params.get("status"):
            queryset = queryset.filter(status=value)
        if value := params.get("category"):
            queryset = queryset.filter(category_id=value)
        if value := params.get("date_from"):
            queryset = queryset.filter(incurred_on__gte=value)
        if value := params.get("date_to"):
            queryset = queryset.filter(incurred_on__lte=value)

        return queryset

    def perform_create(self, serializer):
        # ⚠️  A closed period rejects entry — before the save, not after.
        services.assert_period_open(serializer.validated_data["incurred_on"])

        expense = serializer.save(
            entered_by=self.request.user,
            # ⚠️  The status is forced here rather than read from the request: whoever
            #     enters an expense does not approve it themselves.
            status=ExpenseStatus.DRAFT,
        )

        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.CREATE,
            object_repr=f"مصروف {expense.category.name_ar} · {expense.amount}",
            changes={"amount": str(expense.amount), "incurred_on": str(expense.incurred_on)},
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )


class ExpenseDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [CanManageExpenses]
    serializer_class = s.ExpenseSerializer
    queryset = Expense.objects.select_related("category", "entered_by", "approved_by")

    def perform_update(self, serializer):
        """
        ⚠️  An approved expense is **never edited**.

            Editing it changes a number that has entered a report already
            issued. Corrections go through an offsetting expense, or by
            un-approving first.
        """
        if serializer.instance.status == ExpenseStatus.APPROVED:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail="المصروف معتمد — لا يُعدَّل بعد دخوله التقرير",
                status_code=409,
            )
        services.assert_period_open(serializer.instance.incurred_on)
        serializer.save()

    def perform_destroy(self, instance):
        if instance.status == ExpenseStatus.APPROVED:
            raise BusinessError(
                ErrorCode.CONFLICT, detail="المصروف معتمد — لا يُحذف", status_code=409
            )
        instance.delete()


class ExpenseDecisionAPI(APIView):
    """
    Approve or reject an expense.

    ⚠️  A **separate** permission from entry: someone who enters and approves
        their own expense makes approval a signature on a blank page.
    """

    permission_classes = [CanApproveExpenses]
    serializer_class = s.ExpenseDecisionSerializer

    def post(self, request, pk):
        serializer = s.ExpenseDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        expense = get_object_or_404(Expense, pk=pk)

        if data["decision"] == "APPROVE":
            services.approve_expense(expense, approved_by=request.user)
        else:
            services.reject_expense(expense, rejected_by=request.user, reason=data["reason"])

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"مصروف {expense.category.name_ar} · {expense.amount}",
            changes={"decision": data["decision"], "reason": data.get("reason", "")},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(s.ExpenseSerializer(expense).data)


# ═══════════════════════════════════════════════════════════
#  Periods
# ═══════════════════════════════════════════════════════════


class FiscalPeriodListAPI(generics.ListAPIView):
    permission_classes = [CanViewFinance]
    serializer_class = s.FiscalPeriodSerializer
    queryset = FiscalPeriod.objects.select_related("closed_by")
    pagination_class = None


class ClosePeriodAPI(APIView):
    """
    Close a month.

    ⚠️  **Irreversible from the frontend.**

        Reopening it means a report that was issued and acted upon could change
        retroactively — which is exactly what the period exists to prevent.
        Reopening remains possible from `manage.py`, as a deliberate decision
        rather than a click.
    """

    permission_classes = [CanApproveExpenses]
    serializer_class = s.ClosePeriodSerializer

    def post(self, request):
        serializer = s.ClosePeriodSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        period, _ = FiscalPeriod.objects.get_or_create(year=data["year"], month=data["month"])

        if period.is_closed:
            raise BusinessError(ErrorCode.CONFLICT, detail="الفترة مقفلة سلفًا", status_code=409)

        # ⚠️  A draft expense inside the period blocks closing.
        #
        #     Closing it makes that expense impossible to approve, edit or
        #     delete — it hangs forever outside every report.
        pending = Expense.objects.filter(
            status=ExpenseStatus.DRAFT,
            incurred_on__year=data["year"],
            incurred_on__month=data["month"],
        ).count()

        if pending:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail=f"{pending} مصروف بانتظار الاعتماد — احسمها قبل الإقفال",
                status_code=409,
            )

        period.close(by=request.user, note=data.get("note", ""))

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"إقفال الفترة {period}",
            changes={"note": period.note},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(s.FiscalPeriodSerializer(period).data, status=status.HTTP_201_CREATED)
