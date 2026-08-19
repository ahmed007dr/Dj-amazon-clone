"""
Order listeners for payment events.

⚠️  **This is the side that makes an electronic payment reach the order.**

    `charge()` issues a gateway link or a payment number at a terminal, and does
    not know whether the customer paid. The confirmation arrives by webhook
    minutes or hours later and marks the `PaymentTransaction` as captured — and
    without this file it stops there: the money is in the account and the order
    is "unpaid" on the admin screen.

⚠️  And **the direction is deliberately inverted**: `payments` sits below
    `orders` in the layer diagram (see the import-linter contract in
    `pyproject.toml`), so it must not import `orders` to mark the order itself.
    Payment announces, and the order listens.

⚠️  And **failure here is not swallowed** — unlike the `finance` and
    `notifications` listeners.

    Those write an entry or send a message: their failure must not roll back a
    completed sale. This one records **that the money was taken**. Swallowing
    its failure means a successful response to the gateway for an event that was
    never applied — so it stops resending and the confirmation is lost for good.
    Raising produces a 500 that makes the gateway retry, which is exactly what
    we want.
"""

from __future__ import annotations

import logging
from uuid import UUID

from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _register() -> None:
    # ⚠️  Imported inside the function rather than at the top of the file — it is
    #     called from `AppConfig.ready` after the app registry is complete.
    from core.errors import BusinessError, ErrorCode
    from orders import services
    from orders.events import order_paid
    from orders.models import Order, OrderStatus, PaymentStatus
    from payments.events import payment_captured, payment_failed, payment_refunded

    def _order_for(payment) -> Order | None:
        """
        ⚠️  The reference is **a string**, not a foreign key: `payments` knows
            nothing about orders. And filtering by type is mandatory — a
            point-of-sale sale and a credit payment pass through the same table
            with references of other kinds.

        ⚠️  And **it is validated as a UUID before the query.**

            `reference_id` is a free-text field every domain writes what it
            likes into, and `Order`'s key is a UUID. Passing an invalid string
            to `filter(pk=…)` raises `ValidationError` **before** it reaches the
            database — so the webhook collapses with a 500 and the gateway keeps
            resending an event that will never succeed. And an unfamiliar
            reference is not an error: it is simply a payment that does not
            belong to orders.
        """
        if payment.reference_type != services.REFERENCE_TYPE:
            return None
        if not payment.reference_id:
            return None

        try:
            key = UUID(str(payment.reference_id))
        except (ValueError, AttributeError, TypeError):
            logger.warning(
                "مرجع طلب غير صالح في المعاملة %s: %r",
                payment.reference,
                payment.reference_id,
            )
            return None

        return Order.objects.filter(pk=key).first()

    @receiver(payment_captured, weak=False)
    def on_payment_captured(sender, payment, **kwargs):
        order = _order_for(payment)
        if order is None:
            return

        try:
            services.mark_paid(order)
        except BusinessError as exc:
            # ⚠️  "Already paid" is not a failure but **the desired state**.
            #
            #     The gateway resends, and two confirmations may arrive with
            #     different ids for the same order (a failed attempt then a
            #     successful one). Raising here produced a 500 that retried
            #     forever on an order that lacks nothing.
            if exc.code == ErrorCode.ORDER_ALREADY_PAID:
                return
            raise

        logger.info("الطلب %s عُلِّم مدفوعًا بتأكيد %s", order.number, payment.reference)
        order_paid.send(sender=Order, order=order, payment_reference=payment.reference)

    @receiver(payment_refunded, weak=False)
    def on_payment_refunded(sender, payment, **kwargs):
        """
        ⚠️  The payment status alone — **the order status is not touched**.

            A refund does not automatically mean the order is cancelled: goods
            may have been delivered and then partially refunded. Moving the
            order's status is an operational decision the admin takes from their
            screen, and this listener records what happened at the gateway, not
            what ought to happen to the order.
        """
        order = _order_for(payment)
        if order is None or order.payment_status == PaymentStatus.REFUNDED:
            return

        order.payment_status = PaymentStatus.REFUNDED
        order.save(update_fields=["payment_status"])
        logger.info("الطلب %s عُلِّم مستردًا بتأكيد %s", order.number, payment.reference)

    @receiver(payment_failed, weak=False)
    def on_payment_failed(sender, payment, **kwargs):
        """
        ⚠️  **A paid order does not become unpaid again.**

            A failed attempt may arrive **after** a successful one (a late
            resend of an old event). Applying it with no guard erases a genuine
            payment and makes the order look unsettled.
        """
        order = _order_for(payment)
        if order is None:
            return
        if order.payment_status not in (PaymentStatus.UNPAID, PaymentStatus.PENDING):
            return
        # ⚠️  And it is not marked failed after delivery: cash on delivery is
        #     collected in cash, and an old gateway failure does not touch it.
        if order.status in (OrderStatus.DELIVERED, OrderStatus.COMPLETED):
            return

        order.payment_status = PaymentStatus.FAILED
        order.save(update_fields=["payment_status"])


_register()
