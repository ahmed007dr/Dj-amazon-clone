"""Shipping endpoints."""

from decimal import Decimal, InvalidOperation

from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from core.permissions import CanManageShipping
from shipping import serializers as s
from shipping import services
from shipping.governorates import EGYPT_GOVERNORATES
from shipping.models import Shipment, ShippingMethod, ShippingRate, ShippingZone


class ShippingQuoteAPI(APIView):
    """The shipping quotes available for this governorate — computed from the source."""

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
    Tracking by number.

    ⚠️  Deliberately public — the customer shares the number with whoever
        receives on their behalf.

        And for exactly that reason the response exposes neither the full
        address nor the phone number: a number that gets shared must carry no
        personal data.
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
    permission_classes = [CanManageShipping]
    serializer_class = s.ShipmentSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = Shipment.objects.select_related("method").prefetch_related("events")
        if status_filter := self.request.query_params.get("status"):
            queryset = queryset.filter(status=status_filter)
        return queryset


class AdminTransitionShipmentAPI(APIView):
    """
    ⚠️  A disallowed transition is refused by the state machine with `409`.

        A "delivered" shipment does not go back to "processing" — or every
        delivery report is corrupted.
    """

    permission_classes = [CanManageShipping]
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


# ═══════════════════════════════════════════════════════════
#  Configuration — zones, methods and rates
# ═══════════════════════════════════════════════════════════
#
# ⚠️  **These edit the table the checkout quotes from.**
#
#     Until now the fee table was reachable only from the Django panel, which
#     meant the person who sets the delivery price and the person who runs the
#     shop were not allowed to be the same person: `/admin/` hands out the whole
#     database, not the shipping fees. So the fees were set once at launch and
#     never revisited — a governorate added to a zone six months later needed a
#     developer.
#
# ⚠️  And they all sit behind `CanManageShipping` — the same permission that
#     moves a shipment, not a new one.
#
#     Splitting "configure shipping" from "operate shipping" reads tidier and is
#     wrong in practice: the person who watches parcels fail in Upper Egypt is
#     the person who needs to raise its fee. A second permission means they file
#     a request instead, and the fee stays wrong until somebody else gets to it.


def _log(request, action: str, what: str, **changes) -> None:
    """The audit trail for a fee change — who moved the price, and to what."""
    AuditLog.objects.create(
        actor=request.user,
        action=action,
        object_repr=what,
        changes=changes,
        ip_address=request.META.get("REMOTE_ADDR"),
    )


class ShippingCoverageAPI(APIView):
    """
    The reference governorates, each with the zone that claims it.

    ⚠️  **The server owns this list, and the form picks from it.**

        `for_governorate` matches the name literally, so a zone holding
        "الاسكندرية" while the address says "الإسكندرية" quotes the default
        fee for Alexandria and nothing anywhere reports a problem. A free-text
        field guarantees this eventually; a picker fed from here cannot produce it.

    ⚠️  `has_default_zone` is here because its absence is invisible.

        With no default, every unassigned governorate gets an empty quote and
        the customer sees "no shipping available" — a checkout that cannot
        complete, caused by a setting nobody was asked about.
    """

    permission_classes = [CanManageShipping]

    def get(self, request):
        report = services.coverage()
        assigned = report["assigned"]

        return Response(
            {
                "governorates": [
                    {"name": name, "zone_code": assigned.get(name, "")}
                    for name in EGYPT_GOVERNORATES
                ],
                "unassigned": report["unassigned"],
                "default_zone_code": report["default_zone_code"],
                "has_default_zone": report["has_default_zone"],
            }
        )


class AdminZoneListCreateAPI(generics.ListCreateAPIView):
    """
    ⚠️  Unpaginated on purpose — there are twenty-seven governorates, so there is
        a ceiling on how many zones can usefully exist. Paginating them hides
        half the fee table behind a page control for no gain.
    """

    permission_classes = [CanManageShipping]
    serializer_class = s.AdminShippingZoneSerializer
    pagination_class = None

    def get_queryset(self):
        return ShippingZone.objects.prefetch_related("rates").order_by("-is_default", "code")

    def perform_create(self, serializer):
        zone = serializer.save()
        _log(
            self.request,
            AuditAction.CREATE,
            f"منطقة شحن {zone.code}",
            governorates=zone.governorates,
            is_default=zone.is_default,
        )


class AdminZoneDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [CanManageShipping]
    serializer_class = s.AdminShippingZoneSerializer
    queryset = ShippingZone.objects.prefetch_related("rates")

    def perform_update(self, serializer):
        zone = serializer.save()
        _log(
            self.request,
            AuditAction.SETTING_CHANGE,
            f"منطقة شحن {zone.code}",
            fields=sorted(serializer.validated_data),
            governorates=zone.governorates,
        )

    def perform_destroy(self, instance):
        services.delete_zone(instance)
        _log(self.request, AuditAction.DELETE, f"منطقة شحن {instance.code}")


class AdminMethodListCreateAPI(generics.ListCreateAPIView):
    """
    ⚠️  Not the same list as the public `methods/`.

        That one serves the checkout and shows only what is active; this one
        shows the disabled methods too — a method the admin turned off has to
        remain visible, or turning it back on means creating it again.
    """

    permission_classes = [CanManageShipping]
    serializer_class = s.AdminShippingMethodSerializer
    pagination_class = None
    queryset = ShippingMethod.objects.order_by("display_order", "code")

    def perform_create(self, serializer):
        method = serializer.save()
        _log(
            self.request,
            AuditAction.CREATE,
            f"طريقة شحن {method.code}",
            is_pickup=method.is_pickup,
        )


class AdminMethodDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [CanManageShipping]
    serializer_class = s.AdminShippingMethodSerializer
    queryset = ShippingMethod.objects.all()

    def perform_update(self, serializer):
        method = serializer.save()
        _log(
            self.request,
            AuditAction.SETTING_CHANGE,
            f"طريقة شحن {method.code}",
            fields=sorted(serializer.validated_data),
        )

    def perform_destroy(self, instance):
        services.delete_method(instance)
        _log(self.request, AuditAction.DELETE, f"طريقة شحن {instance.code}")


class AdminRateListCreateAPI(generics.ListCreateAPIView):
    """
    The fee table — zone × method.

    ⚠️  Unpaginated, and that is the point of the screen: the fees are read as a
        grid, and a grid split across pages cannot be compared. Zones times
        methods stays in the low tens.
    """

    permission_classes = [CanManageShipping]
    serializer_class = s.AdminShippingRateSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = ShippingRate.objects.select_related("zone", "method")

        if zone := self.request.query_params.get("zone"):
            queryset = queryset.filter(zone_id=zone)
        if method := self.request.query_params.get("method"):
            queryset = queryset.filter(method_id=method)

        return queryset.order_by("zone__code", "method__display_order")

    def perform_create(self, serializer):
        rate = serializer.save()
        _log(
            self.request,
            # ⚠️  `PRICE_CHANGE`, not `CREATE`: this is a price the customer pays,
            #     and it belongs in the same audit filter as the other prices.
            AuditAction.PRICE_CHANGE,
            f"تعريفة شحن {rate.zone.code} × {rate.method.code}",
            base_fee=str(rate.base_fee),
            free_above=str(rate.free_above) if rate.free_above is not None else None,
            per_kg_fee=str(rate.per_kg_fee),
        )


class AdminRateDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [CanManageShipping]
    serializer_class = s.AdminShippingRateSerializer
    queryset = ShippingRate.objects.select_related("zone", "method")

    def perform_update(self, serializer):
        before = str(serializer.instance.base_fee)
        rate = serializer.save()
        _log(
            self.request,
            AuditAction.PRICE_CHANGE,
            f"تعريفة شحن {rate.zone.code} × {rate.method.code}",
            base_fee_from=before,
            base_fee_to=str(rate.base_fee),
            free_above=str(rate.free_above) if rate.free_above is not None else None,
        )

    def perform_destroy(self, instance):
        """
        ⚠️  A rate is deleted freely — unlike a zone or a method.

            Nothing points at it: the shipment stores the fee it was charged as
            a number, not a reference. Removing the row withdraws the option
            from future checkouts and rewrites no history.
        """
        _log(
            self.request,
            AuditAction.DELETE,
            f"تعريفة شحن {instance.zone.code} × {instance.method.code}",
            base_fee=str(instance.base_fee),
        )
        instance.delete()
