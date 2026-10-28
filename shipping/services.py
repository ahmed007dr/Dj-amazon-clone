"""
Shipping services.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from core import features
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
    #: The fee before the store-wide free-shipping rule — equal to `fee` unless that rule waived it
    original_fee: Decimal = ZERO
    #: True only when the **threshold rule** zeroed a fee that would otherwise be charged
    free_by_threshold: bool = False


@dataclass(frozen=True)
class FreeShippingStatus:
    """
    Where a cart stands against the store-wide free-shipping rule.

    ⚠️  Computed on the server and shown as-is: the storefront never subtracts
        the cart from the threshold itself.
    """

    enabled: bool
    threshold: Decimal
    qualifies: bool
    remaining: Decimal


def free_shipping_status(
    eligible_amount: Decimal, rule: features.FreeShippingRule | None = None
) -> FreeShippingStatus:
    """
    `eligible_amount`: the products total **after item and coupon discounts, before
    tax and shipping** — "X or more" qualifies, so exactly the threshold is free.

    A rule that is off (or on without a positive amount) reports `enabled=False`
    and the storefront draws nothing.
    """
    rule = rule or features.free_shipping_rule()
    if not rule.active:
        return FreeShippingStatus(enabled=False, threshold=ZERO, qualifies=False, remaining=ZERO)

    amount = quantize(max(eligible_amount, ZERO))
    qualifies = amount >= rule.threshold
    return FreeShippingStatus(
        enabled=True,
        threshold=rule.threshold,
        qualifies=qualifies,
        remaining=ZERO if qualifies else quantize(rule.threshold - amount),
    )


def quote(
    governorate: str,
    subtotal: Decimal,
    *,
    weight_grams: int = 0,
    eligible_amount: Decimal | None = None,
    rule: features.FreeShippingRule | None = None,
) -> list[ShippingQuote]:
    """
    The shipping quotes available for this governorate.

    `subtotal` feeds the per-zone `free_above` of each rate (existing behaviour).
    `eligible_amount` feeds the store-wide threshold rule and defaults to
    `subtotal` — callers that know the coupon discount pass the amount after it.

    ⚠️  Computed from the source on every request.

        The frontend does not send the shipping fee and is not trusted for it —
        sending it from the client means free shipping by editing a field in the browser.
    """
    zone = ShippingZone.for_governorate(governorate)
    if zone is None:
        return []

    status = free_shipping_status(subtotal if eligible_amount is None else eligible_amount, rule)

    # ⚠️  `method__deleted_at__isnull=True` is not redundant with the manager.
    #
    #     The soft-delete manager filters `ShippingRate`'s own rows; the joined
    #     method is not filtered by it. Without this, a method deleted from the
    #     Django panel keeps appearing at checkout — priced by a rate pointing at
    #     a method that no longer exists anywhere in the admin.
    rates = ShippingRate.objects.filter(
        zone=zone,
        is_active=True,
        method__is_active=True,
        method__deleted_at__isnull=True,
    ).select_related("method")

    quotes = []
    for rate in rates:
        free_by_threshold = False

        if rate.method.is_pickup:
            fee, is_free = ZERO, True
            original_fee = fee
        elif rate.free_above is not None and subtotal >= rate.free_above:
            fee, is_free = ZERO, True
            original_fee = fee
        else:
            fee = rate.base_fee
            if rate.per_kg_fee and weight_grams:
                fee += quantize(rate.per_kg_fee * Decimal(weight_grams) / Decimal(1000))
            fee = original_fee = quantize(fee)
            is_free = False

            # ⚠️  The store-wide rule only waives a fee that would really be charged,
            #     and only for a method the owner left eligible (express can stay paid).
            #     A rate that costs nothing anyway is not "free by threshold" — reports
            #     must be able to tell the two apart.
            if status.qualifies and rate.method.eligible_for_free_shipping and fee > 0:
                fee, is_free, free_by_threshold = ZERO, True, True

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
                original_fee=original_fee,
                free_by_threshold=free_by_threshold,
            )
        )

    return sorted(quotes, key=lambda q: (q.fee, q.estimated_days_min))


def fee_for(
    method_code: str,
    governorate: str,
    subtotal: Decimal,
    *,
    weight_grams: int = 0,
    eligible_amount: Decimal | None = None,
    rule: features.FreeShippingRule | None = None,
):
    """The fee for a specific method, or `None` if it is unavailable."""
    for entry in quote(
        governorate,
        subtotal,
        weight_grams=weight_grams,
        eligible_amount=eligible_amount,
        rule=rule,
    ):
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


# ═══════════════════════════════════════════════════════════
#  Configuration — zones, methods and rates
# ═══════════════════════════════════════════════════════════
#
# ⚠️  These guard what the admin screen can do to the fee table.
#
#     Every rule here exists because breaking it is silent: the quote keeps
#     answering, the checkout keeps completing, and the wrong fee only shows up
#     in the margin at the end of the month.


def zone_conflicts(
    governorates: list[str], *, exclude_zone: ShippingZone | None = None
) -> dict[str, str]:
    """
    The governorates already claimed by another active zone → that zone's code.

    ⚠️  A governorate in two zones is **ambiguous, not additive**.

        `ShippingZone.for_governorate` iterates the active zones and returns the
        first match — so the fee depends on the row order of the query, which is
        not a promise the database makes. Cairo lands at 30 or at 90 depending
        on which zone happens to be read first, and the same address quotes
        differently on two consecutive requests.
    """
    wanted = set(governorates)
    if not wanted:
        return {}

    zones = ShippingZone.objects.filter(is_active=True)
    if exclude_zone is not None and exclude_zone.pk:
        zones = zones.exclude(pk=exclude_zone.pk)

    conflicts: dict[str, str] = {}
    for zone in zones:
        for name in zone.governorates or []:
            if name in wanted:
                conflicts.setdefault(name, zone.code)
    return conflicts


def stand_down_default_zone(*, exclude_pk=None) -> None:
    """
    Clear the current default so another zone can take it.

    ⚠️  Called **before** the new default is saved, not after.

        The uniqueness of the default is a database constraint, so saving a
        second one raises `IntegrityError` — a 500 the admin reads as "the panel
        is broken" while doing the only thing anyone ever means by that switch:
        moving the default from one zone to another.
    """
    zones = ShippingZone.objects.filter(is_default=True)
    if exclude_pk is not None:
        zones = zones.exclude(pk=exclude_pk)
    zones.update(is_default=False)


def coverage() -> dict:
    """
    Which governorates have a zone, and which fall through to the default.

    ⚠️  Surfaced on the screen rather than left to be discovered.

        A governorate with no zone is not an error anywhere: the default zone
        answers for it at its own fee. So an unassigned Alexandria quotes at the
        remote-area price and nothing complains — until a customer does.

        And **with no default zone at all** the quote comes back empty and the
        customer sees "no shipping available" — a checkout that cannot complete,
        caused by a setting nobody was asked about.
    """
    from shipping.governorates import EGYPT_GOVERNORATES

    assigned: dict[str, str] = {}
    for zone in ShippingZone.objects.filter(is_active=True):
        for name in zone.governorates or []:
            assigned.setdefault(name, zone.code)

    default_zone = ShippingZone.objects.filter(is_default=True, is_active=True).first()

    return {
        "assigned": assigned,
        "unassigned": [name for name in EGYPT_GOVERNORATES if name not in assigned],
        "default_zone_code": default_zone.code if default_zone else "",
        "has_default_zone": default_zone is not None,
    }


@transaction.atomic
def delete_zone(zone: ShippingZone) -> None:
    """
    Retire a zone and the rates hanging off it.

    ⚠️  **The default zone is never deleted.**

        It answers for every governorate nobody assigned. Delete it and those
        addresses get an empty quote — the checkout stops for customers nobody
        was thinking about while clicking delete.

    ⚠️  And a zone that carries shipments is disabled, not deleted: "what did we
        charge for this delivery, and why?" is answered by the zone it names.

    ⚠️  The rates are soft-deleted **explicitly**.

        `ShippingRate.zone` is `CASCADE`, but the cascade belongs to the SQL
        `DELETE` — and `BaseModel.delete` stamps `deleted_at` instead. So the
        rates survive their zone, and a zone restored later comes back carrying
        prices it was never re-approved for.
    """
    if zone.is_default:
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail="هذه هي المنطقة الافتراضية — اجعل منطقة أخرى افتراضية قبل حذفها",
            status_code=409,
        )

    used = Shipment.objects.filter(zone=zone).count()
    if used:
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail=f"على هذه المنطقة {used} شحنة — أوقفها بدل حذفها لتبقى سجلات الشحن مفهومة",
            status_code=409,
        )

    ShippingRate.objects.filter(zone=zone).delete()
    zone.delete()


@transaction.atomic
def delete_method(method: ShippingMethod) -> None:
    """
    Retire a method and the rates that price it.

    ⚠️  A method carrying shipments is disabled, never deleted — the shipment
        names the service the customer was actually sold.

    ⚠️  And the rates go with it, or the method **keeps quoting after deletion**.

        `quote()` reads `ShippingRate.objects.filter(method__is_active=True)`.
        The soft-delete manager filters the rate rows, not the joined method —
        so a deleted-but-active method still appears at checkout, priced by a
        rate whose method no longer exists in the panel.
    """
    used = Shipment.objects.filter(method=method).count()
    if used:
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail=f"على هذه الطريقة {used} شحنة — أوقفها بدل حذفها لتبقى سجلات الشحن مفهومة",
            status_code=409,
        )

    ShippingRate.objects.filter(method=method).delete()
    method.is_active = False
    method.save(update_fields=["is_active"])
    method.delete()


# ═══════════════════════════════════════════════════════════
#  Free shipping above an amount — the owner's switch
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def save_free_shipping_rule(
    *, enabled: bool, threshold: Decimal
) -> tuple[features.FreeShippingRule, features.FreeShippingRule]:
    """
    Store the switch and the amount; returns `(before, after)` for the audit trail.

    ⚠️  The two rows are written together or not at all — a switch flipped on
        while the amount write fails would leave the shop on a rule nobody saw.

    ⚠️  `get_or_create` first: if the rows are missing (a database restored from
        before `core/0003`), they are created with their labels; an existing row
        keeps whatever the Django panel shows for it and only gets a new value.
    """
    from core.models.settings import SystemSetting

    before = features.free_shipping_rule()
    threshold = quantize(threshold)

    wanted = {
        features.FREE_SHIPPING_ENABLED: (
            bool(enabled),
            {
                "value_type": "BOOL",
                "label_ar": "تفعيل الشحن المجاني فوق مبلغ معيّن",
                "label_en": "Free shipping above an amount",
            },
        ),
        features.FREE_SHIPPING_THRESHOLD: (
            str(threshold),
            {
                "value_type": "DECIMAL",
                "label_ar": "حدّ الشحن المجاني (بالجنيه)",
                "label_en": "Free shipping threshold (EGP)",
            },
        ),
    }
    for key, (value, defaults) in wanted.items():
        row, created = SystemSetting.objects.get_or_create(
            key=key, defaults={"value": value, "group": "orders", **defaults}
        )
        if not created and row.value != value:
            row.value = value
            row.save()  # ⚠️  `save()`, not `update()`: it drops the cached copy

    return before, features.free_shipping_rule()
