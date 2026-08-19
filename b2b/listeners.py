"""
B2B listeners.

⚠️  **`orders` does not know credit terms exist.**

    The order emits its state, and this file translates it into a movement on
    the customer's account. The import is downward: `b2b` knows orders, never
    the reverse.

⚠️  And a failed posting **does not fail the order** — but it is logged at error level.

    A debt entry that was never written means goods left with no effect on the
    account, which is more dangerous than an email that was never sent: it is
    discovered as a discrepancy in the statement a month later. The swallow here
    exists only to prevent rolling the order back, and the log is what gets reviewed.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _register():
    from b2b import services
    from b2b.models import BusinessProfile
    from orders.models import Order, OrderStatus

    @receiver(post_save, sender=Order, weak=False)
    def on_order_refunded(sender, instance, created, **kwargs):
        """
        ⚠️  A return on a credit order is **posted as a credit note**.

            Without it the customer stays in debt for goods they returned — so
            they are blocked from buying against a limit consumed by a cancelled order.
        """
        if instance.status != OrderStatus.REFUNDED or instance.customer_id is None:
            return

        try:
            business = BusinessProfile.objects.filter(customer_id=instance.customer_id).first()
            if business is None:
                return
            services.record_credit_note(business, instance)
        except Exception:
            logger.exception("فشل تقييد الإشعار الدائن للطلب %s", instance.pk)


_register()
