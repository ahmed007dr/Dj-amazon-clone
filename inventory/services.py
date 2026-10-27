"""
Inventory services — the only public interface.

⚠️  **Other domains call these functions and never touch the models.**

    The legacy code did this in `orders/api.py`:

        product.quantity -= item.quantity
        product.save()

    Three defects in two lines: one domain editing another domain's model · no
    transaction · no lock. Guaranteed overselling under any concurrency.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Exists, F, OuterRef, Q, Sum, Value
from django.db.models.functions import Greatest
from django.utils import timezone

from catalog.models import ProductColor, ProductVariant
from core.errors import BusinessError, ErrorCode
from inventory.models import (
    AlertType,
    Batch,
    MovementType,
    ReservationStatus,
    Stock,
    StockAlert,
    StockCount,
    StockCountLine,
    StockCountStatus,
    StockLocation,
    StockMovement,
    StockReservation,
)

logger = logging.getLogger(__name__)

#: The default reservation timeout — an abandoned cart does not hold stock forever
DEFAULT_RESERVATION_TTL = timedelta(minutes=30)

#: The near-expiry alert threshold
EXPIRY_WARNING_DAYS = 90

#: At or below this the public sees an exact number ("3 left"); above it just "in stock"
LOW_STOCK_THRESHOLD = 5


@dataclass(frozen=True)
class Availability:
    """A product's availability — what the catalogue and the cart need."""

    product_id: str
    available: int
    is_available: bool
    locations: dict

    @property
    def is_low(self) -> bool:
        return 0 < self.available <= LOW_STOCK_THRESHOLD


# ═══════════════════════════════════════════════════════════
#  Reading
# ═══════════════════════════════════════════════════════════


def get_or_create_stock(product, location=None, variant=None) -> Stock:
    """
    ⚠️  **A missing default location is a configuration state, not a crash.**

        This raised `INTERNAL_ERROR` — "حدث خطأ غير متوقع" — for a condition the
        admin creates and the admin fixes: no location is flagged default, or the
        one that is has been deactivated (`get_default` requires `is_active`, so
        a location still showing the default tick in settings stops being the
        default the moment it is switched off).

        Reporting it as an internal error sends the admin to look for a bug in a
        situation their own settings screen can resolve in one click, and tells
        them nothing about which screen. The message now names the fix.

    ⚠️  And the constraint on the model guarantees **at most** one default, never
        at least one. There is no database state to lean on here.
    """
    location = location or StockLocation.get_default()
    if location is None:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            detail=(
                "لا يوجد موقع تخزين افتراضي — حدّد الموقع في النموذج، "
                "أو عيّن موقعًا افتراضيًا مفعّلًا من: إعدادات مرجعية ← مواقع التخزين"
            ),
        )

    stock, _created = Stock.objects.get_or_create(
        product=product, variant=variant, location=location
    )
    return stock


def counts_toward_availability() -> Q:
    """
    A condition on a `Stock` row: "can this stock actually be sold?"

    ⚠️  Not every row that holds units is sellable.

        * A row on a **variant** counts only while that variant — and its colour —
          is live. Stock left on a deactivated colour is still on the books but a
          customer cannot buy it, so it must not keep the product on the storefront.
        * A row with **no variant** counts only for a product that *has no sellable
          variant*. The cart requires a variant whenever the product offers one, so
          units sitting un-assigned on a product that has since gained colours are
          unsellable — until the admin assigns them (`assign_unvariated_stock`).
          Counting them advertises stock nobody can put in a basket.

    Used by the storefront filter, the public availability figures and the colour
    facts, so the three cannot disagree.
    """
    live_colour = Q(variant__color__isnull=True) | Q(
        variant__color__is_active=True, variant__color__deleted_at__isnull=True
    )
    on_live_variant = (
        Q(variant__isnull=False, variant__is_active=True, variant__deleted_at__isnull=True)
        & live_colour
    )

    product_has_sellable_variant = Exists(
        ProductVariant.objects.filter(product=OuterRef("product"), is_active=True).filter(
            Q(color__isnull=True) | Q(color__is_active=True, color__deleted_at__isnull=True)
        )
    )
    unvaried_and_allowed = Q(variant__isnull=True) & ~Q(product_has_sellable_variant)

    return unvaried_and_allowed | on_live_variant


def availability_for(product_ids, location=None) -> dict:
    """
    Availability for a set of products — **a single aggregated query**.

    ⚠️  This function is what keeps N+1 from returning.

        The catalogue calls it once per page, not once per product. Evaluating
        each row separately means twenty queries on a page of twenty products.

    ⚠️  **Every requested id comes back, including the ones with no stock row at
        all.**

        The earlier form built the result from the rows it found, so a product
        that had never been received simply had no key in the response — and the
        storefront reads a missing key as "the data has not arrived yet", not as
        "there is none". The badge stayed hidden and the add-to-cart button
        stayed enabled on precisely the products that have never had a single
        unit: the answer "we do not know" was returned for a question we know
        the answer to.

        No stock row is not the absence of an answer. It is zero.
    """
    queryset = Stock.objects.filter(product_id__in=product_ids).filter(counts_toward_availability())
    if location is not None:
        queryset = queryset.filter(location=location)
    else:
        queryset = queryset.filter(location__is_sellable=True, location__is_active=True)

    rows = queryset.values("product_id", "location__code").annotate(
        physical=Sum("quantity_physical"),
        reserved=Sum("quantity_reserved"),
        damaged=Sum("quantity_damaged"),
        expired=Sum("quantity_expired"),
    )

    result: dict = {}
    for row in rows:
        product_id = str(row["product_id"])
        available = max(
            0,
            (row["physical"] or 0)
            - (row["reserved"] or 0)
            - (row["damaged"] or 0)
            - (row["expired"] or 0),
        )

        entry = result.setdefault(
            product_id,
            {"total": 0, "locations": {}},
        )
        entry["total"] += available
        entry["locations"][row["location__code"]] = available

    for product_id in product_ids:
        result.setdefault(str(product_id), {"total": 0, "locations": {}})

    return {
        product_id: Availability(
            product_id=product_id,
            available=data["total"],
            is_available=data["total"] > 0,
            locations=data["locations"],
        )
        for product_id, data in result.items()
    }


