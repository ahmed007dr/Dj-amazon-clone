"""
Order and checkout endpoints.

⚠️  Every queryset is filtered by customer — the identity comes from the token, not the URL.
"""

from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from cart import services as cart_services
from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.permissions import CanManageOrders
from customers import services as customer_services
from orders import serializers as s
from orders import services
from orders.models import Order


class MyOrderListAPI(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = s.OrderListSerializer

    def get_queryset(self):
        # ⚠️  The first line of defence — no order belonging to someone else arrives at all
        profile = customer_services.get_or_create_profile(self.request.user)
        queryset = services.orders_for(profile)

        if status_filter := self.request.query_params.get("status"):
            queryset = queryset.filter(status=status_filter)
        return queryset


class MyOrderDetailAPI(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = s.OrderDetailSerializer
    lookup_field = "pk"

    def get_queryset(self):
        profile = customer_services.get_or_create_profile(self.request.user)
        return services.orders_for(profile).prefetch_related("lines", "status_history")


class CheckoutAPI(APIView):
    """
    Checkout.

    ⚠️  **A full re-validation before creation.**

        `create_from_cart` reprices the cart and checks every line: the product
        is active · access is permitted · stock is sufficient · the coupon is
        valid. An order at a stale price or with missing stock is refused here,
        not after shipping.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = s.CheckoutSerializer

    @transaction.atomic
    def post(self, request):
        serializer = s.CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        profile = customer_services.get_or_create_profile(request.user)
        cart = cart_services.get_active_cart(user=request.user)
        address = self._resolve_address(profile, data)

        order = services.create_from_cart(
            cart,
            customer=profile,
            address=address,
            shipping_method_code=data.get("shipping_method_code", ""),
            customer_note=data.get("customer_note", ""),
        )

        payment = self._charge(request, order, data["payment_method"])

        return Response(
            {
                "order": s.OrderDetailSerializer(order).data,
                "payment": {
                    "reference": payment.reference,
                    "status": payment.status,
                    "provider": payment.provider.code,
                }
                if payment
                else None,
            },
            status=status.HTTP_201_CREATED,
        )

    def _resolve_address(self, profile, data) -> dict:
        # ⚠️  In `services`, not here: credit checkout uses the same filtering,
        #     and two copies of it mean one gets forgotten at the first edit.
        return services.resolve_address(profile, data)

    def _charge(self, request, order, method):
        """
        ⚠️  `Idempotency-Key` prevents a duplicate payment.

            A double-click or a retry on a weak connection must not produce two
            payment operations.
        """
        from payments import services as payment_services

        try:
            return payment_services.charge(
                amount=order.grand_total,
                method=method,
                currency=order.currency,
                channel=order.channel,
                reference_type=services.REFERENCE_TYPE,
                reference_id=order.pk,
                customer=order.customer,
                idempotency_key=request.headers.get("Idempotency-Key", ""),
            )
        except BusinessError:
            # The order was created; payment is retried from the order page.
            # Raising here would roll the whole order back over a struggling gateway.
            return None


class CancelOrderAPI(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = s.CancelOrderSerializer

    def post(self, request, pk):
        serializer = s.CancelOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        profile = customer_services.get_or_create_profile(request.user)
        order = Order.objects.filter(pk=pk, customer=profile).first()
        if order is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        order = services.cancel(
            order, reason=serializer.validated_data["reason"], actor=request.user
        )
        return Response(s.OrderDetailSerializer(order).data)


# ═══════════════════════════════════════════════════════════
#  Admin
# ═══════════════════════════════════════════════════════════


class AdminOrderListAPI(generics.ListAPIView):
    permission_classes = [CanManageOrders]
    serializer_class = s.AdminOrderSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = Order.objects.select_related(
            "customer", "customer__user", "location"
        ).prefetch_related("lines")
        params = self.request.query_params

        for field in ("status", "payment_status", "channel"):
            if value := params.get(field):
                queryset = queryset.filter(**{field: value})

        if search := params.get("search"):
            from django.db.models import Q

            queryset = queryset.filter(
                Q(number__icontains=search)
                | Q(customer__user__email__icontains=search)
                | Q(recipient_phone__icontains=search)
            )

        return queryset.order_by("-created_at")


class AdminOrderDetailAPI(generics.RetrieveAPIView):
    permission_classes = [CanManageOrders]
    serializer_class = s.AdminOrderSerializer
    queryset = Order.objects.select_related(
        "customer", "customer__user", "location"
    ).prefetch_related("lines", "status_history")


class AdminTransitionAPI(APIView):
    """
    Move the order to a new status.

    ⚠️  A disallowed transition is refused with `409` by the state machine —
        the rules are not duplicated here.
    """

    permission_classes = [CanManageOrders]
    serializer_class = s.TransitionOrderSerializer

    def post(self, request, pk):
        serializer = s.TransitionOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = Order.objects.filter(pk=pk).first()
        if order is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        order = services.transition(
            order,
            serializer.validated_data["status"],
            note=serializer.validated_data.get("note", ""),
            actor=request.user,
        )
        return Response(s.AdminOrderSerializer(order).data)


class AdminCompleteOrderAPI(APIView):
    permission_classes = [CanManageOrders]

    def post(self, request, pk):
        order = Order.objects.filter(pk=pk).first()
        if order is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        order = services.complete(order, actor=request.user)
        return Response(s.AdminOrderSerializer(order).data)
