"""
Traffic measurement middleware.

⚠️  **Middleware, not an authentication layer** — unlike the registered user's heartbeat.

    An anonymous visitor never passes through an authentication layer at all, so
    measuring them there would have meant never measuring them — and they are
    **most of everyone browsing a store**.
"""

from __future__ import annotations

import logging

from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)

#: ⚠️  The store alone is measured, not the admin panel.
#
#     The question is "when is the store busy?", and a panel refreshing itself
#     every thirty seconds would have produced a flat peak lasting the admin's
#     whole shift, hiding the real customer peak underneath it.
EXCLUDED_PREFIXES = (
    "/api/v1/administration/",
    "/api/v1/reports/",
    "/api/v1/analytics/",
    "/admin/",
    "/static/",
    "/media/",
)

#: Anything not starting with this is not store usage (health checks · files · the root)
MEASURED_PREFIX = "/api/"


def client_ip(request) -> str | None:
    """
    ⚠️  `X-Forwarded-For` is read **from the left** and trusted only behind a proxy.

        Behind Nginx, `REMOTE_ADDR` is the proxy itself, so without this every
        visitor becomes a single fingerprint and "unique visitors" is forever 1.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR")


class TrafficMiddleware(MiddlewareMixin):
    """
    ⚠️  Measurement happens on the **response**, not the request.

        A rejected request (401 · 404 · rate limit) is not usage, and counting
        it makes a break-in attempt look like a browsing peak.

    ⚠️  And it never drops the response, however it fails.

        Measurement that stops a product page loading is a thousand times worse
        than measurement with a gap in it.
    """

    def process_response(self, request, response):
        try:
            self._record(request, response)
        except Exception:
            # ⚠️  Logged, never raised: measurement that stops a product page loading
            #     is a thousand times worse than measurement with a gap in it.
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
            # ⚠️  The presence of the header, not the user's identity: authentication
            #     happens in the DRF layer after all middleware, so `request.user` here
            #     is always anonymous with JWT (the same reason as `LanguageMiddleware`).
            authenticated=bool(request.META.get("HTTP_AUTHORIZATION")),
        )