def available_quantity(product, location=None, variant=None) -> int:
    stock = Stock.objects.filter(product=product, variant=variant)
    if location is not None:
        stock = stock.filter(location=location)
    else:
        stock = stock.filter(location__is_sellable=True, location__is_active=True)

    totals = stock.aggregate(
        physical=Sum("quantity_physical"),
        reserved=Sum("quantity_reserved"),
        damaged=Sum("quantity_damaged"),
        expired=Sum("quantity_expired"),
    )
    return max(
        0,
        (totals["physical"] or 0)
        - (totals["reserved"] or 0)
        - (totals["damaged"] or 0)
        - (totals["expired"] or 0),
    )


def availability_by_variant(product_ids, location=None) -> dict:
    """
    Availability **per variant** — `{product_id: {variant_id | None: available}}`.

    One query however many products and variants there are.

    ⚠️  Every sellable variant of a requested product is present, with `0` when it
        has no stock row — the same rule as `availability_for`: "no row" is zero,
        not "unknown". And a row on a variant that is not sellable (deactivated
        colour…) is left out entirely rather than reported as out of stock, because
        the customer cannot choose it at all.

    The `None` key is stock held on **no variant** — it appears only when the
    product has some, and only when it is still sellable (see
    `counts_toward_availability`).
    """
    product_ids = [str(pid) for pid in product_ids]

    queryset = Stock.objects.filter(product_id__in=product_ids).filter(counts_toward_availability())
    if location is not None:
        queryset = queryset.filter(location=location)
    else:
        queryset = queryset.filter(location__is_sellable=True, location__is_active=True)

    result: dict = {pid: {} for pid in product_ids}

    for row in queryset.values(
        "product_id",
        "variant_id",
        "quantity_physical",
        "quantity_reserved",
        "quantity_damaged",
        "quantity_expired",
    ):
        # ⚠️  Floored per stock row, exactly as `Stock.available` and `availability_for` do:
        #     a damaged surplus in one branch must not eat another branch's stock.
        available = max(
            0,
            row["quantity_physical"]
            - row["quantity_reserved"]
            - row["quantity_damaged"]
            - row["quantity_expired"],
        )
        per_variant = result.setdefault(str(row["product_id"]), {})
        per_variant[row["variant_id"]] = per_variant.get(row["variant_id"], 0) + available

    sellable = (
        ProductVariant.objects.filter(product_id__in=product_ids, is_active=True)
        .filter(Q(color__isnull=True) | Q(color__is_active=True, color__deleted_at__isnull=True))
        .values_list("product_id", "pk")
    )
    for product_id, variant_id in sellable:
        result.setdefault(str(product_id), {}).setdefault(variant_id, 0)

    return result


def color_stock_facts(product, colors, user) -> dict[str, dict]:
    """
    `{color_id: {quantity, is_available, is_low, available}}` — the colours' stock.

    Registered with `core.color_facts` (the catalogue cannot import this layer).

    * `quantity` is the **exact** figure — read by the admin colour list only;
      the public serialiser never forwards it.
    * `available` is the public, masked one: a number below the threshold, else
      `None` (the same rule as `AvailabilitySerializer` — "847 left" tells a
      competitor your stock volume).
    * A colour's stock is the sum over **all its variants** (one, or a size
      matrix), over every sellable location.
    """
    ids = [color.pk for color in colors]
    totals = {color_id: 0 for color_id in ids}

    rows = Stock.objects.filter(
        product=product,
        variant__color_id__in=ids,
        variant__is_active=True,
        location__is_sellable=True,
        location__is_active=True,
    ).values_list(
        "variant__color_id",
        "quantity_physical",
        "quantity_reserved",
        "quantity_damaged",
        "quantity_expired",
    )
    for color_id, physical, reserved, damaged, expired in rows:
        totals[color_id] += max(0, physical - reserved - damaged - expired)

    return {
        str(color_id): {
            "quantity": quantity,
            "is_available": quantity > 0,
            "is_low": 0 < quantity <= LOW_STOCK_THRESHOLD,
            "available": quantity if quantity <= LOW_STOCK_THRESHOLD else None,
        }
        for color_id, quantity in totals.items()
    }


# ═══════════════════════════════════════════════════════════
#  Catalogue visibility — "does any of it exist?"
# ═══════════════════════════════════════════════════════════

#: The name the filter is registered under in `core.visibility`
IN_STOCK_FILTER = "inventory.in_stock"


