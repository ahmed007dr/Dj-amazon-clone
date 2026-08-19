"""
Usage traffic endpoints — **read-only**.

⚠️  The permission is split across two levels on purpose:

    "How many are online now?" is an operational number visible to whoever runs
    the panel. But an hour-resolution traffic curve reveals the size of the
    business — precisely what was blocked from leaking when `count` was removed
    from pagination (ADR-32). It therefore follows the reporting permission
    rather than mere panel access.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts import services as account_services
from analytics import services
from core.errors import BusinessError, ErrorCode
from core.permissions import CanViewReports, IsAdminAccount


def _period(request) -> tuple[date, date]:
    """
    ⚠️  The default is the last 30 days, not the current month.

        The load question is weekly in character; and on the first day of the
        month "the current month" meant "one day" — a heatmap with a single column.
    """
    today = timezone.localdate()

    raw_start = request.query_params.get("start")
    raw_end = request.query_params.get("end")

    try:
        start = date.fromisoformat(raw_start) if raw_start else today - timedelta(days=29)
        end = date.fromisoformat(raw_end) if raw_end else today
    except ValueError as exc:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="تاريخ غير صالح") from exc

    if start > end:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="بداية الفترة بعد نهايتها")

    return start, end


class LiveAPI(APIView):
    """
    The live usage pulse — called every 30 seconds from the panel.

    ⚠️  Deliberately light: two cache reads and one query.

        An endpoint called every half minute from every open panel must not
        touch a large table — or monitoring the load becomes the load.
    """

    permission_classes = [IsAdminAccount]

    def get(self, request):
        online = account_services.online_user_ids()

        return Response(
            {
                "window_minutes": int(
                    account_services.PRESENCE_WINDOW.total_seconds() // 60
                ),
                # ⚠️  Three numbers, not one: "12 anonymous browsers" and
                #     "3 registered" are two different decisions, and their sum hides both.
                "users_online": len(online),
                "guests_online": services.guests_online(),
                "total_online": len(online) + services.guests_online(),
            }
        )


class TrafficAPI(APIView):
    permission_classes = [CanViewReports]

    def get(self, request):
        start, end = _period(request)
        return Response(services.traffic_summary(start, end))


class TrafficPeakHoursAPI(APIView):
    permission_classes = [CanViewReports]

    def get(self, request):
        start, end = _period(request)
        return Response(services.traffic_peak_hours(start, end))
