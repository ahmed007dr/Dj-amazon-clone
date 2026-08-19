"""
Event listeners.

⚠️  **This file is the only party that knows both sides.**

    `orders` emits `order_completed` and does not know who listens.
    `notifications` listens and is imported by nobody.

    Wiring it here inverts the direction: instead of `orders` importing the
    notifications domain (an upward import), `notifications` imports the orders
    domain (a downward one).

⚠️  And a failure in any listener **does not fail the business operation**.

    An email that was not sent must not cancel a completed order. The failure is
    logged and swallowed.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from mailing import templates as mail_templates
from notifications import services
from notifications.models import NotificationCategory, NotificationPriority

logger = logging.getLogger(__name__)


def _safe(handler):
    """
    Swallows any failure in the listener and logs it.

    ⚠️  The listener runs inside the original operation's transaction — an
        uncaught exception rolls the whole order back over an email that was not sent.
    """

    def wrapper(*args, **kwargs):
        try:
            return handler(*args, **kwargs)
        except Exception:
            logger.exception("فشل مستمع الإشعارات %s", handler.__name__)
            return None

    wrapper.__name__ = handler.__name__
    return wrapper


# ═══════════════════════════════════════════════════════════
#  Orders
# ═══════════════════════════════════════════════════════════


def _order_context(order) -> dict:
    """
    The context for the order mail templates.

    ⚠️  **Every figure comes from the stored order** — a snapshot at the time of
        sale (ADR-30).

        Recomputing any amount here produces a message that contradicts the
        invoice, and the customer compares the two.
    """
    from accounts.services import frontend_url

    return {
        "number": order.number,
        "total": f"{order.grand_total} {order.currency}",
        "address": f"{order.governorate} — {order.city}، {order.street}",
        "reason": order.cancellation_reason or "—",
        "link": frontend_url(f"/orders/{order.pk}"),
    }


def _register_order_listeners():
    from orders.events import order_completed
    from orders.models import Order, OrderStatus

    @receiver(order_completed, weak=False)
    @_safe
    def on_order_completed(sender, order, **kwargs):
        # ⚠️  A counter sale with no registered customer — there is nobody to notify.
        #
        #     The buyer took their goods and their receipt and left; there is no
        #     email to send to and no account to see the notification. Ignoring that
        #     raised an `AttributeError` on every point-of-sale sale — swallowed by
        #     `_safe`, so the system looked healthy while the log filled with errors.
        if order.customer is None:
            return

        user = order.customer.user
        services.notify(
            user,
            category=NotificationCategory.ORDER,
            title=f"اكتمل طلبك {order.number}",
            body=f"تم تسليم طلبك بنجاح. إجماليه {order.grand_total} جنيه.",
            template_key=mail_templates.ORDER_DELIVERED.key,
            template_context=_order_context(order),
            action_url=f"/orders/{order.pk}",
            reference_type="order",
            reference_id=order.pk,
        )

    @receiver(post_save, sender=Order, weak=False)
    @_safe
    def on_order_status_changed(sender, instance, created, **kwargs):
        """
        ⚠️  A notification on changes that mean something to the customer only.

            A notification on every save floods the customer with messages that
            do not concern them — "processing" concerns them, editing an
            internal note does not.

        ⚠️  And a counter sale has no customer: there is no recipient at all.
        """
        if instance.customer is None:
            return

        user = instance.customer.user

        if created:
            services.notify(
                user,
                category=NotificationCategory.ORDER,
                title=f"استلمنا طلبك {instance.number}",
                body="طلبك قيد المراجعة وسنبلغك بتأكيده.",
                template_key=mail_templates.ORDER_PLACED.key,
                template_context=_order_context(instance),
                action_url=f"/orders/{instance.pk}",
                reference_type="order",
                reference_id=instance.pk,
            )
            return

        # ⚠️  The template is part of the message, not an addition to it.
        #
        #     The listener used to create an in-app notification with no email, so
        #     a customer who does not open the website never knew their order shipped.
        #     `notify` sends the email **when a template is passed** — and its absence
        #     was read as though it were a choice.
        messages = {
            OrderStatus.CONFIRMED: (
                "تأكد طلبك",
                "جارٍ تجهيز طلبك للشحن.",
                mail_templates.ORDER_CONFIRMED,
            ),
            OrderStatus.SHIPPED: ("شُحن طلبك", "طلبك في الطريق إليك.", mail_templates.ORDER_SHIPPED),
            OrderStatus.DELIVERED: (
                "سُلّم طلبك",
                "نتمنى أن ينال رضاك.",
                mail_templates.ORDER_DELIVERED,
            ),
            OrderStatus.CANCELLED: (
                "أُلغي طلبك",
                instance.cancellation_reason or "",
                mail_templates.ORDER_CANCELLED,
            ),
        }

        entry = messages.get(instance.status)
        if entry is None:
            return

        title, body, template = entry
        services.notify(
            user,
            category=NotificationCategory.ORDER,
            title=f"{title} {instance.number}",
            body=body,
            template_key=template.key,
            template_context=_order_context(instance),
            action_url=f"/orders/{instance.pk}",
            reference_type="order",
            reference_id=instance.pk,
            priority=(
                NotificationPriority.HIGH
                if instance.status == OrderStatus.CANCELLED
                else NotificationPriority.NORMAL
            ),
        )


# ═══════════════════════════════════════════════════════════
#  The account
# ═══════════════════════════════════════════════════════════


def _register_account_listeners():
    from accounts.models import AccountStatusChange

    @receiver(post_save, sender=AccountStatusChange, weak=False)
    @_safe
    def on_account_status_changed(sender, instance, created, **kwargs):
        """
        ⚠️  The `ACCOUNT` category is **mandatory** — it is not disabled by a preference.

            An account suspension passing unnoticed by its owner means a silent compromise.
        """
        if not created:
            return

        from accounts.models import AccountStatus

        suspended = instance.to_status in (
            AccountStatus.SUSPENDED,
            AccountStatus.BLOCKED,
        )

        services.notify(
            instance.user,
            category=NotificationCategory.ACCOUNT,
            title="أُوقف حسابك" if suspended else "أُعيد تفعيل حسابك",
            body=instance.reason,
            template_key=(
                mail_templates.ACCOUNT_SUSPENDED.key
                if suspended
                else mail_templates.ACCOUNT_ACTIVATED.key
            ),
            template_context={"reason": instance.reason},
            priority=NotificationPriority.URGENT,
            reference_type="account_status_change",
            reference_id=instance.pk,
        )


# ═══════════════════════════════════════════════════════════
#  Inventory — for the admin
# ═══════════════════════════════════════════════════════════


def _register_inventory_listeners():
    from inventory.models import StockAlert

    @receiver(post_save, sender=StockAlert, weak=False)
    @_safe
    def on_stock_alert(sender, instance, created, **kwargs):
        """
        ⚠️  A notification for the admin, not for the customer.

            An item running out is an operational matter — telling customers
            about it gives a competitor a picture of your stock.
        """
        if not created:
            return

        from administration.models import AdminProfile

        admins = AdminProfile.objects.select_related("user").all()
        for profile in admins:
            services.notify(
                profile.user,
                category=NotificationCategory.INVENTORY,
                title=f"تنبيه مخزون: {instance.product.sku}",
                body=(
                    f"{instance.get_alert_type_display()} — "
                    f"{instance.product.name_ar} في {instance.location.code}"
                ),
                action_url=f"/admin/inventory/alerts?product={instance.product_id}",
                reference_type="stock_alert",
                reference_id=instance.pk,
                priority=NotificationPriority.HIGH,
            )


# ═══════════════════════════════════════════════════════════
#  Registration
# ═══════════════════════════════════════════════════════════

_register_order_listeners()
_register_account_listeners()
_register_inventory_listeners()