def in_stock_filter(*, location=None, field: str = "pk") -> Q:
    """
    A ready-made filter excluding products whose available quantity is zero.

        Product.objects.filter(inventory.services.in_stock_filter())

    ⚠️  `Exists`, not an aggregate — and the difference is the whole point.

        Summing per product means a `GROUP BY` over every stock row in the
        store on every catalogue page. `Exists` stops the database at the
        **first** row that satisfies the condition, and it composes into the
        query rather than replacing it: the count stays right and pagination
        does not yield short pages.

    ⚠️  And "any row above zero" is the same answer as "the total is above zero".

        `Stock.available` floors each row at zero (a damaged surplus in one
        branch does not eat another branch's stock), so the total is a sum of
        non-negative terms — it exceeds zero exactly when one term does. The
        cheap check and the expensive one agree, so we take the cheap one.

    ⚠️  `location=None` means **every sellable, active location** — deliberately
        the same set `availability_for` reports on.

        A quarantine or a damaged-goods store is not sellable; counting it makes
        the storefront advertise stock that cannot be sold. The counter passes
        its own register's location instead: an item sitting in another branch
        is not on the shelf in front of the cashier.
    """
    rows = Stock.objects.filter(**{"product": OuterRef(field)})

    if location is not None:
        rows = rows.filter(location=location)
    else:
        rows = rows.filter(location__is_sellable=True, location__is_active=True)

    rows = rows.filter(counts_toward_availability()).annotate(
        _available=F("quantity_physical")
        - F("quantity_reserved")
        - F("quantity_damaged")
        - F("quantity_expired")
    ).filter(_available__gt=0)

    return Q(Exists(rows))


# ═══════════════════════════════════════════════════════════
#  Writing — always under a lock and a transaction
# ═══════════════════════════════════════════════════════════


def _locked_stock(product, location, variant=None) -> Stock:
    """
    Fetches the balance **locked**.

    ⚠️  `select_for_update` **does nothing on SQLite**.

        That is why it is not relied on alone: `Stock` carries a
        `CheckConstraint` preventing reserved from exceeding physical, and it
        works on both engines and cannot be bypassed by any code path.

        The lock is for correctness under concurrency; the constraint is for
        absolute impossibility.
    """
    stock = (
        Stock.objects.select_for_update()
        .filter(product=product, variant=variant, location=location)
        .first()
    )
    if stock is None:
        stock = get_or_create_stock(product, location, variant)
        stock = Stock.objects.select_for_update().get(pk=stock.pk)
    return stock


def _record_movement(
    *,
    stock: Stock,
    movement_type: str,
    quantity: int,
    batch=None,
    unit_cost=None,
    reference_type: str = "",
    reference_id: str = "",
    note: str = "",
    performed_by=None,
) -> StockMovement:
    return StockMovement.objects.create(
        product=stock.product,
        variant=stock.variant,
        location=stock.location,
        batch=batch,
        movement_type=movement_type,
        quantity=quantity,
        balance_after=stock.quantity_physical,
        unit_cost=unit_cost,
        reference_type=reference_type,
        reference_id=str(reference_id) if reference_id else "",
        note=note,
        performed_by=performed_by,
    )


@transaction.atomic
def receive(
    product,
    quantity: int,
    unit_cost,
    *,
    location=None,
    variant=None,
    expires_at=None,
    supplier_batch_number: str = "",
    performed_by=None,
) -> Batch:
    """
    Receive a batch.

    ⚠️  `unit_cost` is mandatory — without it calculating profit later is impossible.
    """
    if quantity <= 0:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الكمية يجب أن تكون موجبة")

    location = location or StockLocation.get_default()
    stock = _locked_stock(product, location, variant)

    batch = Batch.objects.create(
        product=product,
        variant=variant,
        location=location,
        quantity_received=quantity,
        quantity_remaining=quantity,
        unit_cost=unit_cost,
        expires_at=expires_at,
        supplier_batch_number=supplier_batch_number,
    )

    Stock.objects.filter(pk=stock.pk).update(quantity_physical=F("quantity_physical") + quantity)
    stock.refresh_from_db()

    _record_movement(
        stock=stock,
        movement_type=MovementType.RECEIPT,
        quantity=quantity,
        batch=batch,
        unit_cost=unit_cost,
        performed_by=performed_by,
    )

    resolve_alerts(product, location)
    return batch


@transaction.atomic
def reserve(
    product,
    quantity: int,
    *,
    location=None,
    variant=None,
    reference_type: str = "",
    reference_id: str = "",
    ttl: timedelta | None = None,
) -> StockReservation:
    """
    Reserve stock.

    ⚠️  **This is where overselling is prevented.**

        The check and the increment happen under the same lock and the same
        transaction. Checking outside them leaves a window through which two
        concurrent orders take the same unit.
    """
    if quantity <= 0:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الكمية يجب أن تكون موجبة")

    location = location or StockLocation.get_default()
    stock = _locked_stock(product, location, variant)

    if stock.available < quantity:
        raise BusinessError(
            ErrorCode.INSUFFICIENT_STOCK,
            detail=f"المتاح: {stock.available} · المطلوب: {quantity}",
        )

    Stock.objects.filter(pk=stock.pk).update(quantity_reserved=F("quantity_reserved") + quantity)
    stock.refresh_from_db()

    reservation = StockReservation.objects.create(
        product=product,
        variant=variant,
        location=location,
        quantity=quantity,
        reference_type=reference_type,
        reference_id=str(reference_id) if reference_id else "",
        expires_at=timezone.now() + (ttl or DEFAULT_RESERVATION_TTL),
    )

    _record_movement(
        stock=stock,
        movement_type=MovementType.RESERVE,
        quantity=quantity,
        reference_type=reference_type,
        reference_id=reference_id,
    )

    check_alerts(product, location)
    return reservation


