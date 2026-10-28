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

from catalog import audit as catalog_audit
from catalog.models import Product, ProductColor, ProductVariant
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


def _has_sellable_variants(product) -> bool:
    return (
        ProductVariant.objects.filter(product=product, is_active=True)
        .filter(Q(color__isnull=True) | Q(color__is_active=True, color__deleted_at__isnull=True))
        .exists()
    )


def _resolve_variant(product, value, *, required: bool = False):
    """
    The variant a stock command is aimed at — which must be **this product's**.

    ⚠️  Previously any variant id was accepted, so stock could be received "into" a
        variant of an entirely different product and sit there looking like that
        product's balance.

    ⚠️  `required` is for commands that *add* stock (receive, an increase). Once a
        product offers colours or sizes, units added to "no variant" are unsellable
        — the cart insists on a variant — and nobody would notice until the product
        sold out with a full shelf. Moving or removing legacy un-assigned stock stays
        allowed without a variant.
    """
    if not value:
        if required and _has_sellable_variants(product):
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR,
                detail="هذا المنتج له ألوان أو نسخ — اختر النسخة التي يُضاف إليها المخزون",
            )
        return None

    variant = get_object_or_404(ProductVariant.objects.select_related("color"), pk=value)
    if variant.product_id != product.pk:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="النسخة لا تخص هذا المنتج")
    return variant


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


