"""
مستمعو الأحداث.

⚠️  **هذا الملف هو الجهة الوحيدة التي تعرف الطرفين.**

    `orders` يبعث `order_completed` ولا يعرف من يستمع.
    `notifications` يستمع ولا يُستورَد من أحد.

    الربط هنا يقلب الاتجاه: بدل أن يستورد `orders` نطاق الإشعارات
    (استيراد صاعد)، يستورد `notifications` نطاق الطلبات (نازل).

⚠️  وفشل أي مستمع **لا يُفشل العملية التجارية**.

    بريد لم يُرسَل يجب ألا يلغي طلبًا اكتمل. الفشل يُسجَّل ويُبتلع.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from core import mail
from notifications import services
from notifications.models import NotificationCategory, NotificationPriority

logger = logging.getLogger(__name__)


def _safe(handler):
    """
    يبتلع أي فشل في المستمع ويسجّله.

    ⚠️  المستمع يعمل داخل معاملة العملية الأصلية — استثناء غير
        ملتقط يتراجع بالطلب كله لأجل بريد لم يُرسَل.
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
#  الطلبات
# ═══════════════════════════════════════════════════════════


def _register_order_listeners():
    from orders.events import order_completed
    from orders.models import Order, OrderStatus

    @receiver(order_completed, weak=False)
    @_safe
    def on_order_completed(sender, order, **kwargs):
        user = order.customer.user
        services.notify(
            user,
            category=NotificationCategory.ORDER,
            title=f"اكتمل طلبك {order.number}",
            body=f"تم تسليم طلبك بنجاح. إجماليه {order.grand_total} جنيه.",
            action_url=f"/account/orders/{order.pk}",
            reference_type="order",
            reference_id=order.pk,
        )

    @receiver(post_save, sender=Order, weak=False)
    @_safe
    def on_order_status_changed(sender, instance, created, **kwargs):
        """
        ⚠️  إشعار عند التغييرات ذات المعنى للعميل فقط.

            إشعار عند كل حفظ يغرق العميل برسائل لا تخصّه —
            «قيد التجهيز» تعنيه، أما تعديل ملاحظة داخلية فلا.
        """
        user = instance.customer.user

        if created:
            services.notify(
                user,
                category=NotificationCategory.ORDER,
                title=f"استلمنا طلبك {instance.number}",
                body="طلبك قيد المراجعة وسنبلغك بتأكيده.",
                action_url=f"/account/orders/{instance.pk}",
                reference_type="order",
                reference_id=instance.pk,
            )
            return

        messages = {
            OrderStatus.CONFIRMED: ("تأكد طلبك", "جارٍ تجهيز طلبك للشحن."),
            OrderStatus.SHIPPED: ("شُحن طلبك", "طلبك في الطريق إليك."),
            OrderStatus.DELIVERED: ("سُلّم طلبك", "نتمنى أن ينال رضاك."),
            OrderStatus.CANCELLED: ("أُلغي طلبك", instance.cancellation_reason or ""),
        }

        entry = messages.get(instance.status)
        if entry is None:
            return

        title, body = entry
        services.notify(
            user,
            category=NotificationCategory.ORDER,
            title=f"{title} {instance.number}",
            body=body,
            action_url=f"/account/orders/{instance.pk}",
            reference_type="order",
            reference_id=instance.pk,
            priority=(
                NotificationPriority.HIGH
                if instance.status == OrderStatus.CANCELLED
                else NotificationPriority.NORMAL
            ),
        )


# ═══════════════════════════════════════════════════════════
#  الحساب
# ═══════════════════════════════════════════════════════════


def _register_account_listeners():
    from accounts.models import AccountStatusChange

    @receiver(post_save, sender=AccountStatusChange, weak=False)
    @_safe
    def on_account_status_changed(sender, instance, created, **kwargs):
        """
        ⚠️  تصنيف `ACCOUNT` **إلزامي** — لا يُوقَف بتفضيل.

            إيقاف حساب يمر بلا علم صاحبه يعني اختراقًا صامتًا.
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
            template_key=(mail.ACCOUNT_SUSPENDED.key if suspended else mail.ACCOUNT_ACTIVATED.key),
            template_context={"reason": instance.reason},
            priority=NotificationPriority.URGENT,
            reference_type="account_status_change",
            reference_id=instance.pk,
        )


# ═══════════════════════════════════════════════════════════
#  المخزون — للأدمن
# ═══════════════════════════════════════════════════════════


def _register_inventory_listeners():
    from inventory.models import StockAlert

    @receiver(post_save, sender=StockAlert, weak=False)
    @_safe
    def on_stock_alert(sender, instance, created, **kwargs):
        """
        ⚠️  إشعار للأدمن لا للعميل.

            نفاد صنف شأن تشغيلي — إبلاغ العملاء به يعطي المنافس
            صورة عن مخزونك.
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
#  التسجيل
# ═══════════════════════════════════════════════════════════

_register_order_listeners()
_register_account_listeners()
_register_inventory_listeners()
