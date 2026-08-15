"""
واجهات الموردين — للأدمن حصرًا.

⚠️  **لا نقطة واحدة للعميل.**

    أسعار الشراء هي هامش المتجر مكشوفًا. تسريبها يجعل أي عميل
    يعرف بكم اشترينا ما نبيعه له.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from suppliers import serializers as s
from suppliers import services
from suppliers.models import (
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
    SupplierLedgerEntry,
    SupplierProduct,
)
from suppliers.permissions import CanManagePurchasing


class SupplierListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [CanManagePurchasing]
    serializer_class = s.SupplierSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        # ⚠️  `order_by` صريح بعد `annotate`.
        #
        #     التجميع يُسقط ترتيب `Meta`، فيصير الترقيم غير مستقر:
        #     نفس الصف يظهر في صفحتين أو يسقط بينهما — وقاعدة
        #     البيانات لا تَعِد بترتيب ثابت بلا `ORDER BY`.
        queryset = Supplier.objects.annotate(
            offer_count=Count("offers", filter=Q(offers__is_active=True))
        ).order_by("name_ar")
        params = self.request.query_params

        if params.get("active") == "true":
            queryset = queryset.filter(is_active=True)
        if value := params.get("search"):
            queryset = queryset.filter(
                Q(name_ar__icontains=value) | Q(name_en__icontains=value) | Q(code__icontains=value)
            )
        return queryset


class SupplierDetailAPI(generics.RetrieveUpdateAPIView):
    permission_classes = [CanManagePurchasing]
    serializer_class = s.SupplierSerializer
    queryset = Supplier.objects.all()


class SupplierOfferListCreateAPI(generics.ListCreateAPIView):
    """عروض الموردين — **أساس الـ Marketplace**."""

    permission_classes = [CanManagePurchasing]
    serializer_class = s.SupplierProductSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = SupplierProduct.objects.select_related("supplier", "product")
        params = self.request.query_params

        if value := params.get("supplier"):
            queryset = queryset.filter(supplier_id=value)
        if value := params.get("product"):
            queryset = queryset.filter(product_id=value)
        return queryset


class SupplierOfferDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [CanManagePurchasing]
    serializer_class = s.SupplierProductSerializer
    queryset = SupplierProduct.objects.select_related("supplier", "product")


class ProductOffersAPI(APIView):
    """
    كل من يعرض منتجًا — مرتّبين بالسعر.

    ⚠️  هذه هي نقطة الـ Marketplace: اليوم تخدم قرار الشراء،
        وغدًا تخدم اختيار العميل بين بائعين بنفس البيانات.
    """

    permission_classes = [CanManagePurchasing]

    def get(self, request, pk):
        from catalog.models import Product

        product = get_object_or_404(Product, pk=pk)
        return Response(services.offers_for(product))


class ReorderSuggestionsAPI(APIView):
    """ما يجب شراؤه — أصناف تحت نقطة إعادة الطلب."""

    permission_classes = [CanManagePurchasing]

    def get(self, request):
        from inventory.models import StockLocation

        location = None
        if value := request.query_params.get("location"):
            location = get_object_or_404(StockLocation, pk=value)

        return Response(services.reorder_suggestions(location))


# ═══════════════════════════════════════════════════════════
#  أوامر الشراء
# ═══════════════════════════════════════════════════════════


class PurchaseOrderListAPI(generics.ListAPIView):
    permission_classes = [CanManagePurchasing]
    serializer_class = s.PurchaseOrderSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = PurchaseOrder.objects.select_related("supplier", "location").prefetch_related(
            "lines__product"
        )
        params = self.request.query_params

        if value := params.get("supplier"):
            queryset = queryset.filter(supplier_id=value)
        if value := params.get("status"):
            queryset = queryset.filter(status=value)
        return queryset


class PurchaseOrderDetailAPI(generics.RetrieveAPIView):
    permission_classes = [CanManagePurchasing]
    serializer_class = s.PurchaseOrderSerializer
    queryset = PurchaseOrder.objects.select_related("supplier", "location").prefetch_related(
        "lines__product"
    )


class CreatePurchaseOrderAPI(APIView):
    permission_classes = [CanManagePurchasing]
    serializer_class = s.CreatePurchaseOrderSerializer

    def post(self, request):
        from inventory.models import StockLocation

        serializer = s.CreatePurchaseOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        supplier = get_object_or_404(Supplier, pk=data["supplier"])
        location = get_object_or_404(StockLocation, pk=data["location"])

        order = services.create_order(
            supplier,
            location,
            data["lines"],
            expected_on=data.get("expected_on"),
            note=data.get("note", ""),
            actor=request.user,
        )

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.CREATE,
            object_repr=f"أمر شراء {order.number}",
            changes={"supplier": supplier.code, "subtotal": str(order.subtotal)},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(s.PurchaseOrderSerializer(order).data, status=status.HTTP_201_CREATED)


class SendPurchaseOrderAPI(APIView):
    permission_classes = [CanManagePurchasing]

    def post(self, request, pk):
        order = get_object_or_404(PurchaseOrder, pk=pk)
        services.send_order(order, actor=request.user)

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"إرسال أمر شراء {order.number}",
            changes={"subtotal": str(order.subtotal)},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(s.PurchaseOrderSerializer(order).data)


class ReceivePurchaseOrderAPI(APIView):
    """
    استلام كمية على سطر.

    ⚠️  الدفعة تدخل عبر `inventory` — بتكلفة **سطر الأمر** لا
        بسعر عرض المورّد اليوم.
    """

    permission_classes = [CanManagePurchasing]
    serializer_class = s.ReceiveLineSerializer

    def post(self, request, pk):
        serializer = s.ReceiveLineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        order = get_object_or_404(PurchaseOrder, pk=pk)
        line = PurchaseOrderLine.objects.filter(pk=data["line"], order=order).first()
        if line is None:
            # ⚠️  مُصفّى بالأمر: معرّف سطر أمر آخر كان يُستلَم من هنا
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        batch = services.receive_line(
            line,
            data["quantity"],
            expires_at=data.get("expires_at"),
            batch_number=data.get("batch_number", ""),
            actor=request.user,
        )

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.CREATE,
            object_repr=f"استلام {order.number} · {line.product.sku}",
            changes={"quantity": data["quantity"], "batch": batch.number},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        order.refresh_from_db()
        return Response(s.PurchaseOrderSerializer(order).data)


class CancelPurchaseOrderAPI(APIView):
    permission_classes = [CanManagePurchasing]
    serializer_class = s.CancelOrderSerializer

    def post(self, request, pk):
        serializer = s.CancelOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        order = get_object_or_404(PurchaseOrder, pk=pk)
        services.cancel_order(order, reason=serializer.validated_data["reason"], actor=request.user)
        return Response(s.PurchaseOrderSerializer(order).data)


# ═══════════════════════════════════════════════════════════
#  حساب المورّد
# ═══════════════════════════════════════════════════════════


class SupplierStatementAPI(APIView):
    permission_classes = [CanManagePurchasing]

    def get(self, request, pk):
        supplier = get_object_or_404(Supplier, pk=pk)

        today = timezone.localdate()
        raw_start = request.query_params.get("start")
        raw_end = request.query_params.get("end")

        start = date.fromisoformat(raw_start) if raw_start else today - timedelta(days=90)
        end = date.fromisoformat(raw_end) if raw_end else today

        result = services.statement(supplier, start, end)

        return Response(
            {
                "supplier": supplier.name_ar,
                "payable": str(services.payable_balance(supplier)),
                "start": str(result.start),
                "end": str(result.end),
                "opening_balance": str(result.opening_balance),
                "closing_balance": str(result.closing_balance),
                "entries": s.SupplierLedgerEntrySerializer(result.entries, many=True).data,
            }
        )


class SupplierPaymentAPI(APIView):
    permission_classes = [CanManagePurchasing]
    serializer_class = s.SupplierPaymentSerializer

    def post(self, request, pk):
        serializer = s.SupplierPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        supplier = get_object_or_404(Supplier, pk=pk)
        entry = services.record_payment(
            supplier,
            data["amount"],
            reference=data.get("reference", ""),
            note=data.get("note", ""),
            actor=request.user,
        )

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.CREATE,
            object_repr=f"سداد لمورّد {supplier.name_ar} · {entry.amount}",
            changes={"amount": str(entry.amount), "reference": entry.reference},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(s.SupplierLedgerEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class SupplierLedgerAPI(generics.ListAPIView):
    permission_classes = [CanManagePurchasing]
    serializer_class = s.SupplierLedgerEntrySerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        return SupplierLedgerEntry.objects.filter(supplier_id=self.kwargs["pk"]).select_related(
            "purchase_order"
        )
