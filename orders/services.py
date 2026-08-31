"""
Order services.

⚠️  **This domain does not touch the inventory models and does not implement the coupon engine.**

    The legacy code did both:

        product.quantity -= item.quantity      ← editing a catalog model
        product.save()

        # plus a complete copy of the coupon logic inside the view

    Here: `inventory.services` and `promotions.services` — a call, not a copy,
    and the direction is downward.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from cart import services as cart_services
from cart.models import Cart, CartStatus
from core.errors import BusinessError, ErrorCode
from core.money import ZERO
from inventory import services as inventory_services
from orders.models import (
    Order,
    OrderChannel,
    OrderLine,
    OrderStatus,
    OrderStatusHistory,
    PaymentStatus,
)
from promotions import services as promotion_services
from shipping import services as shipping_services
from shipping.models import ShippingMethod

logger = logging.getLogger(__name__)

REFERENCE_TYPE = "order"

# ═══════════════════════════════════════════════════════════
#  The state machine
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  The permitted transitions are **declared explicitly**.
#
#      Without a state machine, a "completed" order returns to "pending" in one
#      call — corrupting every sales report and every computed commission.

ALLOWED_TRANSITIONS = {
    OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.PROCESSING, OrderStatus.CANCELLED},
    OrderStatus.PROCESSING: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
    OrderStatus.DELIVERED: {OrderStatus.COMPLETED, OrderStatus.REFUNDED},
    OrderStatus.COMPLETED: {OrderStatus.REFUNDED},
    OrderStatus.CANCELLED: set(),  # terminal
    OrderStatus.REFUNDED: set(),  # terminal
}

#: The statuses in which stock stays reserved
RESERVING_STATUSES = {
    OrderStatus.PENDING,
    OrderStatus.CONFIRMED,
    OrderStatus.PROCESSING,
}


def can_transition(order: Order, to_status: str) -> bool:
    return to_status in ALLOWED_TRANSITIONS.get(order.status, set())


def can_cancel(order: Order) -> bool:
    return OrderStatus.CANCELLED in ALLOWED_TRANSITIONS.get(order.status, set())


# ═══════════════════════════════════════════════════════════
#  Creating the order
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def resolve_address(profile, data: dict) -> dict:
    """
    The shipping address — saved, or sent explicitly.

    ⚠️  **Filtered by the address's owner.**

        Without `customer=profile`, any user ships to any customer's address by
        guessing an id — and reads their name and phone number in the order response.

    ⚠️  And it is deliberately shared between the store checkout and the credit checkout.

        Two copies of the same filtering mean one gets forgotten at the first
        edit — and the forgotten one is the hole.
    """
    if data.get("address"):
        return dict(data["address"])

    from customers.models import CustomerAddress

    saved = CustomerAddress.objects.filter(pk=data["address_id"], customer=profile).first()
    if saved is None:
        # ⚠️  404 for both nonexistent and not-owned — the difference between them
        #     reveals the address's existence to someone who does not own it.
        raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

    return {
        "recipient_name": saved.recipient_name,
        "phone": saved.phone,
        "governorate": saved.governorate,
        "city": saved.city,
        "street": saved.street,
        "building": saved.building,
        "landmark": saved.landmark,
    }


def create_from_cart(
    cart: Cart,
    *,
    customer,
    address: dict,
    shipping_method_code: str = "",
    channel: str = OrderChannel.ONLINE,
    location=None,
    created_by=None,
    customer_note: str = "",
) -> Order:
    """
    Convert a cart into an order.

    ⚠️  **A full re-validation first — without exception.**

        Any prices and totals the frontend sends are ignored entirely. The cart
        is repriced and every line rechecked, so an order at a stale price, with
        a forbidden product, or with missing stock is refused here rather than
        after shipping.
    """
    user = cart.user

    snapshot = cart_services.revalidate(
        cart,
        user=user,
        governorate=address.get("governorate", ""),
        shipping_method_code=shipping_method_code,
    )

    # ⚠️  The problems come **before** the empty check.
    #
    #     When every line fails (stock ran out · the product was discontinued),
    #     `snapshot.lines` becomes empty — so putting the empty check first
    #     tells the customer "your cart is empty" while it is full and the real cause is entirely
    #     different.
    if snapshot.has_issues:
        first = snapshot.issues[0]
        raise BusinessError(
            first.code,
            detail=f"{first.product_name}: {first.message}",
            status_code=409,
        )

    if not snapshot.lines:
        raise BusinessError(ErrorCode.CART_EMPTY)

    priced = snapshot.priced

    # ── Creating the order ─────────────────────────────────
    order = Order.objects.create(
        customer=customer,
        channel=channel,
        location=location or inventory_services.default_location(),
        created_by=created_by,
        subtotal=priced.subtotal,
        discount_total=priced.discount_total,
        coupon_discount=priced.coupon_discount,
        tax_total=priced.tax_total,
        shipping_total=priced.shipping_amount,
        grand_total=priced.total,
        coupon_code=cart.coupon_code,
        shipping_method_code=shipping_method_code,
        recipient_name=address.get("recipient_name", ""),
        recipient_phone=address.get("phone", ""),
        governorate=address.get("governorate", ""),
        city=address.get("city", ""),
        street=address.get("street", ""),
        building=address.get("building", ""),
        landmark=address.get("landmark", ""),
        customer_note=customer_note,
    )

    # ── The lines with their snapshots ─────────────────────
    for (product, quantity, variant), line in snapshot.lines:
        OrderLine.objects.create(
            order=order,
            product=product,
            variant=variant,
            product_sku=product.sku,
            product_name_ar=product.name_ar,
            product_name_en=product.name_en,
            quantity=quantity,
            unit_price=line.unit_price,
            list_price=line.list_price,
            discount_amount=line.discount_amount,
            tax_rate=line.tax_rate,  # ⚠️ a snapshot — ADR-30
            tax_amount=line.tax_amount,
            tax_class_code=line.tax_class_code,
            price_list_code=line.price_list_code,
        )

        # ── Reserving stock ────────────────────────────────
        inventory_services.reserve(
            product,
            quantity,
            location=order.location,
            variant=variant,
            reference_type=REFERENCE_TYPE,
            reference_id=order.pk,
        )

    # ── Recording the coupon ───────────────────────────────
    if snapshot.coupon_result and snapshot.coupon_result.is_valid:
        promotion_services.redeem(
            snapshot.coupon_result.coupon,
            user,
            snapshot.coupon_result.discount_amount,
            order_amount=priced.total,
            reference_type=REFERENCE_TYPE,
            reference_id=order.pk,
        )

    # ── The shipment ───────────────────────────────────────
    if shipping_method_code:
        method = ShippingMethod.objects.filter(code=shipping_method_code).first()
        if method is not None:
            shipping_services.create_shipment(
                method=method,
                address=address,
                shipping_fee=priced.shipping_amount,
                reference_type=REFERENCE_TYPE,
                reference_id=order.pk,
            )

    _record_status(order, "", OrderStatus.PENDING, note="أُنشئ الطلب", actor=created_by)

    cart.status = CartStatus.CONVERTED
    cart.converted_at = timezone.now()
    cart.save(update_fields=["status", "converted_at"])

    return order


# ═══════════════════════════════════════════════════════════
#  Transitions
# ═══════════════════════════════════════════════════════════


def _record_status(order, from_status, to_status, *, note="", actor=None):
    OrderStatusHistory.objects.create(
        order=order,
        from_status=from_status,
        to_status=to_status,
        note=note,
        changed_by=actor,
    )


@transaction.atomic
def transition(order: Order, to_status: str, *, note: str = "", actor=None) -> Order:
    """
    Move the order to a new status.

    ⚠️  A disallowed transition is refused with `409`, never carried out silently.
    """
    if not can_transition(order, to_status):
        raise BusinessError(
            ErrorCode.INVALID_STATE_TRANSITION,
            detail=f"{order.status} ⟵ {to_status} غير مسموح",
            status_code=409,
        )

    previous = order.status
    order.status = to_status
    updates = ["status"]

    now = timezone.now()
    if to_status == OrderStatus.CONFIRMED:
        order.confirmed_at = now
        updates.append("confirmed_at")
    elif to_status == OrderStatus.COMPLETED:
        order.completed_at = now
        updates.append("completed_at")

    order.save(update_fields=updates)
    _record_status(order, previous, to_status, note=note, actor=actor)

    # ⚠️  Stock is fulfilled on shipping, not on confirmation.
    #     A confirmed order may be cancelled; a shipped one does not come back.
    if to_status == OrderStatus.SHIPPED:
        _commit_reservations(order)

    # ⚠️  Delivery **is** the collection for cash on delivery.
    if to_status == OrderStatus.DELIVERED:
        _collect_on_delivery(order)

    return order


def _collect_on_delivery(order: Order) -> int:
    """
    Capture the order's cash-on-delivery transactions once it has been handed over.

    ⚠️  **Cash on delivery is the only method captured here.**

        A card is captured by its gateway's inbound event, and doing it again
        from this side records a collection the gateway never made. Cash on
        delivery has no such event by construction: the money changes hands at
        the door, and the courier's confirmation of delivery is the only signal
        that it did.

    ⚠️  And the capture was left as **a second manual step** until now.

        `charge()` recorded the transaction as `AUTHORIZED` — correctly, since
        nothing had been collected yet — and every screen offering to capture it
        sat in the admin panel. So an order that was delivered and paid for in
        cash stayed "awaiting payment" until somebody remembered to open
        payments and press a button, and the revenue reports counted whatever
        was remembered rather than whatever was sold.

        The person who knows the money arrived is the one marking the order
        delivered. This is where it belongs.

    ⚠️  A failure here **does not undo the delivery.**

        The goods are with the customer whatever the payment record says.
        Raising would roll the transition back and leave a delivered order
        reading "shipped" — a lie about the physical world to protect the
        consistency of a number. The error is logged, the manual capture in the
        admin panel remains, and it is still idempotent.
    """
    from payments import services as payment_services
    from payments.models import PaymentMethodKind, TransactionStatus

    captured = 0

    for payment in payment_services.transactions_for(REFERENCE_TYPE, order.pk):
        if payment.method != PaymentMethodKind.CASH_ON_DELIVERY:
            continue
        if payment.status != TransactionStatus.AUTHORIZED:
            continue

        try:
            payment_services.capture(payment)
        except BusinessError:
            logger.exception(
                "تعذّر تحصيل معاملة %s للطلب %s عند التسليم",
                payment.reference,
                order.number,
            )
            continue

        captured += 1

    if captured:
        # ⚠️  `payment_captured` marked the order paid through a **different**
        #     instance of it — the listener loads it by id. Without this the
        #     caller returns the object it already held, still reading
        #     "awaiting payment" on the very response that collected the money.
        order.refresh_from_db(fields=["payment_status"])

    return captured


def _commit_reservations(order: Order) -> int:
    """
    Fulfil the order's reservations — the actual deduction from stock.

    ⚠️  Through the service by reference, not by querying the inventory models
        here. `orders` is in L6 and `inventory` in L3; knowing its table
        structure makes any change to it a break in two places.
    """
    return inventory_services.commit_for_reference(REFERENCE_TYPE, order.pk)


@transaction.atomic
def cancel(order: Order, *, reason: str, actor=None) -> Order:
    """
    Cancel an order.

    ⚠️  Three actions in one transaction:
          1. release the reserved stock
          2. reverse the coupon usage
          3. record the status and the reason

        Separating them leaves stock reserved for a cancelled order, or a coupon
        consumed for nothing.
    """
    if not can_cancel(order):
        raise BusinessError(
            ErrorCode.ORDER_CANNOT_BE_CANCELLED,
            detail=f"لا يمكن إلغاء طلب في حالة {order.status}",
            status_code=409,
        )

    if not reason:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="سبب الإلغاء إلزامي")

    previous = order.status

    _release_reservations(order)

    redemption = promotion_services.redemption_for(REFERENCE_TYPE, order.pk)
    if redemption is not None:
        promotion_services.cancel_redemption(redemption)

    order.status = OrderStatus.CANCELLED
    order.cancelled_at = timezone.now()
    order.cancellation_reason = reason
    order.save(update_fields=["status", "cancelled_at", "cancellation_reason"])

    _record_status(order, previous, OrderStatus.CANCELLED, note=reason, actor=actor)
    return order


def _release_reservations(order: Order) -> int:
    return inventory_services.release_for_reference(REFERENCE_TYPE, order.pk)


@transaction.atomic
def mark_paid(order: Order, *, actor=None) -> Order:
    """
    Mark the order as paid.

    ⚠️  Called from `payments` after the gateway confirms — not from the frontend.
    """
    if order.payment_status == PaymentStatus.PAID:
        raise BusinessError(ErrorCode.ORDER_ALREADY_PAID)

    order.payment_status = PaymentStatus.PAID
    order.save(update_fields=["payment_status"])

    # Payment confirms the order automatically
    if order.status == OrderStatus.PENDING:
        transition(order, OrderStatus.CONFIRMED, note="تأكيد بعد الدفع", actor=actor)

    return order


@transaction.atomic
def complete(order: Order, *, actor=None) -> Order:
    """
    Complete the order.

    ⚠️  This is where the events consumed by the upper domains are emitted:
        finance, loyalty, commissions and updating the customer's statistics.

        All of them **listen** and are never called — `orders` does not know
        they exist.
    """
    order = transition(order, OrderStatus.COMPLETED, actor=actor)

    from orders.events import order_completed

    order_completed.send(sender=Order, order=order)
    return order


def orders_for(customer):
    """A customer's orders — filtered by ownership."""
    return (
        Order.objects.filter(customer=customer)
        .select_related("customer", "location")
        .prefetch_related("lines")
    )