@transaction.atomic
def release(reservation: StockReservation, *, expired: bool = False) -> StockReservation:
    """Release a reservation — it returns the quantity to available."""
    if reservation.status != ReservationStatus.ACTIVE:
        return reservation

    stock = _locked_stock(reservation.product, reservation.location, reservation.variant)

    # ⚠️  `Greatest(..., 0)` prevents a negative balance should release be called
    #     twice on the same reservation despite the status check above.
    Stock.objects.filter(pk=stock.pk).update(
        quantity_reserved=Greatest(F("quantity_reserved") - reservation.quantity, Value(0))
    )
    stock.refresh_from_db()

    reservation.status = ReservationStatus.EXPIRED if expired else ReservationStatus.RELEASED
    reservation.resolved_at = timezone.now()
    reservation.save(update_fields=["status", "resolved_at"])

    _record_movement(
        stock=stock,
        movement_type=MovementType.RELEASE,
        quantity=reservation.quantity,
        reference_type=reservation.reference_type,
        reference_id=reservation.reference_id,
    )

    resolve_alerts(reservation.product, reservation.location)
    return reservation


@transaction.atomic
def commit(reservation: StockReservation, *, performed_by=None) -> list[StockMovement]:
    """
    Fulfil the reservation — the actual sale.

    It decrements physical and reserved together, and consumes the batches in
    **FEFO** order.
    """
    if reservation.status != ReservationStatus.ACTIVE:
        raise BusinessError(
            ErrorCode.INVALID_STATE_TRANSITION,
            detail=f"الحجز في حالة {reservation.status}",
        )

    stock = _locked_stock(reservation.product, reservation.location, reservation.variant)

    movements = _consume_batches(
        stock=stock,
        quantity=reservation.quantity,
        reference_type=reservation.reference_type,
        reference_id=reservation.reference_id,
        performed_by=performed_by,
    )

    Stock.objects.filter(pk=stock.pk).update(
        quantity_physical=F("quantity_physical") - reservation.quantity,
        quantity_reserved=F("quantity_reserved") - reservation.quantity,
    )

    reservation.status = ReservationStatus.COMMITTED
    reservation.resolved_at = timezone.now()
    reservation.save(update_fields=["status", "resolved_at"])

    check_alerts(reservation.product, reservation.location)
    return movements


@transaction.atomic
def sell_immediately(
    product,
    quantity: int,
    *,
    location=None,
    variant=None,
    reference_type: str = "",
    reference_id: str = "",
    performed_by=None,
) -> list[StockMovement]:
    """
    An immediate sale with no reservation — **for the point of sale**.

    Reservation serves a cart that may be abandoned; a counter sale is
    instantaneous: the customer is standing there and the goods are handed over
    at once.
    """
    if quantity <= 0:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الكمية يجب أن تكون موجبة")

    location = location or StockLocation.get_default()
    stock = _locked_stock(product, location, variant)

    if stock.available < quantity:
        raise BusinessError(
            ErrorCode.INSUFFICIENT_STOCK,
            detail=f"المتاح: {stock.available} · المطلوب: {quantity}",
        )

    movements = _consume_batches(
        stock=stock,
        quantity=quantity,
        reference_type=reference_type,
        reference_id=reference_id,
        performed_by=performed_by,
    )

    Stock.objects.filter(pk=stock.pk).update(quantity_physical=F("quantity_physical") - quantity)

    check_alerts(product, location)
    return movements


def _consume_batches(
    *, stock: Stock, quantity: int, reference_type, reference_id, performed_by
) -> list[StockMovement]:
    """
    Consume batches in **FEFO** order — nearest to expiry first.

    ⚠️  FEFO, not FIFO.

        Ordering by oldest received leaves a batch expiring tomorrow on the
        shelf while a batch good for a year gets sold — so the first is wasted.

    Batches with no expiry date come last (`nulls_last`).
    """
    batches = list(
        Batch.objects.select_for_update()
        .filter(
            product=stock.product,
            variant=stock.variant,
            location=stock.location,
            quantity_remaining__gt=0,
            is_quarantined=False,
        )
        .order_by(F("expires_at").asc(nulls_last=True), "received_at")
    )

    movements: list[StockMovement] = []
    remaining = quantity

    for batch in batches:
        if remaining <= 0:
            break
        if batch.is_expired:
            continue

        take = min(batch.quantity_remaining, remaining)

        Batch.objects.filter(pk=batch.pk).update(quantity_remaining=F("quantity_remaining") - take)
        remaining -= take

        movements.append(
            _record_movement(
                stock=stock,
                movement_type=MovementType.SALE,
                quantity=take,
                batch=batch,
                unit_cost=batch.unit_cost,  # The cost snapshot — required for COGS
                reference_type=reference_type,
                reference_id=reference_id,
                performed_by=performed_by,
            )
        )

    if remaining > 0:
        # Stock with no batches — recorded with no batch reference
        movements.append(
            _record_movement(
                stock=stock,
                movement_type=MovementType.SALE,
                quantity=remaining,
                reference_type=reference_type,
                reference_id=reference_id,
                performed_by=performed_by,
                note="بلا دفعة مرتبطة",
            )
        )

    return movements


