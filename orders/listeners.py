"""
مستمعو الطلبات لأحداث الدفع.

⚠️  **هذا هو الطرف الذي يجعل الدفع الإلكتروني يصل إلى الطلب.**

    `charge()` تُصدر رابط بوابة أو رقم دفع في منفذ، ولا تعرف إن دفع
    العميل. التأكيد يصل ويب‌هوكًا بعد دقائق أو ساعات، فيعلّم
    `PaymentTransaction` محصَّلة — وبلا هذا الملف يقف الأمر هناك:
    المال في الحساب والطلب «غير مدفوع» على شاشة الأدمن.

⚠️  و**الاتجاه مقلوب عمدًا**: `payments` تحت `orders` في مخطط الطبقات
    (انظر عقد import-linter في `pyproject.toml`)، فلا يجوز أن يستورد
    `orders` ليعلّم الطلب بنفسه. الدفع يعلن، والطلب يستمع.

⚠️  و**الفشل هنا لا يُبتلع** — بخلاف مستمعي `finance` و`notifications`.

    أولئك يكتبون قيدًا أو يرسلون رسالة: فشلهم يجب ألا يتراجع ببيعة
    اكتملت. أما هذا فيسجّل **أن المال قُبض**. ابتلاع فشله يعني
    استجابة ناجحة للبوابة عن حدث لم يُطبَّق — فتتوقف عن إعادة
    الإرسال ويضيع التأكيد نهائيًا. رفعه يُنتج ٥٠٠ تعيد البوابة
    المحاولة عليه، وهو ما نريده بالضبط.
"""

from __future__ import annotations

import logging
from uuid import UUID

from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _register() -> None:
    # ⚠️  الاستيراد داخل الدالة لا في رأس الملف — تُستدعى من
    #     `AppConfig.ready` بعد اكتمال سجل التطبيقات.
    from core.errors import BusinessError, ErrorCode
    from orders import services
    from orders.events import order_paid
    from orders.models import Order, OrderStatus, PaymentStatus
    from payments.events import payment_captured, payment_failed, payment_refunded

    def _order_for(payment) -> Order | None:
        """
        ⚠️  المرجع **نصي** لا مفتاح أجنبي: `payments` لا يعرف بوجود
            الطلبات. والتصفية بالنوع إلزامية — بيعة نقطة بيع ودفعة
            آجل يمرّان بنفس الجدول بمراجع من أنواع أخرى.

        ⚠️  و**يُتحقَّق من كونه UUID قبل الاستعلام.**

            `reference_id` حقل نصّي حرّ يكتب فيه كل نطاق ما يشاء،
            ومفتاح `Order` هو UUID. تمرير نصّ غير صالح إلى
            `filter(pk=…)` يرفع `ValidationError` **قبل** أن تصل
            قاعدة البيانات — فينهار الويب‌هوك بـ ٥٠٠ وتظلّ البوابة
            تعيد إرسال حدث لن ينجح أبدًا. والمرجع الغريب ليس خطأ:
            هو ببساطة دفعة لا تخصّ الطلبات.
        """
        if payment.reference_type != services.REFERENCE_TYPE:
            return None
        if not payment.reference_id:
            return None

        try:
            key = UUID(str(payment.reference_id))
        except (ValueError, AttributeError, TypeError):
            logger.warning(
                "مرجع طلب غير صالح في المعاملة %s: %r",
                payment.reference,
                payment.reference_id,
            )
            return None

        return Order.objects.filter(pk=key).first()

    @receiver(payment_captured, weak=False)
    def on_payment_captured(sender, payment, **kwargs):
        order = _order_for(payment)
        if order is None:
            return

        try:
            services.mark_paid(order)
        except BusinessError as exc:
            # ⚠️  «مدفوع بالفعل» ليس فشلًا بل **الحالة المطلوبة**.
            #
            #     البوابة تعيد الإرسال، وقد يصل تأكيدان بمعرّفين
            #     مختلفين لنفس الطلب (محاولة فاشلة ثم ناجحة). رفع
            #     الاستثناء هنا كان يُنتج ٥٠٠ تعيد المحاولة إلى
            #     الأبد على طلب لا ينقصه شيء.
            if exc.code == ErrorCode.ORDER_ALREADY_PAID:
                return
            raise

        logger.info("الطلب %s عُلِّم مدفوعًا بتأكيد %s", order.number, payment.reference)
        order_paid.send(sender=Order, order=order, payment_reference=payment.reference)

    @receiver(payment_refunded, weak=False)
    def on_payment_refunded(sender, payment, **kwargs):
        """
        ⚠️  حالة الدفع وحدها — **لا تُلمس حالة الطلب**.

            استرداد المال لا يعني تلقائيًا أن الطلب ملغى: قد تكون
            بضاعة سُلِّمت ثم رُدّ ثمنها جزئيًا. تحريك حالة الطلب قرار
            تشغيلي يتخذه الأدمن من شاشته، وهذا المستمع يسجّل ما
            حدث في البوابة لا ما ينبغي أن يحدث للطلب.
        """
        order = _order_for(payment)
        if order is None or order.payment_status == PaymentStatus.REFUNDED:
            return

        order.payment_status = PaymentStatus.REFUNDED
        order.save(update_fields=["payment_status"])
        logger.info("الطلب %s عُلِّم مستردًا بتأكيد %s", order.number, payment.reference)

    @receiver(payment_failed, weak=False)
    def on_payment_failed(sender, payment, **kwargs):
        """
        ⚠️  **الطلب المدفوع لا يعود غير مدفوع.**

            المحاولة الفاشلة قد تصل **بعد** الناجحة (إعادة إرسال
            متأخرة لحدث قديم). تطبيقها بلا حارس يمسح دفعة حقيقية
            ويجعل الطلب يبدو غير مسدَّد.
        """
        order = _order_for(payment)
        if order is None:
            return
        if order.payment_status not in (PaymentStatus.UNPAID, PaymentStatus.PENDING):
            return
        # ⚠️  ولا يُعلَّم فاشلًا بعد التسليم: الدفع عند الاستلام
        #     يُحصَّل نقدًا، وفشل بوابة قديم لا يمسّه.
        if order.status in (OrderStatus.DELIVERED, OrderStatus.COMPLETED):
            return

        order.payment_status = PaymentStatus.FAILED
        order.save(update_fields=["payment_status"])


_register()
