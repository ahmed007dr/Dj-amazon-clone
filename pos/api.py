"""
واجهات نقطة البيع.

⚠️  الكاشير يعمل على وردية **مفتوحة خاصة به**.

    كل نقطة أدناه تستخرج الوردية من المستخدم لا من الطلب — فلا
    يستطيع كاشير تسجيل بيعة على وردية زميله بتمرير معرّف.
"""

from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Product, ProductVariant
from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from core.permissions import IsAdminAccount
from pos import serializers as s
from pos import services
from pos.models import POSSession, Register, SessionStatus
from pos.permissions import CanOperatePOS, CanRefund


class SessionMixin:
    """
    ⚠️  الوردية تُستخرج من **المستخدم** لا من مُعامل الطلب.

        قبولها كمعرّف يعني أن كاشيرًا يسجّل بيعة على وردية زميله
        بتغيير رقم — فتُنسب النقدية للشخص الخطأ ولا توازن أي تسوية.
    """

    def current_session(self) -> POSSession:
        session = POSSession.objects.filter(
            cashier=self.request.user, status=SessionStatus.OPEN
        ).select_related("register", "register__location").first()

        if session is None:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail=_("لا توجد وردية مفتوحة — افتح وردية أولًا"),
                status_code=409,
            )
        return session


# ═══════════════════════════════════════════════════════════
#  الأجهزة
# ═══════════════════════════════════════════════════════════


class RegisterListAPI(generics.ListAPIView):
    permission_classes = [CanOperatePOS]
    serializer_class = s.RegisterSerializer
    pagination_class = None

    def get_queryset(self):
        return Register.objects.filter(is_active=True).select_related("location")


class AdminRegisterListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [IsAdminAccount]
    serializer_class = s.RegisterSerializer
    pagination_class = None
    queryset = Register.objects.select_related("location")


# ═══════════════════════════════════════════════════════════
#  الوردية
# ═══════════════════════════════════════════════════════════


class MySessionAPI(SessionMixin, APIView):
    """الوردية المفتوحة للكاشير الحالي — أو `null`."""

    permission_classes = [CanOperatePOS]
    serializer_class = s.SessionSerializer

    def get(self, request):
        session = POSSession.objects.filter(
            cashier=request.user, status=SessionStatus.OPEN
        ).select_related("register").first()

        # ⚠️  `null` لا `404`: غياب وردية حالة عادية في بداية اليوم
        if session is None:
            return Response(None)

        return Response(s.SessionSerializer(session).data)


class OpenSessionAPI(APIView):
    permission_classes = [CanOperatePOS]
    serializer_class = s.OpenSessionSerializer

    def post(self, request):
        serializer = s.OpenSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        register = get_object_or_404(Register, pk=data["register"])
        session = services.open_session(
            register, request.user, opening_float=data["opening_float"]
        )

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.CREATE,
            object_repr=f"وردية {session.number}",
            changes={"register": register.code, "opening_float": str(session.opening_float)},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(s.SessionSerializer(session).data, status=status.HTTP_201_CREATED)


class CloseSessionAPI(SessionMixin, APIView):
    """
    إغلاق الوردية بتسوية نقدية.

    ⚠️  الفرق فوق الحد يوجب تفسيرًا — يفرضه `services.close_session`.
    """

    permission_classes = [CanOperatePOS]
    serializer_class = s.CloseSessionSerializer

    def post(self, request):
        serializer = s.CloseSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        session = services.close_session(
            self.current_session(),
            counted_cash=data["counted_cash"],
            closed_by=request.user,
            variance_note=data.get("variance_note", ""),
        )

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"وردية {session.number}",
            changes={
                "counted": str(session.counted_cash),
                "expected": str(session.expected_cash),
                "variance": str(session.variance),
            },
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(s.SessionSerializer(session).data)


class SessionCashAPI(SessionMixin, APIView):
    """إيداع أو سحب من الدرج."""

    permission_classes = [CanOperatePOS]
    serializer_class = s.CashMovementInputSerializer

    def get(self, request):
        session = self.current_session()
        return Response(
            s.CashMovementSerializer(session.cash_movements.all(), many=True).data
        )

    def post(self, request):
        serializer = s.CashMovementInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        movement = services.record_cash(
            self.current_session(),
            kind=data["kind"],
            amount=data["amount"],
            reason=data["reason"],
            performed_by=request.user,
        )

        return Response(
            s.CashMovementSerializer(movement).data, status=status.HTTP_201_CREATED
        )