@transaction.atomic
def adjust(
    product,
    quantity: int,
    *,
    location=None,
    variant=None,
    reason: str,
    performed_by=None,
) -> StockMovement:
    """
    A manual adjustment. `quantity` is positive for an increase and negative for a decrease.

    The reason is mandatory — an adjustment with no documented reason is a hole
    in any later stock count.
    """
    if quantity == 0:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="التسوية بصفر بلا معنى")
    if not reason:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="سبب التسوية إلزامي")

    location = location or StockLocation.get_default()
    stock = _locked_stock(product, location, variant)

    if quantity < 0 and stock.available < abs(quantity):
        raise BusinessError(
            ErrorCode.INSUFFICIENT_STOCK,
            detail=f"المتاح: {stock.available} · المطلوب خصمه: {abs(quantity)}",
        )

    Stock.objects.filter(pk=stock.pk).update(quantity_physical=F("quantity_physical") + quantity)
    stock.refresh_from_db()

    movement = _record_movement(
        stock=stock,
        movement_type=(
            MovementType.ADJUSTMENT_UP if quantity > 0 else MovementType.ADJUSTMENT_DOWN
        ),
        quantity=abs(quantity),
        note=reason,
        performed_by=performed_by,
    )

    check_alerts(product, location)
    return movement


# ═══════════════════════════════════════════════════════════
#  Giving a product's un-assigned stock to a variant (a colour)
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  A product that had no variants holds its stock on `variant=None`. The moment
#      it gets its first colour the cart requires a variant, so those units become
#      unsellable — and the shop must decide which colour they really are. Guessing
#      ("the first colour") would be wrong half the time and invisible; leaving them
#      would silently orphan the whole stock of the product. So it is an explicit,
#      one-time step, and it moves the units through recorded movements.


def unassigned_stock(product) -> list[dict]:
    """
    The units held on **no variant**, per location — `[{location, location_code, quantity}]`.

    "Units" are the *available* ones: reserved, damaged and expired units cannot be
    moved to another colour (a reservation is bound to the row it was taken on).
    """
    rows = (
        Stock.objects.filter(product=product, variant__isnull=True)
        .select_related("location")
        .order_by("location__code")
    )
    return [
        {"location": row.location, "location_code": row.location.code, "quantity": row.available}
        for row in rows
        if row.available > 0
    ]


def _move_batches(product, location, to_variant, quantity: int) -> None:
    """
    Re-point `quantity` units' worth of un-assigned batches at `to_variant`, FEFO.

    ⚠️  The batches travel with the stock — a sale consumes batches of the *same*
        variant (`_consume_batches`), so leaving them behind would sell the colour
        "without a batch": no cost recorded, and COGS wrong for every unit.

        A batch bigger than what remains to move is **split**, the cost and expiry
        copied — both halves keep `received - remaining` (what was already sold)
        intact, so the `batch_remaining_not_above_received` constraint holds.
    """
    batches = list(
        Batch.objects.select_for_update()
        .filter(
            product=product,
            variant__isnull=True,
            location=location,
            quantity_remaining__gt=0,
            is_quarantined=False,
        )
        .order_by(F("expires_at").asc(nulls_last=True), "received_at")
    )

    remaining = quantity
    for batch in batches:
        if remaining <= 0:
            break

        take = min(batch.quantity_remaining, remaining)
        if take == batch.quantity_remaining:
            Batch.objects.filter(pk=batch.pk).update(variant=to_variant)
        else:
            Batch.objects.create(
                product=product,
                variant=to_variant,
                location=location,
                number=batch.number,
                supplier_batch_number=batch.supplier_batch_number,
                quantity_received=take,
                quantity_remaining=take,
                unit_cost=batch.unit_cost,
                manufactured_at=batch.manufactured_at,
                expires_at=batch.expires_at,
                received_at=batch.received_at,
            )
            Batch.objects.filter(pk=batch.pk).update(
                quantity_received=F("quantity_received") - take,
                quantity_remaining=F("quantity_remaining") - take,
            )
        remaining -= take


@transaction.atomic
def assign_unvariated_stock(product, variant, *, location=None, performed_by=None) -> dict:
    """
    Move the product's un-assigned stock onto `variant` — every location, or one.

    Returns `{"moved": total, "locations": [{"location_code", "quantity"}]}`.

    Each location produces **two recorded movements** (a decrease on the old row, an
    increase on the new one) sharing `reference_type="variant_assignment"`, so the
    log shows exactly where the units went; the total on the shelf is unchanged.

    ⚠️  Only the **available** units move.

        Reserved units stay on the old row: their reservation is bound to it and is
        committed or released against it. Damaged and expired units are not for
        sale and have no business inflating a colour's balance.

    ⚠️  Alerts are *not* re-evaluated.

        The product's total on the shelf is unchanged, so nothing about "is it low /
        out of stock" has changed — and the emptied row on its own would read as
        "out of stock" for a product whose units are right there on the colour.
    """
    if variant is None or variant.product_id != product.pk:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="النسخة لا تخص هذا المنتج")
    if not variant.is_active:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="النسخة غير مفعّلة")

    candidates = Stock.objects.filter(product=product, variant__isnull=True)
    if location is not None:
        candidates = candidates.filter(location=location)

    moved_total = 0
    per_location = []

    for row in candidates.select_related("location"):
        source = _locked_stock(product, row.location, None)
        quantity = source.available
        if quantity <= 0:
            continue

        target = _locked_stock(product, row.location, variant)

        Stock.objects.filter(pk=source.pk).update(
            quantity_physical=F("quantity_physical") - quantity
        )
        Stock.objects.filter(pk=target.pk).update(
            quantity_physical=F("quantity_physical") + quantity
        )
        source.refresh_from_db()
        target.refresh_from_db()

        reference = {"reference_type": "variant_assignment", "reference_id": str(variant.pk)}
        _record_movement(
            stock=source,
            movement_type=MovementType.ADJUSTMENT_DOWN,
            quantity=quantity,
            note=f"نقل المخزون غير المخصَّص إلى {variant.name_ar}",
            performed_by=performed_by,
            **reference,
        )
        _record_movement(
            stock=target,
            movement_type=MovementType.ADJUSTMENT_UP,
            quantity=quantity,
            note="مخزون غير مخصَّص نُقل إلى هذه النسخة",
            performed_by=performed_by,
            **reference,
        )

        _move_batches(product, row.location, variant, quantity)

        moved_total += quantity
        per_location.append({"location_code": row.location.code, "quantity": quantity})

    return {"moved": moved_total, "locations": per_location}


