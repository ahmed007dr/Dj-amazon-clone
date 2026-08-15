"""
مستمعو المالية.

⚠️  **`orders` و`pos` لا يعرفان بوجود المالية.**

    كلاهما يبعث إشارة ولا يعرف من يستمع؛ والمالية تستورد نطاق
    الطلبات (استيراد نازل) لا العكس. الربط هنا يقلب الاتجاه.

⚠️  وفشل التقييد **لا يُفشل البيعة**.

    قيد محاسبي لم يُكتب يجب ألا يلغي طلبًا اكتمل أو بيعةً سُلِّمت
    بضاعتها. الفشل يُسجَّل ويُبتلع — ويُصلَح بإعادة الالتقاط.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from finance import services

logger = logging.getLogger(__name__)


def _safe(handler):
    """
    ⚠️  المستمع يعمل داخل معاملة العملية الأصلية.

        استثناء غير ملتقط يتراجع بالبيعة كلها لأجل قيد لم يُكتب —
        والبضاعة قد سُلِّمت فعلًا على الكاونتر.
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
        ⚠️  **إعادة حساب التكلفة بعد ربط حركات المخزون بالطلب.**

            نقطة البيع تخصم المخزون **قبل** إنشاء الطلب (لئلا يبقى
            طلب يتيم لو نفد صنف)، فتُربط الحركات بالوردية ثم
            يُعاد توجيهها إلى الطلب بعد إنشائه.

            لكن `post_save` على الطلب يسبق ذلك التوجيه، فيقع أول
            حساب للتكلفة على **صفر حركات**. بلا هذا المستمع تبقى
            كل بيعة كاونتر مقيَّدة بتكلفة صفر — أي بربح يساوي ثمن
            البيع كاملًا، وهو أسوأ اتجاه ممكن للخطأ لأن التقرير
            يبدو ممتازًا.
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
        ⚠️  **بيعة الكاونتر لا تمرّ بـ `order_completed`.**

            نقطة البيع تُنشئ الطلب في حالته النهائية مباشرةً
            (`DELIVERED`/`PAID`) بلا مرور بآلة الحالة — فلا إشارة
            اكتمال تُبعَث. الاكتفاء بالإشارة كان يعني أن **كل
            مبيعات الفرع تغيب عن قائمة الأرباح** بينما التقرير
            يبدو سليمًا.

        ⚠️  والمرتجع يُلتقط من هنا أيضًا: `REFUNDED` حالة تُكتب
            على الطلب لا حدثًا مستقلًا.
        """
        if instance.status == OrderStatus.REFUNDED:
            services.record_refund(instance)
            return

        # الطلب المكتمل أو المسلَّم — والالتقاط لا يزدوج بفضل
        # القيد الفريد على (المصدر، الطلب).
        if instance.status in (OrderStatus.COMPLETED, OrderStatus.DELIVERED):
            services.record_order_revenue(instance)


_register()
