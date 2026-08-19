"""
Loyalty listeners.

⚠️  **`orders` and `pos` know nothing about loyalty.**

    Both emit a signal, and this file translates it into points. The import is
    downward: `loyalty` knows orders, never the reverse.

⚠️  And a failed award **does not fail the order**.

    A point that was not posted is fixed by re-running the capture; an order
    rolled back for the sake of a point is a loss that cannot be fixed. The
    failure is logged and swallowed.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from loyalty import services

logger = logging.getLogger(__name__)


def _safe(handler):
    """
    ⚠️  The listener runs inside the original operation's transaction.

        An uncaught exception rolls the whole sale back for the sake of points
        that were not awarded — and the goods have already been handed over at
        the counter.
    """

    def wrapper(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        except Exception:
            logger.exception("فشل مستمع الولاء %s", handler.__name__)
            return None

    wrapper.__name__ = handler.__name__
    return wrapper


def _register():
    from orders.events import order_completed
    from orders.models import Order, OrderStatus

    @receiver(order_completed, weak=False)
    @_safe
    def on_order_completed(sender, order, **kwargs):
        services.award_for_order(order)
        services.reward_referral(order)

    @receiver(post_save, sender=Order, weak=False)
    @_safe
    def on_order_saved(sender, instance, created, **kwargs):
        """
        ⚠️  **A counter sale does not pass through `order_completed`.**

            Point of sale creates the order directly in its final state without
            passing through the state machine, so no completion signal is
            emitted. Relying on the signal means **the branch's customer earns
            nothing** while the website's customer earns on the same order — a
            disparity that reads as a fault.

        ⚠️  And returns are captured here too: `REFUNDED` is a state written on
            the order, not an independent event. Without the withdrawal the
            open path remains: buy · earn · return · and keep the points.

        ⚠️  Duplication is prevented not by this check but by the unique
            constraint on (order, type) in the ledger: the order is saved several times.
        """
        if instance.status == OrderStatus.REFUNDED:
            services.reverse_for_order(instance)
            return

        if instance.status in (OrderStatus.COMPLETED, OrderStatus.DELIVERED):
            services.award_for_order(instance)
            services.reward_referral(instance)


_register()
