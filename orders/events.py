"""
أحداث نطاق الطلبات.

⚠️  **`orders` لا يعرف من يستمع.**

    المالية والولاء والعمولات وإحصاءات العملاء كلها تستهلك هذه
    الإشارات. استدعاؤها مباشرةً يعني أن `orders` يستورد نطاقات
    أعلى منه — استيراد صاعد يكسر الحدود.

    الإشارة تقلب الاتجاه: الباعث لا يعرف المستمع.
"""

import django.dispatch

#: أُنشئ طلب — المخزون محجوز، الدفع لم يتم بعد
order_created = django.dispatch.Signal()

#: اكتمل الطلب — يستهلكه: finance · loyalty · commissions · customers
order_completed = django.dispatch.Signal()

#: أُلغي الطلب — المخزون أُفرج عنه والكوبون أُلغي
order_cancelled = django.dispatch.Signal()

#: تم الدفع
order_paid = django.dispatch.Signal()

#: تم الشحن — المخزون خُصم فعليًا
order_shipped = django.dispatch.Signal()
