"""
Inventory endpoints.

⚠️  All writes go through `services` — no direct edit of any model.
    The endpoints here validate the inputs and call, nothing more.
"""

from django.db.models import Case, Count, F, IntegerField, Q, When
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Product, ProductVariant
from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from core.permissions import CanManageInventory
from inventory import serializers as s
from inventory import services
from inventory.models import (
    Batch,
    Stock,
    StockAlert,
    StockCount,
    StockCountLine,
    StockLocation,
    StockMovement,
    StockReservation,
)


def _resolve(model, value, default=None):
    return get_object_or_404(model, pk=value) if value else default


# ═══════════════════════════════════════════════════════════
#  Public — availability only
# ═══════════════════════════════════════════════════════════


class AvailabilityAPI(APIView):
    """
    Availability for a set of products.

    ⚠️  A single aggregated query however many products there are — this is the
        function that keeps N+1 out of the catalogue lists.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        raw = request.query_params.get("products", "")
        product_ids = [value for value in raw.split(",") if value.strip()]

        if not product_ids:
            return Response({})
        if len(product_ids) > 100:
            product_ids = product_ids[:100]

        result = services.availability_for(product_ids)
        return Response(
            {
                product_id: s.AvailabilitySerializer(entry).data
                for product_id, entry in result.items()
            }
        )


# ═══════════════════════════════════════════════════════════
#  Admin — reading
# ═══════════════════════════════════════════════════════════


class StockLocationListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [CanManageInventory]
    serializer_class = s.StockLocationSerializer
    queryset = StockLocation.objects.all()
    pagination_class = None


class StockLocationDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [CanManageInventory]
    serializer_class = s.StockLocationSerializer
    queryset = StockLocation.objects.all()


class StockListAPI(generics.ListAPIView):
    permission_classes = [CanManageInventory]
    serializer_class = s.StockSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = Stock.objects.select_related("product", "location", "variant")
        params = self.request.query_params

        if location := params.get("location"):
            queryset = queryset.filter(location_id=location)
        if product := params.get("product"):
            queryset = queryset.filter(product_id=product)
        if search := params.get("search"):
            queryset = queryset.filter(product__sku__icontains=search)

        # The computed filters are applied in Python — `available` is not a column
        status_filter = params.get("status")
        if status_filter in ("low", "critical", "out"):
            matching = [
                stock.pk
                for stock in queryset
                if (status_filter == "out" and stock.available == 0)
                or (status_filter == "critical" and stock.is_critical)
                or (status_filter == "low" and stock.needs_reorder)
            ]
            queryset = queryset.filter(pk__in=matching)

        return queryset.order_by("product__sku")


class StockDetailAPI(generics.RetrieveUpdateAPIView):
    """Editing the alert thresholds only — quantities are never edited by hand."""

    permission_classes = [CanManageInventory]
    serializer_class = s.StockSerializer
    queryset = Stock.objects.select_related("product", "location")


class BatchListAPI(generics.ListAPIView):
    permission_classes = [CanManageInventory]
    serializer_class = s.BatchSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = Batch.objects.select_related("product", "location")
        params = self.request.query_params

        if product := params.get("product"):
            queryset = queryset.filter(product_id=product)
        if location := params.get("location"):
            queryset = queryset.filter(location_id=location)
        if params.get("status") == "expiring":
            from datetime import timedelta

            from django.utils import timezone

            queryset = queryset.filter(
                expires_at__lte=timezone.localdate() + timedelta(days=90),
                expires_at__gte=timezone.localdate(),
                quantity_remaining__gt=0,
            )
        elif params.get("status") == "expired":
            from django.utils import timezone

            queryset = queryset.filter(expires_at__lt=timezone.localdate())
        elif params.get("status") == "active":
            queryset = queryset.filter(quantity_remaining__gt=0, is_quarantined=False)

        # FEFO — nearest to expiry first
        return queryset


class StockMovementListAPI(generics.ListAPIView):
    """
    The movement log.

    ⚠️  Read-only — the log is append-only, and corrections go through an
        offsetting movement.
    """

    permission_classes = [CanManageInventory]
    serializer_class = s.StockMovementSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = StockMovement.objects.select_related(
            "product", "location", "batch", "performed_by"
        )
        params = self.request.query_params

        if product := params.get("product"):
            queryset = queryset.filter(product_id=product)
        if location := params.get("location"):
            queryset = queryset.filter(location_id=location)
        if movement_type := params.get("type"):
            queryset = queryset.filter(movement_type=movement_type)
        if batch := params.get("batch"):
            queryset = queryset.filter(batch_id=batch)

        return queryset


class StockAlertListAPI(generics.ListAPIView):
    permission_classes = [CanManageInventory]
    serializer_class = s.StockAlertSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = StockAlert.objects.select_related("product", "location", "batch")

        if self.request.query_params.get("resolved") != "true":
            queryset = queryset.filter(is_resolved=False)
        if alert_type := self.request.query_params.get("type"):
            queryset = queryset.filter(alert_type=alert_type)

        return queryset


class ReservationListAPI(generics.ListAPIView):
    permission_classes = [CanManageInventory]
    serializer_class = s.StockReservationSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = StockReservation.objects.select_related("product", "location")
        if status_filter := self.request.query_params.get("status"):
            queryset = queryset.filter(status=status_filter)
        return queryset


# ═══════════════════════════════════════════════════════════
#  Admin — commands
# ═══════════════════════════════════════════════════════════


class ReceiveStockAPI(APIView):
    permission_classes = [CanManageInventory]
    serializer_class = s.ReceiveStockSerializer

    def post(self, request):
        serializer = s.ReceiveStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        batch = services.receive(
            _resolve(Product, data["product"]),
            data["quantity"],
            data["unit_cost"],
            location=_resolve(StockLocation, data.get("location")),
            variant=_resolve(ProductVariant, data.get("variant")),
            expires_at=data.get("expires_at"),
            supplier_batch_number=data.get("supplier_batch_number", ""),
            performed_by=request.user,
        )
        return Response(s.BatchSerializer(batch).data, status=201)


class AdjustStockAPI(APIView):
    permission_classes = [CanManageInventory]
    serializer_class = s.AdjustStockSerializer

    def post(self, request):
        serializer = s.AdjustStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        movement = services.adjust(
            _resolve(Product, data["product"]),
            data["quantity"],
            location=_resolve(StockLocation, data.get("location")),
            variant=_resolve(ProductVariant, data.get("variant")),
            reason=data["reason"],
            performed_by=request.user,
        )
        return Response(s.StockMovementSerializer(movement).data, status=201)


class TransferStockAPI(APIView):
    permission_classes = [CanManageInventory]
    serializer_class = s.TransferStockSerializer

    def post(self, request):
        serializer = s.TransferStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        out_movement, in_movement = services.transfer(
            _resolve(Product, data["product"]),
            data["quantity"],
            from_location=_resolve(StockLocation, data["from_location"]),
            to_location=_resolve(StockLocation, data["to_location"]),
            variant=_resolve(ProductVariant, data.get("variant")),
            performed_by=request.user,
        )
        return Response(
            {
                "out": s.StockMovementSerializer(out_movement).data,
                "in": s.StockMovementSerializer(in_movement).data,
            },
            status=201,
        )


class MarkDamagedAPI(APIView):
    permission_classes = [CanManageInventory]
    serializer_class = s.MarkDamagedSerializer

    def post(self, request):
        serializer = s.MarkDamagedSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        movement = services.mark_damaged(
            _resolve(Product, data["product"]),
            data["quantity"],
            location=_resolve(StockLocation, data.get("location")),
            variant=_resolve(ProductVariant, data.get("variant")),
            reason=data["reason"],
            performed_by=request.user,
        )
        return Response(s.StockMovementSerializer(movement).data, status=201)


class RunMaintenanceAPI(APIView):
    """
    Manual execution of the periodic tasks.

    They run automatically on a schedule; this endpoint is for running them on demand.
    """

    permission_classes = [CanManageInventory]

    def post(self, request):
        return Response(
            {
                "released_reservations": services.release_expired_reservations(),
                "quarantined_batches": services.quarantine_expired_batches(),
                "expiry_alerts": services.check_expiring_batches(),
            }
        )


# ═══════════════════════════════════════════════════════════
#  Stock counting
# ═══════════════════════════════════════════════════════════


class StockCountListAPI(generics.ListAPIView):
    permission_classes = [CanManageInventory]
    serializer_class = s.StockCountSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = StockCount.objects.select_related("location").annotate(
            line_count=Count("lines", distinct=True),
            # ⚠️  Count the discrepancies in the query, not in Python.
            #
            #     Dragging every line of every session in to count them makes the
            #     list load thousands of rows to display one number per row.
            variance_count=Count(
                Case(
                    When(~Q(lines__counted_quantity=F("lines__expected_quantity")), then=1),
                    output_field=IntegerField(),
                ),
                distinct=True,
            ),
        )

        params = self.request.query_params
        if location := params.get("location"):
            queryset = queryset.filter(location_id=location)
        if status_filter := params.get("status"):
            queryset = queryset.filter(status=status_filter)

        return queryset


class StockCountDetailAPI(generics.RetrieveAPIView):
    permission_classes = [CanManageInventory]
    serializer_class = s.StockCountDetailSerializer
    queryset = StockCount.objects.select_related("location").prefetch_related(
        "lines__product", "lines__variant"
    )


class OpenStockCountAPI(APIView):
    """
    Open a stock count session **and take the balance snapshot immediately**.

    ⚠️  Both steps together, not separately.

        A session opened with no snapshot stays empty, and the counter assumes
        it is ready and starts counting on paper — while the snapshot is taken
        later against a balance that has changed.
    """

    permission_classes = [CanManageInventory]
    serializer_class = s.OpenCountSerializer

    def post(self, request):
        serializer = s.OpenCountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        location = get_object_or_404(StockLocation, pk=data["location"])
        count = services.open_count(location, note=data.get("note", ""), actor=request.user)
        lines = services.snapshot_count(count)

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.CREATE,
            object_repr=f"جرد {count.reference} @ {location.code}",
            changes={"lines": lines},
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        count.refresh_from_db()
        return Response(s.StockCountDetailSerializer(count).data, status=201)


class RecordCountedAPI(APIView):
    permission_classes = [CanManageInventory]
    serializer_class = s.RecordCountedSerializer

    def post(self, request, pk):
        serializer = s.RecordCountedSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        count = get_object_or_404(StockCount, pk=pk)
        line = StockCountLine.objects.filter(pk=data["line"], count=count).first()
        if line is None:
            # ⚠️  Filtered by session: another session's line id used to be editable here
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        services.record_counted(count, line, data["counted_quantity"], note=data.get("note", ""))
        return Response(s.StockCountLineSerializer(line).data)


class ApplyStockCountAPI(APIView):
    """
    Approve the stock count — **it settles the discrepancies with recorded movements**.

    ⚠️  Irreversible: the discrepancies become movements, and correction goes
        through a new count.
    """

    permission_classes = [CanManageInventory]

    def post(self, request, pk):
        count = get_object_or_404(StockCount, pk=pk)
        result = services.apply_count(count, actor=request.user)

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.SETTING_CHANGE,
            object_repr=f"اعتماد جرد {count.reference}",
            changes=result,
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        count.refresh_from_db()
        return Response({**result, "count": s.StockCountSerializer(count).data})


class CancelStockCountAPI(APIView):
    permission_classes = [CanManageInventory]
    serializer_class = s.CancelCountSerializer

    def post(self, request, pk):
        serializer = s.CancelCountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        count = get_object_or_404(StockCount, pk=pk)
        services.cancel_count(count, reason=serializer.validated_data["reason"])
        return Response(s.StockCountSerializer(count).data)
