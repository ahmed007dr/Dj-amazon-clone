"""
أحداث نقطة البيع.

⚠️  `pos` يبعث ولا يعرف من يستمع.

    `finance` في المرحلة ٨ سيستمع لـ `pos_session_closed` ليقيّد
    النقد؛ واستيراده من هنا يعني أن نقطة البيع تعرف المحاسبة —
    فيصير كل تغيير في القيود مسًّا بشاشة الكاشير.
"""

import django.dispatch

#: يُبعث عند إغلاق وردية بعد حساب الفرق.
#:     sender=POSSession  ·  session
pos_session_closed = django.dispatch.Signal()

#: يُبعث عند إتمام بيعة — بعد إنشاء الطلب وخصم المخزون.
#:     sender=POSSession  ·  session · order
pos_sale_completed = django.dispatch.Signal()
