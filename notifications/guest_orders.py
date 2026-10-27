"""
Messages about guest orders — a buyer with no account.

⚠️  Kept out of `listeners.py` so that file only gains the two hooks that call
    in here. Nothing in this module needs a `User` for the buyer: there is none.
    The recipient is the email on the order, the language is the one the buyer
    chose at checkout, and the link is the signed tracking token.

    The owner side is the opposite: staff are real accounts, so they get the
    ordinary in-app notification (as for a stock alert), plus an optional email
    to a configured address.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q

from mailing import services as mail_services
from mailing import templates as mail_templates
from notifications import services
from notifications.models import NotificationCategory, NotificationChannel, NotificationPriority

logger = logging.getLogger(__name__)

#: Order status → the template the buyer receives. The same set the member path
#: mails for, so a guest is told exactly what a customer would be.
STATUS_TEMPLATES = {
    "CONFIRMED": mail_templates.ORDER_CONFIRMED,
    "SHIPPED": mail_templates.ORDER_SHIPPED,
    "DELIVERED": mail_templates.ORDER_DELIVERED,
    "CANCELLED": mail_templates.ORDER_CANCELLED,
}

#: How long "this status was already mailed" is remembered.
_DEDUPE_SECONDS = 14 * 24 * 3600


def _order_managers():
    """
    Everyone who may manage orders — the people to tell that a call is needed.

    ⚠️  The same rule as `CanManageOrders`: a superuser, the owner, or anyone
        holding `orders.change_order` directly or through a group.
    """
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission

    condition = Q(is_superuser=True) | Q(admin_profile__is_owner=True)
    permission = Permission.objects.filter(
        content_type__app_label="orders", codename="change_order"
    ).first()
    if permission is not None:
        condition |= Q(user_permissions=permission) | Q(groups__permissions=permission)

    return get_user_model().objects.filter(is_active=True).filter(condition).distinct()


def order_placed(order, tracking_token: str) -> None:
    """A guest order exists: confirm to the buyer, and tell the owner to call."""
    from accounts.services import frontend_url
    from orders import guest

    context = guest.mail_context(order, tracking_token)

    mail_services.send_mail(
        mail_templates.GUEST_ORDER_CONFIRMATION.key,
        to=order.contact_email,
        language=order.contact_language or "ar",
        context=context,
    )

    admin_link = frontend_url(f"/admin/orders/{order.pk}")

    # ── In-app, to every order manager ──────────────────────
    for manager in _order_managers():
        try:
            services.notify(
                manager,
                category=NotificationCategory.ORDER,
                title=f"طلب زائر جديد {order.number}",
                body=(
                    f"اتصل بـ {order.recipient_name} على {order.recipient_phone} "
                    f"لتأكيد الطلب · الإجمالي {order.grand_total} {order.currency}"
                ),
                action_url=f"/admin/orders/{order.pk}",
                reference_type="order",
                reference_id=order.pk,
                priority=NotificationPriority.HIGH,
                # No email template for staff here — the optional address below
                # carries the detailed mail. One in-app line per manager is enough.
                channels=(NotificationChannel.IN_APP,),
            )
        except Exception:
            logger.exception("تعذّر إشعار %s بطلب الزائر %s", manager.pk, order.number)

    # ── Optional email to the store ─────────────────────────
    alert_to = getattr(settings, "GUEST_ORDER_ALERT_EMAIL", "")
    if alert_to:
        mail_services.send_mail(
            mail_templates.GUEST_ORDER_ADMIN_ALERT.key,
            to=alert_to,
            language="ar",
            context={**context, "link": admin_link},
        )


def status_changed(order, update_fields=None) -> None:
    """
    Tell the buyer about a status that means something to them.

    ⚠️  One mail per status per order.

        `post_save` fires on *every* save — recording a payment, editing an
        internal note in the Django panel. Without this, a confirmed order would
        mail "your order is confirmed" again each time anything touched it. The
        `update_fields` check covers the service paths; the cache marker covers a
        plain `save()`.
    """
    if update_fields is not None and "status" not in update_fields:
        return

    template = STATUS_TEMPLATES.get(order.status)
    if template is None:
        return

    if not cache.add(f"guest-order-mail:{order.pk}:{order.status}", 1, _DEDUPE_SECONDS):
        return

    from orders import guest

    # A fresh token per message: each carries its own timestamp, so an old email's
    # link is not extended by a newer one, and none outlives its own max age.
    token = guest.make_token(order)

    mail_services.send_mail(
        template.key,
        to=order.contact_email,
        language=order.contact_language or "ar",
        context=guest.mail_context(order, token),
    )