# ═══════════════════════════════════════════════════════════
#  البيع
# ═══════════════════════════════════════════════════════════


class CheckoutAPI(SessionMixin, APIView):
    """
    إتمام بيعة.

    ⚠️  المنتجات تُحمَّل **باستعلام واحد** لا واحد لكل سطر.

        بيعة بعشرين صنفًا كانت ستنتج عشرين استعلامًا بينما العميل
        واقف — وهو أسوأ مكان لبطء يمكن تفاديه.
    """

    permission_classes = [CanOperatePOS]
    serializer_class = s.CheckoutSerializer

    def post(self, request):
        serializer = s.CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        session = self.current_session()

        products = Product.objects.in_bulk(
            [entry["product"] for entry in data["lines"]]
        )
        variant_ids = [entry.get("variant") for entry in data["lines"] if entry.get("variant")]
        variants = ProductVariant.objects.in_bulk(variant_ids) if variant_ids else {}

        lines = []
        for entry in data["lines"]:
            product = products.get(entry["product"])
            if product is None:
                raise BusinessError(
                    ErrorCode.NOT_FOUND,
                    detail=_("منتج غير موجود: {id}").format(id=entry["product"]),
                    status_code=404,
                )
            lines.append(
                services.SaleLine(
                    product=product,
                    quantity=entry["quantity"],
                    variant=variants.get(entry.get("variant")) if entry.get("variant") else None,
                )
            )

        payments = [
            services.SplitPayment(method=entry["method"], amount=entry["amount"])
            for entry in data["payments"]
        ]

        customer = None
        if data.get("customer"):
            from customers.models import CustomerProfile

            customer = get_object_or_404(CustomerProfile, pk=data["customer"])

        result = services.checkout(
            session,
            lines,
            payments,
            customer=customer,
            discount_percent=data["discount_percent"],
            note=data.get("note", ""),
        )

        from orders.serializers import OrderDetailSerializer

        return Response(
            {
                "order": OrderDetailSerializer(result.order).data,
                "payments": [
                    {"reference": payment.reference, "status": payment.status}
                    for payment in result.payments
                ],
            },
            status=status.HTTP_201_CREATED,
        )


class POSRefundAPI(SessionMixin, APIView):
    """
    ⚠️  الاسترداد يحتاج اعتماد مدير — قاعدة العمل ١١ (توصية مطبَّقة).
    """

    permission_classes = [CanOperatePOS, CanRefund]
    serializer_class = s.RefundSerializer

    def post(self, request):
        serializer = s.RefundSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        from orders.models import Order

        order = get_object_or_404(Order, pk=data["order"])

        result = services.refund_sale(
            self.current_session(),
            order,
            reason=data["reason"],
            cash_amount=data.get("cash_amount"),
            performed_by=request.user,
        )

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"استرداد نقطة بيع {order.number}",
            changes={"reason": data["reason"], "cash": str(data.get("cash_amount") or 0)},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        from orders.serializers import OrderDetailSerializer

        return Response({"order": OrderDetailSerializer(result.order).data})


# ═══════════════════════════════════════════════════════════
#  الأدمن
# ═══════════════════════════════════════════════════════════


class AdminSessionListAPI(generics.ListAPIView):
    """كل الورديات — لمراجعة الفروق النقدية."""

    permission_classes = [IsAdminAccount]
    serializer_class = s.SessionSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = POSSession.objects.select_related("register", "cashier")
        params = self.request.query_params

        if register := params.get("register"):
            queryset = queryset.filter(register_id=register)
        if session_status := params.get("status"):
            queryset = queryset.filter(status=session_status)
        if cashier := params.get("cashier"):
            queryset = queryset.filter(cashier_id=cashier)

        return queryset


class AdminSessionDetailAPI(generics.RetrieveAPIView):
    permission_classes = [IsAdminAccount]
    serializer_class = s.SessionSerializer
    queryset = POSSession.objects.select_related("register", "cashier", "closed_by")
