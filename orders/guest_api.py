"""
Guest order endpoints — everything an anonymous visitor can do with an order.

    POST /orders/guest-checkout/            place a cash-on-delivery order
    GET  /orders/guest/<token>/             the tracking page's data
    POST /orders/guest/<token>/cancel/      cancel while still PENDING
    POST /orders/guest/lookup/              "find my order" (emails the link)

⚠️  `authentication_classes = []` on every view here.

    These endpoints are for people who are not signed in. With the default JWT
    authentication a *stale* bearer token (a member whose session lapsed, now
    shopping as a guest) turns an anonymous-friendly endpoint into a 401 before
    the permission check even runs — the visitor sees "session expired" on a
    page that never needed a session. And a signed-in member who lands here is
    simply treated as the guest they are acting as: the order is not attached to
    their account (claiming happens only after email verification).

⚠️  The tracking token is a bearer credential in a URL: responses carry
    `Cache-Control: no-store` so a shared proxy or the browser never keeps one.
"""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from cart import services as cart_services
from cart.api import GUEST_HEADER
from core.errors import BusinessError, ErrorCode
from orders import guest
from orders import guest_serializers as s
from orders.throttles import GuestCheckoutThrottle, GuestLookupThrottle, GuestTokenThrottle

logger = logging.getLogger(__name__)

#: What "find my order" always answers — matched or not (no enumeration).
LOOKUP_DETAIL = (
    "إن طابقت البيانات طلبًا لدينا فسنرسل رابط التتبع إلى البريد المسجّل عليه خلال دقائق."
)


class _GuestView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        response["Referrer-Policy"] = "no-referrer"
        return response


class GuestCheckoutAPI(_GuestView):
    """
    Place an order without an account.

    ⚠️  The cart is the one named by `X-Cart-Session`. There is no way to name a
        member's cart from here: this view never reads `request.user`.
    """

    throttle_classes = [GuestCheckoutThrottle]
    serializer_class = s.GuestCheckoutSerializer

    def post(self, request):
        serializer = s.GuestCheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)

        # ── The honeypot ──
        # ⚠️  Answered with a plain validation error, not a fake success. A
        #     browser extension that autofills every field would otherwise leave
        #     a real customer believing an order exists that was never created;
        #     a bot does not read the response either way.
        if data.pop("website", ""):
            logger.warning("طلب زائر مرفوض: حقل الفخ مُعبّأ")
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR, detail="تعذّر إرسال الطلب — حدّث الصفحة وحاول مجددًا"
            )

        if not guest.verify_captcha(data.pop("captcha_token", ""), request):
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR, detail="فشل التحقق الأمني — حاول مجددًا"
            )

        session_key = cart_services.normalise_session_key(request.META.get(GUEST_HEADER, ""))
        cart = cart_services.get_active_cart(session_key=session_key)

        idempotency_key = (
            request.headers.get("Idempotency-Key", "").strip()
            or data.pop("idempotency_key", "")
        )
        data.pop("idempotency_key", None)
        data.pop("payment_method", None)  # COD is not a choice

        result = guest.place_order(
            cart, session_key=session_key, form=data, idempotency_key=idempotency_key
        )
        return Response(
            s.placed_payload(result),
            status=status.HTTP_200_OK if result.replayed else status.HTTP_201_CREATED,
        )


class GuestOrderDetailAPI(_GuestView):
    throttle_classes = [GuestTokenThrottle]

    def get(self, request, token):
        order = guest.read_token(token)
        return Response(s.GuestOrderSerializer(order).data)


class GuestOrderCancelAPI(_GuestView):
    throttle_classes = [GuestTokenThrottle]
    serializer_class = s.GuestCancelSerializer

    def post(self, request, token):
        serializer = s.GuestCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        guest.cancel_with_token(token, serializer.validated_data.get("reason", ""))

        # Re-read so the response reflects the cancelled state with its history
        return Response(s.GuestOrderSerializer(guest.read_token(token)).data)


class GuestOrderLookupAPI(_GuestView):
    """
    "Find my order" — order number + phone → the link, by email.

    ⚠️  **Always `200` with the same sentence.**

        A different answer for "no such order" is an oracle that tells a stranger
        which numbers exist and which phones belong to them. The only thing a
        match changes is an email that lands in the real buyer's inbox.
    """

    throttle_classes = [GuestLookupThrottle]
    serializer_class = s.GuestLookupSerializer

    def post(self, request):
        serializer = s.GuestLookupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            guest.request_link(
                serializer.validated_data["order_number"], serializer.validated_data["phone"]
            )
        except Exception:
            # Even a failure here answers the same: an error would be a signal.
            logger.exception("فشل بحث طلب الزائر")

        return Response({"detail": LOOKUP_DETAIL})
