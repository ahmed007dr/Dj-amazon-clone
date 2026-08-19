"""
Reporting endpoints — **read-only**.

⚠️  There is not one write endpoint here. A report reflects what happened; it
    does not change it.

⚠️  And the permission is **explicit**: the reports reveal sales, profits and
    every employee's performance by name. Tying them to panel access opens them
    to anyone who opened it for an entirely different reason.
"""

from __future__ import annotations

from datetime import date

from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from core.errors import BusinessError, ErrorCode
from core.permissions import CanViewReports
from reporting import services


def _period(request) -> tuple[date, date]:
    today = timezone.localdate()

    raw_start = request.query_params.get("start")
    raw_end = request.query_params.get("end")

    start = date.fromisoformat(raw_start) if raw_start else today.replace(day=1)
    end = date.fromisoformat(raw_end) if raw_end else today

    if start > end:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="بداية الفترة بعد نهايتها")

    return start, end


class OverviewAPI(APIView):
    """The combined dashboard — sales, profit and stock together."""

    permission_classes = [CanViewReports]

    def get(self, request):
        start, end = _period(request)
        return Response(services.overview(start, end))


def _positive_int(request, name: str, default: int, ceiling: int) -> int:
    """
    ⚠️  The limit is **capped**.

        `?limit=100000` against the order lines table is a query that paralyses
        the database, and no screen displays a hundred thousand rows. The cap
        makes the endpoint unusable as an exhaustion tool.
    """
    raw = request.query_params.get(name)
    if raw is None:
        return default

    try:
        value = int(raw)
    except ValueError as exc:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail=f"{name} يجب أن يكون عددًا") from exc

    if value < 1:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail=f"{name} يجب أن يكون موجبًا")

    return min(value, ceiling)


class SalesReportAPI(APIView):
    permission_classes = [CanViewReports]

    def get(self, request):
        start, end = _period(request)
        summary = services.sales_summary(start, end)

        return Response(
            {
                "start": str(summary.start),
                "end": str(summary.end),
                "orders_count": summary.orders_count,
                "gross_sales": str(summary.gross_sales),
                "returns_total": str(summary.returns_total),
                "net_sales": str(summary.net_sales),
                "average_order": str(summary.average_order),
                "customers_count": summary.customers_count,
                "by_day": services.sales_by_day(start, end),
                "by_channel": services.sales_by_channel(start, end),
                "by_category": services.sales_by_category(start, end),
                "top_products": services.top_products(
                    start,
                    end,
                    limit=_positive_int(request, "limit", 20, 200),
                    by=request.query_params.get("by", "revenue"),
                ),
            }
        )


class InventoryReportAPI(APIView):
    permission_classes = [CanViewReports]

    def get(self, request):
        days = int(request.query_params.get("expiry_days", 90))
        return Response(
            {
                "summary": services.inventory_summary(),
                "expiring": services.expiry_report(days),
            }
        )


class CustomersReportAPI(APIView):
    permission_classes = [CanViewReports]

    def get(self, request):
        start, end = _period(request)
        return Response(
            {
                "start": str(start),
                "end": str(end),
                **services.customer_behaviour(start, end),
                "by_segment": services.segment_breakdown(start, end),
            }
        )


class PeakHoursAPI(APIView):
    """
    Peak hours — a 7×24 map.

    ⚠️  Under **the same reporting permission**, not mere panel access.

        The traffic curve reveals the size of the business at hour resolution —
        exactly what was blocked from leaking in pagination when `count` was
        removed from it (ADR-32).
    """

    permission_classes = [CanViewReports]

    def get(self, request):
        start, end = _period(request)
        return Response(services.peak_hours(start, end))


class PerformanceReportAPI(APIView):
    """Employee and supplier performance together — the two ends of commercial activity."""

    permission_classes = [CanViewReports]

    def get(self, request):
        start, end = _period(request)
        return Response(
            {
                "start": str(start),
                "end": str(end),
                "employees": services.employee_leaderboard(start, end),
                "suppliers": services.supplier_purchases(start, end),
            }
        )
