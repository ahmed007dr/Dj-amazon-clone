"""
خدمات الطلبات.

⚠️  **هذا النطاق لا يلمس موديلات المخزون ولا ينفّذ محرك الكوبونات.**

    الكود القديم فعل الاثنين:

        product.quantity -= item.quantity      ← يعدّل موديل catalog
        product.save()

        # ونسخة كاملة من منطق الكوبون داخل الـ view

    هنا: `inventory.services` و`promotions.services` — استدعاء لا
    تكرار، والاتجاه نازل.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from cart import services as cart_services
from cart.models import Cart, CartStatus
from core.errors import BusinessError, ErrorCode
from inventory import services as inventory_services
from orders.models import (
    Order,
    OrderChannel,
    OrderLine,
    OrderStatus,
    OrderStatusHistory,
    PaymentStatus,
)
from promotions import services as promotion_services
from shipping import services as shipping_services
from shipping.models import ShippingMethod

logger = logging.getLogger(__name__)

REFERENCE_TYPE = "order"

# ═══════════════════════════════════════════════════════════
#  آلة الحالة
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  الانتقالات المسموحة **معرّفة صراحةً**.
#
#      بلا آلة حالة، طلب «مكتمل» يعود إلى «قيد الانتظار» بنداء
#      واحد — فيفسد كل تقرير مبيعات وكل عمولة محسوبة.

ALLOWED_TRANSITIONS = {
    OrderStatus.PENDING: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED: {OrderStatus.PROCESSING, OrderStatus.CANCELLED},
    OrderStatus.PROCESSING: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED, OrderStatus.CANCELLED},
    OrderStatus.DELIVERED: {OrderStatus.COMPLETED, OrderStatus.REFUNDED},
    OrderStatus.COMPLETED: {OrderStatus.REFUNDED},
    OrderStatus.CANCELLED: set(),  # نهائية
    OrderStatus.REFUNDED: set(),  # نهائية
}

#: الحالات التي يبقى فيها المخزون محجوزًا
RESERVING_STATUSES = {
    OrderStatus.PENDING,
    OrderStatus.CONFIRMED,
    OrderStatus.PROCESSING,
}


def can_transition(order: Order, to_status: str) -> bool:
    return to_status in ALLOWED_TRANSITIONS.get(order.status, set())


def can_cancel(order: Order) -> bool:
    return OrderStatus.CANCELLED in ALLOWED_TRANSITIONS.get(order.status, set())


# ═══════════════════════════════════════════════════════════
#  إنشاء الطلب
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def create_from_cart(
    cart: Cart,
    *,
    customer,
    address: dict,
    shipping_method_code: str = "",
    channel: str = OrderChannel.ONLINE,
    location=None,
    created_by=None,
    customer_note: str = "",
) -> Order:
    """
    تحويل سلة إلى طلب.

    ⚠️  **إعادة تحقق كاملة أولًا — بلا استثناء.**

        ما ترسله الواجهة من أسعار وإجماليات يُتجاهَل تمامًا. السلة
        تُعاد تسعيرها ويُعاد فحص كل سطر، فطلب بسعر قديم أو منتج
        ممنوع أو مخزون ناقص يُرفض هنا لا بعد الشحن.
    """
    user = cart.user

    snapshot = cart_services.revalidate(
        cart,
        user=user,
        governorate=address.get("governorate", ""),
        shipping_method_code=shipping_method_code,
    )

    # ⚠️  المشاكل **قبل** فحص الفراغ.
    #
    #     حين تفشل كل الأسطر (نفد المخزون · أُوقف المنتج) تصير
    #     `snapshot.lines` فارغة — فتقديم فحص الفراغ يعطي العميل
    #     «سلتك فارغة» بينما سلته ممتلئة وسببها الحقيقي مختلف تمامًا.
    if snapshot.has_issues:
        first = snapshot.issues[0]
        raise BusinessError(
            first.code,
            detail=f"{first.product_name}: {first.message}",
            status_code=409,
        )

    if not snapshot.lines:
        raise BusinessError(ErrorCode.CART_EMPTY)

    priced = snapshot.priced

    # ── إنشاء الطلب ────────────────────────────────────────
    order = Order.objects.create(
        customer=customer,
        channel=channel,
        location=location or inventory_services.default_location(),
        created_by=created_by,
        subtotal=priced.subtotal,
        discount_total=priced.discount_total,
        coupon_discount=priced.coupon_discount,
        tax_total=priced.tax_total,
        shipping_total=priced.shipping_amount,
        grand_total=priced.total,
        coupon_code=cart.coupon_code,
        shipping_method_code=shipping_method_code,
        recipient_name=address.get("recipient_name", ""),
        recipient_phone=address.get("phone", ""),
        governorate=address.get("governorate", ""),
        city=address.get("city", ""),
        street=address.get("street", ""),
        building=address.get("building", ""),
        landmark=address.get("landmark", ""),
        customer_note=customer_note,
    )

    # ── الأسطر بلقطاتها ────────────────────────────────────
    for (product, quantity, variant), line in snapshot.lines:
        OrderLine.objects.create(
            order=order,
            product=product,
            variant=variant,
            product_sku=product.sku,
            product_name_ar=product.name_ar,
            product_name_en=product.name_en,
            quantity=quantity,
            unit_price=line.unit_price,
            list_price=line.list_price,
            discount_amount=line.discount_amount,
            tax_rate=line.tax_rate,  # ⚠️ لقطة — ADR-30
            tax_amount=line.tax_amount,
            tax_class_code=line.tax_class_code,
            price_list_code=line.price_list_code,
        )

        # ── حجز المخزون ────────────────────────────────────
        inventory_services.reserve(
            product,
            quantity,
            location=order.location,
            variant=variant,
            reference_type=REFERENCE_TYPE,
            reference_id=order.pk,
        )

    # ── تسجيل الكوبون ──────────────────────────────────────
    if snapshot.coupon_result and snapshot.coupon_result.is_valid:
        promotion_services.redeem(
            snapshot.coupon_result.coupon,
            user,
            snapshot.coupon_result.discount_amount,
            order_amount=priced.total,
            reference_type=REFERENCE_TYPE,
            reference_id=order.pk,
        )

    # ── الشحنة ─────────────────────────────────────────────
    if shipping_method_code:
        method = ShippingMethod.objects.filter(code=shipping_method_code).first()
        if method is not None:
            shipping_services.create_shipment(
                method=method,
                address=address,
                shipping_fee=priced.shipping_amount,
                reference_type=REFERENCE_TYPE,
                reference_id=order.pk,
            )

    _record_status(order, "", OrderStatus.PENDING, note="أُنشئ الطلب", actor=created_by)

    cart.status = CartStatus.CONVERTED
    cart.converted_at = timezone.now()
    cart.save(update_fields=["status", "converted_at"])

    return order


# ═══════════════════════════════════════════════════════════
#  الانتقالات
# ═══════════════════════════════════════════════════════════


def _record_status(order, from_status, to_status, *, note="", actor=None):
    OrderStatusHistory.objects.create(
        order=order,
        from_status=from_status,
        to_status=to_status,
        note=note,
        changed_by=actor,
    )


@transaction.atomic
def transition(order: Order, to_status: str, *, note: str = "", actor=None) -> Order:
    """
    نقل الطلب إلى حالة جديدة.

    ⚠️  الانتقال غير المسموح يُرفض بـ `409` لا يُنفَّذ بصمت.
    """
    if not can_transition(order, to_status):
        raise BusinessError(
            ErrorCode.INVALID_STATE_TRANSITION,
            detail=f"{order.status} ⟵ {to_status} غير مسموح",
            status_code=409,
        )

    previous = order.status
    order.status = to_status
    updates = ["status"]

    now = timezone.now()
    if to_status == OrderStatus.CONFIRMED:
        order.confirmed_at = now
        updates.append("confirmed_at")
    elif to_status == OrderStatus.COMPLETED:
        order.completed_at = now
        updates.append("completed_at")

    order.save(update_fields=updates)
    _record_status(order, previous, to_status, note=note, actor=actor)

    # ⚠️  المخزون يُنفَّذ عند الشحن لا عند التأكيد.
    #     الطلب المؤكد قد يُلغى؛ المشحون لا يعود.
    if to_status == OrderStatus.SHIPPED:
        _commit_reservations(order)

    return order


def _commit_reservations(order: Order) -> int:
    """
    تنفيذ حجوزات الطلب — الخصم الفعلي من المخزون.

    ⚠️  عبر الخدمة بالمرجع لا باستعلام موديلات المخزون هنا.
        `orders` في L6 و`inventory` في L3؛ معرفة بنية جداوله
        تجعل أي تغيير فيها كسرًا في مكانين.
    """
    return inventory_services.commit_for_reference(REFERENCE_TYPE, order.pk)


@transaction.atomic
def cancel(order: Order, *, reason: str, actor=None) -> Order:
    """
    إلغاء طلب.

    ⚠️  ثلاثة إجراءات في معاملة واحدة:
          ١. الإفراج عن المخزون المحجوز
          ٢. إلغاء استخدام الكوبون
          ٣. تسجيل الحالة والسبب

        الفصل بينها يترك مخزونًا محجوزًا لطلب ملغى، أو كوبونًا
        مستهلكًا بلا مقابل.
    """
    if not can_cancel(order):
        raise BusinessError(
            ErrorCode.ORDER_CANNOT_BE_CANCELLED,
            detail=f"لا يمكن إلغاء طلب في حالة {order.status}",
            status_code=409,
        )

    if not reason:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="سبب الإلغاء إلزامي")

    previous = order.status

    _release_reservations(order)

    redemption = promotion_services.redemption_for(REFERENCE_TYPE, order.pk)
    if redemption is not None:
        promotion_services.cancel_redemption(redemption)

    order.status = OrderStatus.CANCELLED
    order.cancelled_at = timezone.now()
    order.cancellation_reason = reason
    order.save(update_fields=["status", "cancelled_at", "cancellation_reason"])

    _record_status(order, previous, OrderStatus.CANCELLED, note=reason, actor=actor)
    return order


def _release_reservations(order: Order) -> int:
    return inventory_services.release_for_reference(REFERENCE_TYPE, order.pk)


@transaction.atomic
def mark_paid(order: Order, *, actor=None) -> Order:
    """
    تعليم الطلب مدفوعًا.

    ⚠️  يُستدعى من `payments` بعد تأكيد البوابة — لا من الواجهة.
    """
    if order.payment_status == PaymentStatus.PAID:
        raise BusinessError(ErrorCode.ORDER_ALREADY_PAID)

    order.payment_status = PaymentStatus.PAID
    order.save(update_fields=["payment_status"])

    # الدفع يؤكد الطلب تلقائيًا
    if order.status == OrderStatus.PENDING:
        transition(order, OrderStatus.CONFIRMED, note="تأكيد بعد الدفع", actor=actor)

    return order


@transaction.atomic
def complete(order: Order, *, actor=None) -> Order:
    """
    إكمال الطلب.

    ⚠️  هنا تُبعث الأحداث التي تستهلكها النطاقات العليا:
        المالية والولاء والعمولات وتحديث إحصاءات العميل.

        كلها **تستمع** ولا تُستدعى — `orders` لا يعرف بوجودها.
    """
    order = transition(order, OrderStatus.COMPLETED, actor=actor)

    from orders.events import order_completed

    order_completed.send(sender=Order, order=order)
    return order


def orders_for(customer):
    """طلبات عميل — مُصفّاة بالملكية."""
    return (
        Order.objects.filter(customer=customer)
        .select_related("customer", "location")
        .prefetch_related("lines")
    )