# ═══════════════════════════════════════════════════════════
#  Stock counting
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def open_count(location: StockLocation, *, note: str = "", actor=None) -> StockCount:
    """
    Opens a stock count session.

    ⚠️  **One open session per location.**

        Two sessions on the same warehouse mean two counters each writing their
        own quantity, and whoever approves last erases the first one's work —
        with no conflict ever showing.
    """
    existing = StockCount.objects.filter(
        location=location,
        status__in=[StockCountStatus.DRAFT, StockCountStatus.IN_PROGRESS],
    ).first()

    if existing is not None:
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail=f"جلسة جرد مفتوحة سلفًا على {location.code}: {existing.reference}",
            status_code=409,
        )

    return StockCount.objects.create(location=location, note=note)


@transaction.atomic
def snapshot_count(count: StockCount) -> int:
    """
    Fills the session with the location's balances **at the moment it starts**.

    ⚠️  **The snapshot is taken at the start, not at approval.**

        A stock count takes hours, and the stock moves during them. Reading the
        expected balance at approval time compares what was counted in the
        morning against the evening's balance — showing a shortfall equal to
        everything sold during the count.

    ⚠️  And the counted quantity starts at the expected figure, not at zero.

        Starting at zero makes every item not yet counted look like a total
        shortfall; and in a partial count approved before completion, the whole
        warehouse is written down.
    """
    if count.status != StockCountStatus.DRAFT:
        raise BusinessError(
            ErrorCode.CONFLICT, detail="اللقطة تُؤخذ مرة واحدة عند البدء", status_code=409
        )

    rows = Stock.objects.filter(location=count.location).select_related("product", "variant")

    created = 0
    for stock in rows:
        StockCountLine.objects.update_or_create(
            count=count,
            product=stock.product,
            variant=stock.variant,
            defaults={
                "expected_quantity": stock.quantity_physical,
                "counted_quantity": stock.quantity_physical,
            },
        )
        created += 1

    count.status = StockCountStatus.IN_PROGRESS
    count.started_at = timezone.now()
    count.save(update_fields=["status", "started_at", "updated_at"])
    return created


@transaction.atomic
def record_counted(count: StockCount, line: StockCountLine, counted: int, *, note: str = ""):
    """
    ⚠️  The discrepancy is **computed, never entered** — entering it allows a
        shortfall to be hidden.
    """
    if count.status != StockCountStatus.IN_PROGRESS:
        raise BusinessError(ErrorCode.CONFLICT, detail="الجلسة غير جارية", status_code=409)

    if counted < 0:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الكمية لا تكون سالبة")

    line.counted_quantity = counted
    line.note = note
    line.save(update_fields=["counted_quantity", "note", "updated_at"])
    return line


@transaction.atomic
def apply_count(count: StockCount, *, actor=None) -> dict:
    """
    Approves the stock count: **it settles the discrepancies with `COUNT` movements and closes the
    session**.

    ⚠️  Settlement happens through a recorded movement, not by writing the balance directly.

        A direct write makes the balance change with no trace: the accountant
        asks "where did this shortfall come from?" and finds no movement. And a
        `COUNT` movement carries the discrepancy, who approved it, and when.

    ⚠️  And lines with no discrepancy **produce no movement**.

        A zero movement for every item in the warehouse floods the log with
        thousands of meaningless rows, making a search for a real discrepancy
        impossible.
    """
    if count.status != StockCountStatus.IN_PROGRESS:
        raise BusinessError(ErrorCode.CONFLICT, detail="لا يُعتمد إلا جرد جارٍ", status_code=409)

    adjusted = 0
    surplus = 0
    shortage = 0

    for line in count.lines.select_related("product", "variant"):
        variance = line.variance
        if variance == 0:
            continue

        stock = _locked_stock(line.product, count.location, line.variant)

        Stock.objects.filter(pk=stock.pk).update(
            quantity_physical=F("quantity_physical") + variance
        )
        stock.refresh_from_db()

        _record_movement(
            stock=stock,
            movement_type=MovementType.COUNT,
            quantity=abs(variance),
            note=(
                f"جرد {count.reference}: "
                f"متوقَّع {line.expected_quantity} · معدود {line.counted_quantity}"
            ),
            reference_type="stock_count",
            reference_id=str(count.pk),
            performed_by=actor,
        )

        adjusted += 1
        if variance > 0:
            surplus += variance
        else:
            shortage += abs(variance)

        check_alerts(line.product, count.location)

    count.status = StockCountStatus.COMPLETED
    count.completed_at = timezone.now()
    count.save(update_fields=["status", "completed_at", "updated_at"])

    return {"adjusted": adjusted, "surplus": surplus, "shortage": shortage}