# ═══════════════════════════════════════════════════════════
#  Point of sale
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  **One order for every channel.**
#
#      The two functions below are the point of sale's entry into the same
#      order model — not a parallel one. `pos` calls them and never knows
#      `Order` directly, and `orders` knows nothing at all about `pos`: its inputs are items and
#      numbers.
#
#      The alternative (a separate `POSOrder`) means two sales reports, two
#      stock figures and two sources of truth — and the first accounting
#      question exposes the gap with no way to settle it.


@transaction.atomic
def create_pos_order(
    *,
    customer,
    location,
    cashier,
    lines: list[dict],
    totals: dict,
    note: str = "",
) -> Order:
    """
    A point-of-sale order — **confirmed, paid and delivered at once**.

    ⚠️  It starts at `DELIVERED`, not at `PENDING`.

        The goods were handed over at the counter and the money taken. Walking
        it through the state machine from "pending" to "delivered" produces five
        phantom events in the log for an operation that took a second, and
        floods the customer with five notifications about an order they are
        holding in their hand.

    ⚠️  And `customer` may be `None`: a counter sale requires no account. The
        order then has no owner — which is the normal case in a physical shop,
        not missing data.
    """
    order = Order.objects.create(
        customer=customer,
        channel=OrderChannel.POS,
        location=location,
        created_by=cashier,
        status=OrderStatus.DELIVERED,
        payment_status=PaymentStatus.PAID,
        subtotal=totals["subtotal"],
        discount_total=totals.get("discount_total", ZERO),
        tax_total=totals.get("tax_total", ZERO),
        shipping_total=ZERO,
        grand_total=totals["grand_total"],
        internal_note=note,
        confirmed_at=timezone.now(),
    )

    for entry in lines:
        product = entry["product"]
        OrderLine.objects.create(
            order=order,
            product=product,
            variant=entry.get("variant"),
            # ⚠️  Snapshots at the time of sale (ADR-30) — the invoice does not change
            #     when the product's name or price changes tomorrow.
            product_sku=product.sku,
            product_name_ar=product.name_ar,
            product_name_en=product.name_en,
            quantity=entry["quantity"],
            unit_price=entry["unit_price"],
            discount_amount=entry.get("discount_amount", ZERO),
            tax_rate=entry.get("tax_rate", ZERO),
            tax_amount=entry.get("tax_amount", ZERO),
            # ⚠️  No `line_total`: the line total is **a computed property**
            #     (`net + tax_amount`), not a column. Storing it means two numbers
            #     that may diverge — and which is correct is a question with no answer.
        )

    _record_status(order, "", OrderStatus.DELIVERED, note="بيع نقطة بيع", actor=cashier)

    return order


@transaction.atomic
def refund_pos_order(order: Order, *, reason: str, actor=None) -> Order:
    """
    Refund a point-of-sale sale.

    ⚠️  **No deletion.** The sale happened and its tax was collected; deleting
        it erases both from the day's report. The order remains and is marked
        `REFUNDED`, and returning the stock happens in `pos` because it concerns
        the register's location.
    """
    if order.channel != OrderChannel.POS:
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail="هذه الدالة لطلبات نقطة البيع وحدها",
            status_code=409,
        )

    if order.status == OrderStatus.REFUNDED:
        raise BusinessError(ErrorCode.CONFLICT, detail="هذا الطلب مسترد بالفعل", status_code=409)

    previous = order.status
    order.status = OrderStatus.REFUNDED
    order.payment_status = PaymentStatus.REFUNDED
    order.cancellation_reason = reason
    order.save(update_fields=["status", "payment_status", "cancellation_reason"])

    _record_status(order, previous, OrderStatus.REFUNDED, note=reason, actor=actor)

    return order
