"""
واجهات التقارير — **قراءة فقط**.

⚠️  لا نقطة كتابة واحدة هنا. التقرير يعكس ما وقع، ولا يغيّره.

⚠️  والصلاحية **صريحة**: التقارير تكشف المبيعات والأرباح وأداء
    كل موظف بالاسم. جعلها تابعة لدخول اللوحة يفتحها لمن يفتحها
    لسبب آخر تمامًا.
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
    """اللوحة الجامعة — المبيعات والربح والمخزون معًا."""

    permission_classes = [CanViewReports]

    def get(self, request):
        start, end = _period(request)
        return Response(services.overview(start, end))


def _positive_int(request, name: str, default: int, ceiling: int) -> int:
    """
    ⚠️  الحدّ **مسقوف**.

        `?limit=100000` على جدول سطور الطلبات استعلامٌ يشلّ القاعدة،
        ولا شاشة تعرض مئة ألف صف. السقف يجعل النقطة غير قابلة
        للاستخدام كأداة إنهاك.
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
    أوقات الضغط — خريطة ٧×٢٤.

    ⚠️  تحت **نفس صلاحية التقارير** لا مجرد دخول اللوحة.

        منحنى الحركة يكشف حجم النشاط بدقة الساعة — وهو ما مُنع
        تسريبه في الترقيم حين حُذف `count` منه (ADR-32).
    """

    permission_classes = [CanViewReports]

    def get(self, request):
        start, end = _period(request)
        return Response(services.peak_hours(start, end))


class PerformanceReportAPI(APIView):
    """أداء الموظفين والموردين معًا — طرفا الحركة التجارية."""

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
