"""
واجهات حركة الاستخدام — **قراءة فقط**.

⚠️  الصلاحية مقسومة عمدًا على مستويين:

    «كم متصلًا الآن؟» رقم تشغيلي يراه من يدير اللوحة.
    أما منحنى الحركة بدقّة الساعة فيكشف حجم النشاط — وهو ما مُنع
    تسريبه حين حُذف `count` من الترقيم (ADR-32). ولذلك يتبع صلاحية
    التقارير لا مجرد دخول اللوحة.
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
    ⚠️  الافتراضي آخر ٣٠ يومًا لا الشهر الجاري.

        سؤال الضغط أسبوعي الطابع؛ وفي أول يوم من الشهر كان الشهر
        الجاري يعني «يوم واحد» — خريطة حرارية بعمود واحد.
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
    نبض الاستخدام الآن — يُستدعى كل ٣٠ ثانية من اللوحة.

    ⚠️  خفيفة عمدًا: قراءتان من الكاش واستعلام واحد.

        نقطة تُنادى كل نصف دقيقة من كل لوحة مفتوحة لا يجوز أن تلمس
        جدولًا كبيرًا — وإلا صارت مراقبة الضغط هي الضغط.
    """

    permission_classes = [IsAdminAccount]

    def get(self, request):
        online = account_services.online_user_ids()

        return Response(
            {
                "window_minutes": int(
                    account_services.PRESENCE_WINDOW.total_seconds() // 60
                ),
                # ⚠️  ثلاثة أرقام لا رقم واحد: «١٢ متصفّحًا مجهولًا»
                #     و«٣ مسجَّلين» قراران مختلفان، ومجموعهما يخفيهما.
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
