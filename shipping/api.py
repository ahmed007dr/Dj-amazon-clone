"""واجهات الشحن."""

from decimal import Decimal, InvalidOperation

from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.permissions import IsAdminAccount
from shipping import serializers as s
from shipping import services
from shipping.models import Shipment, ShippingMethod


class ShippingQuoteAPI(APIView):
    """عروض الشحن المتاحة لهذه المحافظة — تُحسب من المصدر."""

    permission_classes = [AllowAny]

    def get(self, request):
        governorate = request.query_params.get("governorate", "").strip()
        if not governorate:
            raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="المحافظة مطلوبة")

        try:
            subtotal = Decimal(request.query_params.get("subtotal", "0"))
        except (TypeError, InvalidOperation):
            subtotal = Decimal("0")

        quotes = services.quote(governorate, subtotal)
        return Response(s.ShippingQuoteSerializer(quotes, many=True).data)


class ShippingMethodListAPI(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = s.ShippingMethodSerializer
    pagination_class = None
    queryset = ShippingMethod.objects.filter(is_active=True)


class TrackShipmentAPI(APIView):
    """
    تتبع بالرقم.

    ⚠️  عام عمدًا — العميل يشارك الرقم مع من يستلم عنه.

        ولهذا بالضبط لا تكشف الاستجابة العنوان الكامل ولا الهاتف:
        رقم يُشارَك يجب ألا يحمل بيانات شخصية.
    """

    permission_classes = [AllowAny]

    def get(self, request, number):
        shipment = (
            Shipment.objects.filter(number=number)
            .select_related("method")
            .prefetch_related("events")
            .first()
        )
        if shipment is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)
        return Response(s.ShipmentSerializer(shipment).data)


class AdminShipmentListAPI(generics.ListAPIView):
    permission_classes = [IsAdminAccount]
    serializer_class = s.ShipmentSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = Shipment.objects.select_related("method").prefetch_related("events")
        if status_filter := self.request.query_params.get("status"):
            queryset = queryset.filter(status=status_filter)
        return queryset


class AdminTransitionShipmentAPI(APIView):
    """
    ⚠️  الانتقال غير المسموح يُرفض من آلة الحالة بـ `409`.

        شحنة «سُلّمت» لا تعود إلى «قيد التجهيز» — وإلا فسد كل
        تقرير تسليم.
    """

    permission_classes = [IsAdminAccount]
    serializer_class = s.TransitionShipmentSerializer

    def post(self, request, pk):
        serializer = s.TransitionShipmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        shipment = Shipment.objects.filter(pk=pk).first()
        if shipment is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        shipment = services.transition(
            shipment,
            data["status"],
            note=data.get("note", ""),
            location=data.get("location", ""),
            tracking_number=data.get("tracking_number", ""),
        )
        return Response(s.ShipmentSerializer(shipment).data)
