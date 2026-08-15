"""
أحداث نطاق الدفع.

⚠️  **`payments` لا يعرف من يستمع — ولا يستطيع أن يعرف.**

    الطبقات تضع `payments` **تحت** `orders` (انظر عقد import-linter
    في `pyproject.toml`): الطلب يستدعي الدفع، والدفع لا يعرف بوجود
    الطلبات إطلاقًا — مرجعه نصي.

    ولذلك لا يجوز أن يعلّم الويب‌هوك طلبًا كمدفوع باستيراد `orders`.
    الإشارة تقلب الاتجاه: الدفع يعلن، ومن هو أعلى منه يستمع.

⚠️  وتُبعَث **بعد** حفظ المعاملة لا قبله.

    مستمع يقرأ حالة لم تُحفظ بعد يبني قرارًا على قيمة قد يتراجع
    عنها الـ rollback.
"""

import django.dispatch

#: صُرِّح بالمبلغ ولم يُحصَّل بعد — البطاقة حجزت الرصيد
payment_authorized = django.dispatch.Signal()

#: **المال قُبض فعلًا** — يستهلكه: orders (تعليم الطلب مدفوعًا) · finance
payment_captured = django.dispatch.Signal()

#: فشل الدفع أو أُلغي أو انتهت مهلته
payment_failed = django.dispatch.Signal()

#: استرداد أكّدته البوابة عبر حدث وارد
payment_refunded = django.dispatch.Signal()
