"""
مستمعو الولاء.

⚠️  **`orders` و`pos` لا يعرفان بوجود الولاء.**

    كلاهما يبعث إشارة، وهذا الملف يترجمها إلى نقاط. الاستيراد
    نازل: `loyalty` يعرف الطلبات ولا العكس.

⚠️  وفشل المنح **لا يُفشل الطلب**.

    نقطة لم تُقيَّد تُصلَح بإعادة التقاط؛ طلبٌ تراجع لأجل نقطة
    خسارةٌ لا تُصلَح. الفشل يُسجَّل ويُبتلع.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from loyalty import services

logger = logging.getLogger(__name__)


def _safe(handler):
    """
    ⚠️  المستمع يعمل داخل معاملة العملية الأصلية.

        استثناء غير ملتقط يتراجع بالبيعة كلها لأجل نقاط لم
        تُمنَح — والبضاعة قد سُلِّمت فعلًا على الكاونتر.
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
        ⚠️  **بيعة الكاونتر لا تمرّ بـ `order_completed`.**

            نقطة البيع تُنشئ الطلب في حالته النهائية مباشرةً بلا
            مرور بآلة الحالة، فلا إشارة اكتمال تُبعَث. الاكتفاء
            بالإشارة يعني أن **عميل الفرع لا يكسب شيئًا** بينما
            عميل الموقع يكسب على الطلب نفسه — تفاوتٌ يُقرأ عطلًا.

        ⚠️  والمرتجع يُلتقط من هنا أيضًا: `REFUNDED` حالة تُكتب
            على الطلب لا حدثًا مستقلًا. بدون السحب يبقى المسار
            المفتوح: يشتري · يكسب · يُرجِع · ويحتفظ بالنقاط.

        ⚠️  الازدواج لا يمنعه هذا الفحص بل القيد الفريد على
            (الطلب، النوع) في الدفتر: الطلب يُحفَظ مرات.
        """
        if instance.status == OrderStatus.REFUNDED:
            services.reverse_for_order(instance)
            return

        if instance.status in (OrderStatus.COMPLETED, OrderStatus.DELIVERED):
            services.award_for_order(instance)
            services.reward_referral(instance)


_register()