@transaction.atomic
def cancel_count(count: StockCount, *, reason: str) -> StockCount:
    """
    ⚠️  Cancelling **does not touch the stock** — the session was never approved.

        And a completed one is not cancelled: its discrepancies have become
        recorded movements, and cancelling it leaves a balance adjusted by a
        session that says it was cancelled.
    """
    if count.status == StockCountStatus.COMPLETED:
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail="الجرد مكتمل — التصحيح بجرد جديد لا بإلغاء",
            status_code=409,
        )

    count.status = StockCountStatus.CANCELLED
    count.note = f"{count.note}\n— أُلغي: {reason}".strip()
    count.save(update_fields=["status", "note", "updated_at"])
    return count


@transaction.atomic
def return_to_supplier(
    product,
    quantity: int,
    *,
    location=None,
    variant=None,
    reason: str,
    reference_type: str = "",
    reference_id: str = "",
    performed_by=None,
) -> StockMovement:
    """
    Goods going out **to the supplier** — neither an adjustment nor a sale.

    ⚠️  A `RETURN_OUT` movement, not `ADJUSTMENT_DOWN`.

        An adjustment means "the balance was wrong"; a return means "the goods
        went out to a known party against payment". Conflating them makes the
        discrepancy report count every return as a counting error — and hides
        that the warehouse regularly returns goods to one particular supplier.

    ⚠️  And the reference is mandatory in practice: without `reference_id` the
        return is not linked to the purchase order it came from.
    """
    if quantity <= 0:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الكمية يجب أن تكون موجبة")
    if not reason:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="سبب الإرجاع إلزامي")

    location = location or StockLocation.get_default()
    stock = _locked_stock(product, location, variant)

    if stock.available < quantity:
        raise BusinessError(
            ErrorCode.INSUFFICIENT_STOCK,
            detail=f"المتاح: {stock.available} · المطلوب إرجاعه: {quantity}",
        )

    Stock.objects.filter(pk=stock.pk).update(quantity_physical=F("quantity_physical") - quantity)
    stock.refresh_from_db()

    movement = _record_movement(
        stock=stock,
        movement_type=MovementType.RETURN_OUT,
        quantity=quantity,
        note=reason,
        reference_type=reference_type,
        reference_id=reference_id,
        performed_by=performed_by,
    )

    check_alerts(product, location)
    return movement


@transaction.atomic
def transfer(
    product,
    quantity: int,
    *,
    from_location: StockLocation,
    to_location: StockLocation,
    variant=None,
    performed_by=None,
) -> tuple[StockMovement, StockMovement]:
    """
    A transfer between two locations — two movements in one transaction.

    Separating them means goods vanishing from the first and not appearing in
    the second on any partial failure.
    """
    if from_location == to_location:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الموقعان متطابقان")

    source = _locked_stock(product, from_location, variant)
    if source.available < quantity:
        raise BusinessError(
            ErrorCode.INSUFFICIENT_STOCK,
            detail=f"المتاح في {from_location.code}: {source.available}",
        )

    destination = _locked_stock(product, to_location, variant)

    Stock.objects.filter(pk=source.pk).update(quantity_physical=F("quantity_physical") - quantity)
    Stock.objects.filter(pk=destination.pk).update(
        quantity_physical=F("quantity_physical") + quantity
    )
    source.refresh_from_db()
    destination.refresh_from_db()

    out_movement = _record_movement(
        stock=source,
        movement_type=MovementType.TRANSFER_OUT,
        quantity=quantity,
        note=f"إلى {to_location.code}",
        performed_by=performed_by,
    )
    in_movement = _record_movement(
        stock=destination,
        movement_type=MovementType.TRANSFER_IN,
        quantity=quantity,
        note=f"من {from_location.code}",
        performed_by=performed_by,
    )

    check_alerts(product, from_location)
    resolve_alerts(product, to_location)
    return out_movement, in_movement


@transaction.atomic
def mark_damaged(
    product, quantity: int, *, location=None, variant=None, reason: str, performed_by=None
) -> StockMovement:
    """Mark a quantity as damaged — it stays in physical and leaves available."""
    location = location or StockLocation.get_default()
    stock = _locked_stock(product, location, variant)

    if stock.available < quantity:
        raise BusinessError(ErrorCode.INSUFFICIENT_STOCK, detail=f"المتاح: {stock.available}")

    Stock.objects.filter(pk=stock.pk).update(quantity_damaged=F("quantity_damaged") + quantity)
    stock.refresh_from_db()

    movement = _record_movement(
        stock=stock,
        movement_type=MovementType.DAMAGE,
        quantity=quantity,
        note=reason,
        performed_by=performed_by,
    )
    check_alerts(product, location)
    return movement


# ═══════════════════════════════════════════════════════════
#  Periodic tasks
# ═══════════════════════════════════════════════════════════


def release_expired_reservations() -> int:
    """
    Release expired reservations.

    ⚠️  Without this task, abandoned carts' reservations accumulate until
        everything looks out of stock while it is available.
    """
    expired = StockReservation.objects.filter(
        status=ReservationStatus.ACTIVE, expires_at__lt=timezone.now()
    )

    count = 0
    for reservation in expired:
        try:
            release(reservation, expired=True)
            count += 1
        except Exception:
            logger.exception("فشل الإفراج عن الحجز %s", reservation.pk)

    return count


