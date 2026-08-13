"""
واجهات الطلبات وإتمام الشراء.

⚠️  كل queryset مُصفّى بالعميل — الهوية من التوكن لا من الرابط.
"""

from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from cart import services as cart_services
from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.permissions import IsAdminAccount
from customers import services as customer_services
from orders import serializers as s
from orders import services
from orders.models import Order


class MyOrderListAPI(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = s.OrderListSerializer

    def get_queryset(self):
        # ⚠️  خط الدفاع الأول — لا طلب لغير صاحبه يصل أصلًا
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
    إتمام الشراء.

    ⚠️  **إعادة تحقق كاملة قبل الإنشاء.**

        `create_from_cart` تعيد تسعير السلة وتفحص كل سطر: المنتج
        مفعّل · الوصول مسموح · المخزون كافٍ · الكوبون صالح. طلب
        بسعر قديم أو مخزون ناقص يُرفض هنا لا بعد الشحن.
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
        if data.get("address"):
            return dict(data["address"])

        from customers.models import CustomerAddress

        saved = CustomerAddress.objects.filter(pk=data["address_id"], customer=profile).first()
        if saved is None:
            # ⚠️  404 لغير الموجود وغير المملوك معًا
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        return {
            "recipient_name": saved.recipient_name,
            "phone": saved.phone,
            "governorate": saved.governorate,
            "city": saved.city,
            "street": saved.street,
            "building": saved.building,
            "landmark": saved.landmark,
        }

    def _charge(self, request, order, method):
        """
        ⚠️  `Idempotency-Key` يمنع الدفع المكرر.

            نقرة مزدوجة أو إعادة محاولة على شبكة ضعيفة يجب ألا
            تنتج عمليتي دفع.
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
            # الطلب أُنشئ؛ الدفع يُعاد من صفحة الطلب.
            # رفع الاستثناء هنا يتراجع بالطلب كله لأجل بوابة متعثّرة.
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
#  الأدمن
# ═══════════════════════════════════════════════════════════


class AdminOrderListAPI(generics.ListAPIView):
    permission_classes = [IsAdminAccount]
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
    permission_classes = [IsAdminAccount]
    serializer_class = s.AdminOrderSerializer
    queryset = Order.objects.select_related(
        "customer", "customer__user", "location"
    ).prefetch_related("lines", "status_history")


class AdminTransitionAPI(APIView):
    """
    نقل الطلب إلى حالة جديدة.

    ⚠️  الانتقال غير المسموح يُرفض بـ `409` من آلة الحالة —
        لا تُكرَّر القواعد هنا.
    """

    permission_classes = [IsAdminAccount]
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
    permission_classes = [IsAdminAccount]

    def post(self, request, pk):
        order = Order.objects.filter(pk=pk).first()
        if order is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        order = services.complete(order, actor=request.user)
        return Response(s.AdminOrderSerializer(order).data)
