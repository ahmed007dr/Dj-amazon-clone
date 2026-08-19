"""
Shipping services.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core.errors import BusinessError, ErrorCode
from core.money import ZERO, quantize
from shipping.models import (
    Shipment,
    ShipmentEvent,
    ShipmentStatus,
    ShippingMethod,
    ShippingRate,
    ShippingZone,
)

#: The permitted transitions — anything outside them is refused
ALLOWED_TRANSITIONS = {
    ShipmentStatus.PENDING: {ShipmentStatus.PICKED, ShipmentStatus.FAILED},
    ShipmentStatus.PICKED: {ShipmentStatus.IN_TRANSIT, ShipmentStatus.FAILED},
    ShipmentStatus.IN_TRANSIT: {
        ShipmentStatus.OUT_FOR_DELIVERY,
        ShipmentStatus.FAILED,
    },
    ShipmentStatus.OUT_FOR_DELIVERY: {
        ShipmentStatus.DELIVERED,
        ShipmentStatus.FAILED,
    },
    ShipmentStatus.FAILED: {
        ShipmentStatus.OUT_FOR_DELIVERY,  # a retry
        ShipmentStatus.RETURNED,
    },
    ShipmentStatus.DELIVERED: set(),  # terminal
    ShipmentStatus.RETURNED: set(),  # terminal
}


@dataclass(frozen=True)
class ShippingQuote:
    """A shipping quote."""

    method_code: str
    method_name_ar: str
    method_name_en: str
    fee: Decimal
    is_free: bool
    estimated_days_min: int
    estimated_days_max: int
    is_pickup: bool


def quote(governorate: str, subtotal: Decimal, *, weight_grams: int = 0) -> list[ShippingQuote]:
    """
    The shipping quotes available for this governorate.

    ⚠️  Computed from the source on every request.

        The frontend does not send the shipping fee and is not trusted for it —
        sending it from the client means free shipping by editing a field in the browser.
    """
    zone = ShippingZone.for_governorate(governorate)
    if zone is None:
        return []

    rates = ShippingRate.objects.filter(
        zone=zone, is_active=True, method__is_active=True
    ).select_related("method")

    quotes = []
    for rate in rates:
        if rate.method.is_pickup:
            fee, is_free = ZERO, True
        elif rate.free_above is not None and subtotal >= rate.free_above:
            fee, is_free = ZERO, True
        else:
            fee = rate.base_fee
            if rate.per_kg_fee and weight_grams:
                fee += quantize(rate.per_kg_fee * Decimal(weight_grams) / Decimal(1000))
            fee, is_free = quantize(fee), False

        quotes.append(
            ShippingQuote(
                method_code=rate.method.code,
                method_name_ar=rate.method.name_ar,
                method_name_en=rate.method.name_en,
                fee=fee,
                is_free=is_free,
                estimated_days_min=rate.method.estimated_days_min,
                estimated_days_max=rate.method.estimated_days_max,
                is_pickup=rate.method.is_pickup,
            )
        )

    return sorted(quotes, key=lambda q: (q.fee, q.estimated_days_min))


def fee_for(method_code: str, governorate: str, subtotal: Decimal, *, weight_grams: int = 0):
    """The fee for a specific method, or `None` if it is unavailable."""
    for entry in quote(governorate, subtotal, weight_grams=weight_grams):
        if entry.method_code == method_code:
            return entry
    return None


@transaction.atomic
def create_shipment(
    *,
    method: ShippingMethod,
    address: dict,
    shipping_fee: Decimal,
    reference_type: str = "",
    reference_id: str = "",
    weight_grams: int = 0,
) -> Shipment:
    """
    Create a shipment with a copied address snapshot.

    ⚠️  The address is copied rather than referenced — the customer may edit it
        after shipping, and the snapshot at shipping time is what is defended in
        any dispute.
    """
    zone = ShippingZone.for_governorate(address.get("governorate", ""))

    shipment = Shipment.objects.create(
        method=method,
        zone=zone,
        reference_type=reference_type,
        reference_id=str(reference_id) if reference_id else "",
        recipient_name=address.get("recipient_name", ""),
        recipient_phone=address.get("phone", ""),
        governorate=address.get("governorate", ""),
        city=address.get("city", ""),
        street=address.get("street", ""),
        building=address.get("building", ""),
        landmark=address.get("landmark", ""),
        shipping_fee=shipping_fee,
        weight_grams=weight_grams,
    )

    ShipmentEvent.objects.create(
        shipment=shipment, status=ShipmentStatus.PENDING, note="أُنشئت الشحنة"
    )
    return shipment


@transaction.atomic
def transition(
    shipment: Shipment,
    to_status: str,
    *,
    note: str = "",
    location: str = "",
    tracking_number: str = "",
) -> Shipment:
    """
    Move the shipment to a new status.

    ⚠️  The permitted transitions are **declared explicitly**.

        Without a state machine, a "delivered" shipment can be returned to
        "processing" with one API call — corrupting every delivery report.
    """
    allowed = ALLOWED_TRANSITIONS.get(shipment.status, set())

    if to_status not in allowed:
        raise BusinessError(
            ErrorCode.INVALID_STATE_TRANSITION,
            detail=f"{shipment.status} ⟵ {to_status} غير مسموح",
            status_code=409,
        )

    shipment.status = to_status
    updates = ["status"]

    if tracking_number:
        shipment.tracking_number = tracking_number
        updates.append("tracking_number")

    now = timezone.now()
    if to_status == ShipmentStatus.IN_TRANSIT and shipment.shipped_at is None:
        shipment.shipped_at = now
        updates.append("shipped_at")
    elif to_status == ShipmentStatus.DELIVERED:
        shipment.delivered_at = now
        updates.append("delivered_at")
    elif to_status == ShipmentStatus.FAILED and note:
        shipment.failure_reason = note
        updates.append("failure_reason")

    shipment.save(update_fields=updates)

    ShipmentEvent.objects.create(shipment=shipment, status=to_status, note=note, location=location)
    return shipment
