"""
وسيط قياس الحركة.

⚠️  **وسيطٌ لا طبقة مصادقة** — بخلاف نبضة المستخدم المسجَّل.

    الزائر المجهول لا يمرّ بطبقة مصادقة إطلاقًا، فقياسه هناك كان
    يعني ألا يُقاس أبدًا — وهو **معظم من يتصفّح متجرًا**.
"""

from __future__ import annotations

import logging

from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

#: ⚠️  يُقاس المتجر وحده لا لوحة الإدارة.
#
#     السؤال «متى الضغط على المتجر؟»، ولوحة تُحدِّث نفسها كل ثلاثين
#     ثانية كانت ستُنتج ذروةً ثابتة طوال دوام الأدمن تخفي ذروة
#     العملاء الحقيقية تحتها.
EXCLUDED_PREFIXES = (
    "/api/v1/administration/",
    "/api/v1/reports/",
    "/api/v1/analytics/",
    "/admin/",
    "/static/",
    "/media/",
)

#: ما لا يبدأ بهذا ليس استخدامًا للمتجر (فحوص صحة · ملفات · جذر)
MEASURED_PREFIX = "/api/"


def client_ip(request) -> str | None:
    """
    ⚠️  `X-Forwarded-For` يُقرأ **من اليسار** ويُثق به خلف وكيل فقط.

        خلف Nginx يكون `REMOTE_ADDR` هو الوكيل نفسه، فبدونه يصير
        كل الزوار بصمةً واحدة ويصير «الزوار الفريدون» دائمًا ١.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR")


class TrafficMiddleware(MiddlewareMixin):
    """
    ⚠️  القياس على **الاستجابة** لا الطلب.

        الطلب المرفوض (٤٠١ · ٤٠٤ · حدّ معدّل) ليس استخدامًا، وعدّه
        يجعل محاولة اقتحام تبدو ذروة تصفّح.

    ⚠️  ولا يُسقِط الاستجابة أبدًا مهما فشل.

        قياسٌ يمنع صفحة منتج من الوصول أسوأ ألف مرة من قياس ناقص.
    """

    def process_response(self, request, response):
        try:
            self._record(request, response)
        except Exception:
            # ⚠️  يُسجَّل ولا يُرفَع: قياسٌ يمنع صفحة منتج من الوصول
            #     أسوأ ألف مرة من قياس ناقص.
            logger.exception("فشل قياس الحركة")
        return response

    def _record(self, request, response) -> None:
        path = request.path

        if not path.startswith(MEASURED_PREFIX):
            return
        if path.startswith(EXCLUDED_PREFIXES):
            return
        if response.status_code >= 400:
            return

        from analytics import services

        services.record_visit(
            ip=client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
            # ⚠️  وجود الترويسة لا هوية المستخدم: المصادقة تقع في
            #     طبقة DRF بعد كل الوسائط، فـ`request.user` هنا
            #     مجهول دائمًا مع JWT (نفس سبب `LanguageMiddleware`).
            authenticated=bool(request.META.get("HTTP_AUTHORIZATION")),
        )
