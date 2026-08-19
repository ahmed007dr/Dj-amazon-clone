"""
Finance listeners.

⚠️  **`orders` and `pos` know nothing about finance.**

    Both emit a signal without knowing who listens; and finance imports the
    orders domain (a downward import), not the reverse. Wiring it the other way
    would invert the direction.

⚠️  And a failed posting **does not fail the sale**.

    An accounting entry that was not written must not cancel a completed order
    or a sale whose goods have been handed over. The failure is logged and
    swallowed — and fixed by re-running the capture.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from finance import services

logger = logging.getLogger(__name__)


def _safe(handler):
    """
    ⚠️  The listener runs inside the original operation's transaction.

        An uncaught exception rolls the whole sale back for the sake of an entry
        that was not written — and the goods have already been handed over at the counter.
    """

    def wrapper(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        except Exception:
            logger.exception("فشل مستمع المالية %s", handler.__name__)
            return None

    wrapper.__name__ = handler.__name__
    return wrapper


def _register():
    from orders.events import order_completed
    from orders.models import Order, OrderStatus
    from pos.events import pos_sale_completed

    @receiver(pos_sale_completed, weak=False)
    @_safe
    def on_pos_sale_completed(sender, session, order, **kwargs):
        """
        ⚠️  **Recomputing the cost after linking the stock movements to the order.**

            Point of sale deducts stock **before** creating the order (so no
            orphan order remains should an item run out), so the movements are
            attached to the shift and then redirected to the order once it exists.

            But `post_save` on the order fires before that redirection, so the
            first cost calculation happens on **zero movements**. Without this
            listener every counter sale stays posted at zero cost — that is, at
            a profit equal to the full selling price, the worst possible
            direction for an error because the report looks excellent.
        """
        entry = services.RevenueEntry.objects.filter(
            source=services.RevenueSource.ORDER, order=order
        ).first()
        if entry is not None:
            services.record_cogs(entry)

    @receiver(order_completed, weak=False)
    @_safe
    def on_order_completed(sender, order, **kwargs):
        services.record_order_revenue(order)

    @receiver(post_save, sender=Order, weak=False)
    @_safe
    def on_order_saved(sender, instance, created, **kwargs):
        """
        ⚠️  **A counter sale does not pass through `order_completed`.**

            Point of sale creates the order directly in its final state
            (`DELIVERED`/`PAID`) without passing through the state machine — so
            no completion signal is emitted. Relying on the signal alone meant
            **all branch sales were absent from the profit statement** while the
            report looked sound.

        ⚠️  And returns are captured here too: `REFUNDED` is a state written on
            the order, not an independent event.
        """
        if instance.status == OrderStatus.REFUNDED:
            services.record_refund(instance)
            return

        # A completed or delivered order — and the capture does not double up thanks
        # to the unique constraint on (source, order).
        if instance.status in (OrderStatus.COMPLETED, OrderStatus.DELIVERED):
            services.record_order_revenue(instance)


_register()