@transaction.atomic
def quarantine_expired_batches() -> int:
    """
    Move expired batches into expired stock.

    ⚠️  An expired batch remaining in available stock means selling an expired medicine.
    """
    today = timezone.localdate()
    expired = Batch.objects.filter(
        expires_at__lt=today, quantity_remaining__gt=0, is_quarantined=False
    ).select_related("product", "location")

    count = 0
    for batch in expired:
        stock = _locked_stock(batch.product, batch.location, batch.variant)

        Stock.objects.filter(pk=stock.pk).update(
            quantity_expired=F("quantity_expired") + batch.quantity_remaining
        )
        stock.refresh_from_db()

        _record_movement(
            stock=stock,
            movement_type=MovementType.EXPIRY,
            quantity=batch.quantity_remaining,
            batch=batch,
            note=f"انتهت في {batch.expires_at}",
        )

        Batch.objects.filter(pk=batch.pk).update(is_quarantined=True)

        StockAlert.objects.get_or_create(
            alert_type=AlertType.EXPIRED,
            product=batch.product,
            location=batch.location,
            is_resolved=False,
            defaults={"batch": batch, "current_value": batch.quantity_remaining},
        )
        count += 1

    return count


def check_expiring_batches(days: int = EXPIRY_WARNING_DAYS) -> int:
    """An alert on batches approaching expiry."""
    threshold = timezone.localdate() + timedelta(days=days)
    batches = Batch.objects.filter(
        expires_at__lte=threshold,
        expires_at__gte=timezone.localdate(),
        quantity_remaining__gt=0,
        is_quarantined=False,
    ).select_related("product", "location")

    count = 0
    for batch in batches:
        _, created = StockAlert.objects.get_or_create(
            alert_type=AlertType.EXPIRING_SOON,
            product=batch.product,
            location=batch.location,
            is_resolved=False,
            defaults={
                "batch": batch,
                "current_value": batch.days_to_expiry() or 0,
                "threshold_value": days,
            },
        )
        if created:
            count += 1

    return count


# ═══════════════════════════════════════════════════════════
#  Alerts
# ═══════════════════════════════════════════════════════════


def check_alerts(product, location) -> StockAlert | None:
    """
    ⚠️  `get_or_create` conditioned on `is_resolved=False` — not a direct create.

        An out-of-stock product generates an alert on every attempted sale;
        dozens of alerts for the same situation within an hour make the alerts
        screen useless.
    """
    stock = Stock.objects.filter(product=product, location=location).first()
    if stock is None:
        return None

    available = stock.available

    if available == 0:
        alert_type = AlertType.OUT_OF_STOCK
        threshold = 0
    elif stock.is_critical:
        alert_type = AlertType.CRITICAL_STOCK
        threshold = stock.critical_point
    elif stock.needs_reorder:
        alert_type = AlertType.LOW_STOCK
        threshold = stock.reorder_point
    else:
        resolve_alerts(product, location)
        return None

    alert, _created = StockAlert.objects.get_or_create(
        alert_type=alert_type,
        product=product,
        location=location,
        is_resolved=False,
        defaults={"current_value": available, "threshold_value": threshold},
    )
    return alert


def resolve_alerts(product, location) -> int:
    """Resolve out-of-stock and low-stock alerts once the stock returns."""
    stock = Stock.objects.filter(product=product, location=location).first()
    if stock is None:
        return 0

    resolvable = Q(alert_type=AlertType.OUT_OF_STOCK) if stock.available > 0 else Q()

    if not stock.needs_reorder:
        resolvable |= Q(alert_type=AlertType.LOW_STOCK)
    if not stock.is_critical:
        resolvable |= Q(alert_type=AlertType.CRITICAL_STOCK)

    if not resolvable:
        return 0

    return StockAlert.objects.filter(
        resolvable, product=product, location=location, is_resolved=False
    ).update(is_resolved=True, resolved_at=timezone.now())


# ═══════════════════════════════════════════════════════════
#  The reference-based interface — for the upper domains
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  `orders` and `cart` **do not import the inventory models**.
#
#      Importing `StockReservation` there to query an order's reservations
#      means an upper domain knowing a lower domain's table structure — so any
#      change to that structure becomes a break in two places.
#
#      These functions take the string reference and return the result, so the
#      caller needs to know no model at all.


def default_location() -> StockLocation | None:
    """The default location — with no need to import `StockLocation`."""
    return StockLocation.get_default()


def active_reservations_for(reference_type: str, reference_id) -> list[StockReservation]:
    return list(
        StockReservation.objects.filter(
            reference_type=reference_type,
            reference_id=str(reference_id),
            status=ReservationStatus.ACTIVE,
        )
    )


@transaction.atomic
def commit_for_reference(reference_type: str, reference_id) -> int:
    """Fulfil all of a reference's reservations — on shipping."""
    count = 0
    for reservation in active_reservations_for(reference_type, reference_id):
        commit(reservation)
        count += 1
    return count


@transaction.atomic
def release_for_reference(reference_type: str, reference_id) -> int:
    """Release all of a reference's reservations — on cancellation."""
    count = 0
    for reservation in active_reservations_for(reference_type, reference_id):
        release(reservation)
        count += 1
    return count