class ProductAvailabilityAPI(APIView):
    """
    One product's availability **per variant** — what a colour / size picker needs.

        GET /inventory/availability/<product>/

    ⚠️  Public, so masked exactly like the list endpoint: a number only at or below
        the low-stock threshold, otherwise just "in stock". And the stock held on
        *no variant* is never shown here — a customer cannot choose it.
    """

    permission_classes = [AllowAny]

    def get(self, request, pk):
        product = get_object_or_404(Product, pk=pk, is_active=True)
        per_variant = services.availability_by_variant([product.pk])[str(product.pk)]

        variants = {}
        for variant_id, available in per_variant.items():
            if variant_id is None:
                continue
            variants[str(variant_id)] = {
                "is_available": available > 0,
                "is_low": 0 < available <= services.LOW_STOCK_THRESHOLD,
                "available": available if available <= services.LOW_STOCK_THRESHOLD else None,
            }

        if variants:
            is_available = any(entry["is_available"] for entry in variants.values())
        else:
            is_available = services.availability_for([product.pk])[str(product.pk)].is_available

        return Response(
            {"product_id": str(product.pk), "is_available": is_available, "variants": variants}
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
        queryset = Stock.objects.select_related("product", "location", "variant", "variant__color")
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


class UnstockedProductListAPI(generics.ListAPIView):
    """
    The products that have **no stock row at all**.

    ⚠️  **`StockListAPI` structurally cannot answer this.**

        It lists `Stock` rows, and these products have none — so they appear in no
        page of it, no `status=out` filter and no SKU search. The balances screen
        answers "what do I hold?"; nothing answered "what have I never
        received?", and on a catalogue imported without its opening balances that
        is the overwhelming majority of it.

        The gap matters more now that the storefront hides whatever has zero
        available: these products are invisible to customers **and** invisible on
        the screen an admin would open to find out why.

    ⚠️  And "no row" is kept distinct from "a row reading zero".

        Both are unbuyable and they are not the same problem: one is reordered,
        the other has never been received once. `?include_zero=true` merges them
        for whoever wants the single "cannot be sold" list.
    """

    permission_classes = [CanManageInventory]
    serializer_class = s.UnstockedProductSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        params = self.request.query_params

        queryset = Product.objects.all()
        if params.get("include_inactive") != "true":
            queryset = queryset.filter(is_active=True)

        if params.get("include_zero") == "true":
            # ⚠️  Everything unsellable — expressed through the same filter the
            #     storefront hides by, so the two answers cannot disagree.
            queryset = queryset.exclude(services.in_stock_filter())
        else:
            queryset = queryset.filter(stock_records__isnull=True)

        if search := params.get("search"):
            queryset = queryset.filter(
                Q(sku__icontains=search)
                | Q(name_ar__icontains=search)
                | Q(name_en__icontains=search)
            )

        return queryset.order_by("sku")


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
            "product", "location", "batch", "performed_by", "variant"
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

        product = _resolve(Product, data["product"])
        batch = services.receive(
            product,
            data["quantity"],
            data["unit_cost"],
            location=_resolve(StockLocation, data.get("location")),
            variant=_resolve_variant(product, data.get("variant"), required=True),
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

        product = _resolve(Product, data["product"])
        movement = services.adjust(
            product,
            data["quantity"],
            location=_resolve(StockLocation, data.get("location")),
            variant=_resolve_variant(product, data.get("variant"), required=data["quantity"] > 0),
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

        product = _resolve(Product, data["product"])
        out_movement, in_movement = services.transfer(
            product,
            data["quantity"],
            from_location=_resolve(StockLocation, data["from_location"]),
            to_location=_resolve(StockLocation, data["to_location"]),
            variant=_resolve_variant(product, data.get("variant")),
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

        product = _resolve(Product, data["product"])
        movement = services.mark_damaged(
            product,
            data["quantity"],
            location=_resolve(StockLocation, data.get("location")),
            variant=_resolve_variant(product, data.get("variant")),
            reason=data["reason"],
            performed_by=request.user,
        )
        return Response(s.StockMovementSerializer(movement).data, status=201)


class ProductVariantChoicesAPI(APIView):
    """
    The variants a stock command can target, with what each holds — for the movement form.

        GET /inventory/product-variants/?product=<id>

    Behind `CanManageInventory`, not the catalogue permission: the person receiving a
    delivery may not be allowed to edit products, and still needs to say *which colour*
    arrived. Exact figures, since this is an admin screen.
    """

    permission_classes = [CanManageInventory]

    def get(self, request):
        product = get_object_or_404(Product.all_objects, pk=request.query_params.get("product"))
        variants = (
            ProductVariant.objects.filter(product=product, is_active=True)
            .select_related("color")
            .order_by("display_order", "sku")
        )
        stock = services.availability_by_variant([product.pk])[str(product.pk)]

        rows = []
        for variant in variants:
            if not variant.is_sellable:
                continue
            color = variant.color if variant.color_id else None
            rows.append(
                {
                    "id": str(variant.pk),
                    "sku": variant.sku,
                    "name_ar": variant.name_ar,
                    "name_en": variant.name_en,
                    "available": stock.get(variant.pk, 0),
                    "color": (
                        {
                            "id": str(color.pk),
                            "name_ar": color.name_ar,
                            "name_en": color.name_en,
                            "hex": color.hex,
                        }
                        if color is not None
                        else None
                    ),
                }
            )
        return Response(rows)


class UnassignedStockAPI(APIView):
    """
    Stock a product holds on **no variant** — the number the "assign to a colour"
    step shows before the admin chooses.

        GET /inventory/unassigned-stock/?product=<id>
    """

    permission_classes = [CanManageInventory]

    def get(self, request):
        product = get_object_or_404(Product.all_objects, pk=request.query_params.get("product"))
        locations = services.unassigned_stock(product)
        return Response(
            {
                "product": str(product.pk),
                "total": sum(entry["quantity"] for entry in locations),
                "locations": [
                    {
                        "location": str(entry["location"].pk),
                        "location_code": entry["location_code"],
                        "quantity": entry["quantity"],
                    }
                    for entry in locations
                ],
            }
        )


class AssignStockAPI(APIView):
    """
    Give a product's un-assigned stock to one colour (or variant) — the one-time step
    after the product's **first** colour is added.

    ⚠️  Never automatic. See `services.assign_unvariated_stock` for why, and for what
        moves (only the available units, batches included).
    """

    permission_classes = [CanManageInventory]
    serializer_class = s.AssignStockSerializer

    def post(self, request):
        serializer = s.AssignStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        product = get_object_or_404(Product, pk=data["product"])

        if data.get("color"):
            color = get_object_or_404(ProductColor, pk=data["color"], product=product)
            variant = (
                ProductVariant.objects.filter(color=color, is_active=True)
                .order_by("display_order", "created_at")
                .first()
            )
            if variant is None:
                raise BusinessError(
                    ErrorCode.VALIDATION_ERROR, detail="هذا اللون بلا نسخة مفعّلة تستقبل المخزون"
                )
        else:
            variant = _resolve_variant(product, data["variant"])

        result = services.assign_unvariated_stock(
            product,
            variant,
            location=_resolve(StockLocation, data.get("location")),
            performed_by=request.user,
        )
        if not result["moved"]:
            raise BusinessError(
                ErrorCode.CONFLICT, detail="لا يوجد مخزون غير مخصَّص لنقله", status_code=409
            )

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.STOCK_CHANGE,
            object_repr=f"تخصيص مخزون {product.sku} ← {variant.sku}",
            changes=result,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        catalog_audit.log_product_change(
            request,
            product,
            AuditAction.STOCK_CHANGE,
            {"assigned_to": variant.sku, **result},
            object_repr=f"مخزون منتج {product.sku}",
        )
        return Response(result)


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
