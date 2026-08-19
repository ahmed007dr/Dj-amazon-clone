"""
Supplier endpoints — admin only.

⚠️  **Not one customer-facing endpoint.**

    Purchase prices are the store's margin laid bare. Leaking them lets any
    customer learn what we paid for what we sell them.
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
        # ⚠️  An explicit `order_by` after `annotate`.
        #
        #     Aggregation drops the `Meta` ordering, so pagination becomes unstable:
        #     the same row appears on two pages or falls between them — and the
        #     database promises no stable order without an `ORDER BY`.
        queryset = (
            services.annotated_suppliers()
            .annotate(offer_count=Count("offers", filter=Q(offers__is_active=True)))
            .order_by("name_ar")
        )
        params = self.request.query_params

        # ⚠️  An explicit `status` rather than `active=true` alone.
        #
        #     The old condition was `== "true"` only, so `active=false`
        #     **did nothing**: the admin asked for the disabled ones, saw everyone,
        #     and no error appeared.
        status_filter = params.get("status")
        if status_filter == "active":
            queryset = queryset.filter(is_active=True)
        elif status_filter == "inactive":
            queryset = queryset.filter(is_active=False)

        if params.get("has_debt") == "true":
            queryset = queryset.filter(payable__gt=0)
        if params.get("overdue") == "true":
            queryset = queryset.filter(has_overdue=True)

        if value := params.get("search"):
            queryset = queryset.filter(
                Q(name_ar__icontains=value) | Q(name_en__icontains=value) | Q(code__icontains=value)
            )
        return queryset


class SupplierDetailAPI(generics.RetrieveUpdateAPIView):
    permission_classes = [CanManagePurchasing]
    serializer_class = s.SupplierSerializer

    def get_queryset(self):
        # ⚠️  The same aggregation: the detail screen shows the balance and the
        #     total purchases, and computing them with a separate function makes the two
        #     figures differ between the list and the detail at the first edit to either.
        return services.annotated_suppliers()


class SupplierOfferListCreateAPI(generics.ListCreateAPIView):
    """Supplier offers — **the basis of the marketplace**."""

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
    Everyone offering a product — ordered by price.

    ⚠️  This is the marketplace endpoint: today it serves the purchasing
        decision, and tomorrow it serves the customer's choice between sellers
        on the same data.
    """

    permission_classes = [CanManagePurchasing]

    def get(self, request, pk):
        from catalog.models import Product

        product = get_object_or_404(Product, pk=pk)
        return Response(services.offers_for(product))


class ReorderSuggestionsAPI(APIView):
    """What needs buying — items below their reorder point."""

    permission_classes = [CanManagePurchasing]

    def get(self, request):
        from inventory.models import StockLocation

        location = None
        if value := request.query_params.get("location"):
            location = get_object_or_404(StockLocation, pk=value)

        return Response(services.reorder_suggestions(location))


# ═══════════════════════════════════════════════════════════
#  Purchase orders
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

        # ⚠️  Price differences are recorded on sending.
        #
        #     An unrecorded price edit makes "who lowered/raised it, and by how much?"
        #     a question with no answer after the first offer update.
        variances = services.price_variances(order)

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"إرسال أمر شراء {order.number}",
            changes={"subtotal": str(order.subtotal), "price_variances": variances},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(s.PurchaseOrderSerializer(order).data)


class ReceivePurchaseOrderAPI(APIView):
    """
    Receive a quantity against a line.

    ⚠️  The batch enters through `inventory` — at the **order line's** cost, not
        at the supplier's offer price today.
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
            # ⚠️  Filtered by the order: another order's line id used to be receivable here
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


class ReturnToSupplierAPI(APIView):
    """
    Return goods **that were actually received** to the supplier.

    ⚠️  It deducts from stock with a `RETURN_OUT` movement and creates a credit
        note — so it appears under "returns" on the statement.
    """

    permission_classes = [CanManagePurchasing]
    serializer_class = s.ReturnToSupplierSerializer

    def post(self, request, pk):
        serializer = s.ReturnToSupplierSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        order = get_object_or_404(PurchaseOrder, pk=pk)
        line = PurchaseOrderLine.objects.filter(pk=data["line"], order=order).first()
        if line is None:
            # ⚠️  Filtered by the order — as in receiving
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        entry = services.return_to_supplier(
            line, data["quantity"], reason=data["reason"], actor=request.user
        )

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.CREATE,
            object_repr=f"مرتجع لمورّد {order.number} · {line.product.sku}",
            changes={
                "quantity": data["quantity"],
                "amount": str(entry.amount),
                "reason": data["reason"],
            },
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
#  The supplier account
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
                # ⚠️  The aggregates are separate line items: a statement of movements alone
                #     forces the accountant to sort and add them up to learn the four figures.
                "invoiced": str(result.invoiced),
                "paid": str(result.paid),
                "returned": str(result.returned),
                "adjusted": str(result.adjusted),
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
