"""
مستمعو B2B.

⚠️  **`orders` لا يعرف بوجود الآجل.**

    الطلب يُبعث حالته، وهذا الملف يترجمها إلى حركة على حساب
    العميل. الاستيراد نازل: `b2b` يعرف الطلبات ولا العكس.

⚠️  وفشل التقييد **لا يُفشل الطلب** — لكنه يُسجَّل بمستوى خطأ.

    قيد مديونية لم يُكتب يعني بضاعة خرجت بلا أثر على الحساب،
    وهو أخطر من بريد لم يُرسَل: يُكتشف بفارق في كشف الحساب بعد
    شهر. الابتلاع هنا لمنع تراجع الطلب فقط، والسجل هو ما يُراجَع.
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
        ⚠️  المرتجع على طلب آجل **يُقيَّد إشعارًا دائنًا**.

            بدونه يبقى العميل مدينًا ببضاعة أعادها — فيُمنَع من
            الشراء بحدٍّ استهلكه طلب أُلغي.
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
