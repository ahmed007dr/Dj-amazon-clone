"""
خدمات نقطة البيع.

⚠️  **المبدأ الحاكم: POS قناة بيع لا نظام موازٍ.**

        pos.services.checkout()
                ↓
        orders.services.create_pos_order(channel=POS, location=…)
                ↓
            Order عادي

    تقرير مبيعات واحد · مخزون واحد · مالية واحدة.

⚠️  ولا تجاوز لأي قاعدة: سياسات الوصول والتسعير والمخزون تُطبَّق
    كما هي. «الكاشير أمام العميل ومستعجل» ليس سببًا لبيع صنف
    ممنوع أو غير متوفر — وهو بالضبط ما يجعل الجرد لا يوازن.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from core.errors import BusinessError, ErrorCode
from core.models.settings import SystemSetting
from core.money import ZERO, quantize
from inventory import services as inventory_services
from inventory.models import StockMovement
from payments import services as payment_services
from pos.events import pos_sale_completed, pos_session_closed
from pos.models import (
    CASH_IN,
    CashMovement,
    CashMovementKind,
    POSSession,
    Register,
    SessionStatus,
)
from pricing import services as pricing_services

logger = logging.getLogger(__name__)

#: مفاتيح الإعدادات القابلة للضبط من اللوحة
VARIANCE_THRESHOLD = "pos.cash_variance_threshold"
MAX_DISCOUNT_PERCENT = "pos.max_discount_percent"


def variance_threshold() -> Decimal:
    """
    الحد الذي يصير فوقه تفسير الفرق إلزاميًا.

    ⚠️  قاعدة العمل ١٢ لم تُحسم بعد — القيمة الافتراضية توصية
        مكتوبة في `docs/shared/04-DECISIONS.md`، وقابلة للضبط
        من اللوحة بلا نشر.
    """
    return Decimal(str(SystemSetting.get(VARIANCE_THRESHOLD, default="20.00")))


def max_discount_percent() -> Decimal:
    """
    سقف الخصم اليدوي للكاشير.

    ⚠️  قاعدة العمل ١١ لم تُحسم — الافتراضي **صفر**: لا خصم بلا
        اعتماد. الافتراضي المتساهل يفتح بابًا يصعب إغلاقه بعد أن
        يعتاده الكاشير.
    """
    return Decimal(str(SystemSetting.get(MAX_DISCOUNT_PERCENT, default="0")))


# ═══════════════════════════════════════════════════════════
#  الوردية
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def open_session(register: Register, cashier, *, opening_float: Decimal = ZERO) -> POSSession:
    """
    فتح وردية.

    ⚠️  الجهاز الموقوف لا يفتح وردية، والوردية المفتوحة لا تُفتح
        ثانيةً — القيد في قاعدة البيانات هو الحارس النهائي، وهذا
        الفحص يعطي رسالة مفهومة بدل خطأ تكامل.
    """
    if not register.is_active:
        raise BusinessError(ErrorCode.CONFLICT, detail="هذا الجهاز موقوف", status_code=409)

    existing = register.open_session
    if existing is not None:
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail=f"للجهاز وردية مفتوحة بالفعل: {existing.number}",
            status_code=409,
        )

    return POSSession.objects.create(
        register=register,
        cashier=cashier,
        opening_float=quantize(opening_float),
    )


def expected_cash_for(session: POSSession) -> Decimal:
    """
    النقد المتوقَّع في الدرج.

    ⚠️  محسوب من **حركات الصندوق** لا من مبيعات الوردية.

        بيعة بالبطاقة لا تضع نقدًا في الدرج؛ وحسابها ضمن المتوقَّع
        يُنتج عجزًا وهميًا بحجم كل مبيعات البطاقات — ويُتَّهم
        الكاشير بما لم يفعله.
    """
    total = session.cash_movements.aggregate(
        cash_in=Sum("amount", filter=__kind_in(CASH_IN)),
        cash_out=Sum("amount", filter=__kind_not_in(CASH_IN)),
    )

    inflow = total["cash_in"] or ZERO
    outflow = total["cash_out"] or ZERO

    return quantize(session.opening_float + inflow - outflow)


def __kind_in(kinds):
    from django.db.models import Q

    return Q(kind__in=list(kinds))


def __kind_not_in(kinds):
    from django.db.models import Q

    return ~Q(kind__in=list(kinds))


@transaction.atomic
def close_session(
    session: POSSession,
    *,
    counted_cash: Decimal,
    closed_by,
    variance_note: str = "",
) -> POSSession:
    """
    إغلاق وردية بتسوية نقدية.

    ⚠️  **الفرق فوق الحد يوجب تفسيرًا.**

        قاعدة العمل ١٢. فرق بلا تفسير يتراكم شهورًا ثم يُكتشف
        كعجز لا يعرف أحد مصدره — والتفسير وقت الإغلاق هو الوقت
        الوحيد الذي يتذكّر فيه الكاشير ما جرى.

    ⚠️  والوردية المغلقة لا تُغلق ثانيةً: الإغلاق المكرر كان
        سيعيد كتابة `expected_cash` بلقطة جديدة، فتتغيّر تسوية
        مُعتمدة بأثر رجعي.
    """
    if not session.is_open:
        raise BusinessError(ErrorCode.CONFLICT, detail="هذه الوردية مغلقة بالفعل", status_code=409)

    expected = expected_cash_for(session)
    counted = quantize(counted_cash)
    variance = counted - expected

    if abs(variance) > variance_threshold() and not variance_note.strip():
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            detail=(
                f"الفرق {variance} يتجاوز الحد المسموح "
                f"({variance_threshold()}) — التفسير إلزامي"
            ),
            status_code=400,
        )

    session.status = SessionStatus.CLOSED
    session.closed_at = timezone.now()
    session.closed_by = closed_by
    session.counted_cash = counted
    session.expected_cash = expected
    session.variance_note = variance_note.strip()
    session.save(
        update_fields=[
            "status",
            "closed_at",
            "closed_by",
            "counted_cash",
            "expected_cash",
            "variance_note",
        ]
    )

    # ⚠️  الحدث بعد الحفظ لا قبله: المستمع (المالية لاحقًا) يقرأ
    #     وردية مغلقة فعلًا لا واحدة قد يفشل حفظها.
    pos_session_closed.send(sender=POSSession, session=session)

    return session


def record_cash(
    session: POSSession,
    *,
    kind: str,
    amount: Decimal,
    reason: str = "",
    performed_by=None,
    reference_type: str = "",
    reference_id: str = "",
) -> CashMovement:
    """
    تسجيل حركة نقدية.

    ⚠️  الوردية المغلقة لا تقبل حركات — وإلا تغيّر متوقَّع مُسوّى.
    """
    if not session.is_open:
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail="لا تُسجَّل حركة على وردية مغلقة",
            status_code=409,
        )

    if amount <= ZERO:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="المبلغ يجب أن يكون موجبًا")

    return CashMovement.objects.create(
        session=session,
        kind=kind,
        amount=quantize(amount),
        reason=reason,
        performed_by=performed_by,
        reference_type=reference_type,
        reference_id=str(reference_id) if reference_id else "",
    )


# ═══════════════════════════════════════════════════════════
#  البيع
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SaleLine:
    """سطر في بيعة — المنتج والكمية فقط، والسعر يحسبه `pricing`."""

    product: object
    quantity: int
    variant: object | None = None


@dataclass(frozen=True)
class SplitPayment:
    """
    جزء من دفع مقسّم.

    ⚠️  الدفع المقسّم حالة يومية على الكاونتر: نصفه نقدًا ونصفه
        بالبطاقة. حصره في طريقة واحدة يجبر الكاشير على تسجيل
        بيعتين لعملية واحدة — فينكسر الإيصال والمرتجع معًا.
    """

    method: str
    amount: Decimal


@dataclass
class SaleResult:
    order: object
    payments: list = field(default_factory=list)
    cash_movement: CashMovement | None = None


@dataclass(frozen=True)
class Quote:
    """
    تسعير بيعة قبل إتمامها.

    ⚠️  **نفس الحساب الذي سيُحصَّل — لا نسخة منه.**

        شاشة الكاشير تعرض إجماليًا، والخادم يحصّل إجماليًا. حسابهما
        في مكانين يعني أنهما يتباعدان عند أول تغيير في التسعير،
        فيقول الجهاز رقمًا ويطبع الإيصال آخر — والعميل هو من يكتشف.
    """

    lines: list
    subtotal: Decimal
    tax_total: Decimal
    discount_total: Decimal
    total: Decimal


def quote(
    session: POSSession,
    lines: list[SaleLine],
    *,
    customer=None,
    discount_percent: Decimal = ZERO,
) -> Quote:
    """
    يسعّر السلة بلا أي أثر: لا مخزون يُخصم ولا طلب يُنشأ.

    ⚠️  سقف الخصم يُفحَص هنا أيضًا.

        تركه للإتمام وحده يجعل الكاشير يبني بيعة كاملة أمام العميل
        ثم يُرفض في آخر ضغطة — والأصل أن يُمنع الخصم لحظة إدخاله.
    """
    cap = max_discount_percent()
    if discount_percent > cap:
        raise BusinessError(
            ErrorCode.PERMISSION_DENIED,
            detail=f"الخصم {discount_percent}% يتجاوز السقف المسموح ({cap}%)",
            status_code=403,
        )

    user = customer.user if customer is not None else None

    priced_lines = [
        (
            line,
            pricing_services.price_for(
                line.product, line.quantity, user=user, variant=line.variant
            ),
        )
        for line in lines
    ]

    subtotal = quantize(sum((priced.subtotal for _line, priced in priced_lines), ZERO))
    tax_total = quantize(sum((priced.tax_amount for _line, priced in priced_lines), ZERO))
    line_discount = quantize(sum((priced.discount_amount for _line, priced in priced_lines), ZERO))

    manual_discount = quantize(subtotal * discount_percent / Decimal("100"))

    return Quote(
        lines=priced_lines,
        subtotal=subtotal,
        tax_total=tax_total,
        discount_total=quantize(line_discount + manual_discount),
        total=quantize(subtotal + tax_total - manual_discount),
    )


def _assert_payments_cover(total: Decimal, payments: list[SplitPayment]) -> None:
    """
    ⚠️  مجموع الدفعات **يساوي** الإجمالي بالضبط.

        الأقل يعني بيعة غير مسدَّدة تُسجَّل كمكتملة؛ والأكثر يعني
        فائضًا لا يعرف النظام أين يذهب. الباقي للعميل يُحسبه
        الكاشير خارج النظام كما هو الحال في كل صندوق.
    """
    paid = quantize(sum((entry.amount for entry in payments), ZERO))

    if paid != total:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            detail=f"مجموع الدفعات {paid} لا يساوي الإجمالي {total}",
            status_code=400,
        )


@transaction.atomic
def checkout(
    session: POSSession,
    lines: list[SaleLine],
    payments: list[SplitPayment],
    *,
    customer=None,
    discount_percent: Decimal = ZERO,
    note: str = "",
) -> SaleResult:
    """
    إتمام بيعة على الكاونتر.

    ⚠️  الترتيب مقصود وغير قابل للتبديل:

          ١. تسعير من `pricing`      ← لا سعر يدخل من الواجهة
          ٢. خصم المخزون فورًا       ← بلا حجز، البيع لحظي
          ٣. إنشاء الطلب             ← `channel=POS`
          ٤. تسجيل الدفعات
          ٥. حركة صندوق للنقدي وحده

        خصم المخزون **قبل** إنشاء الطلب: لو نفد صنف تُلغى المعاملة
        كلها بلا طلب يتيم. والعكس يترك طلبًا مسجَّلًا لبضاعة لم
        تُسلَّم.
    """
    if not session.is_open:
        raise BusinessError(
            ErrorCode.CONFLICT, detail="الوردية مغلقة — افتح وردية أولًا", status_code=409
        )

    if not lines:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="لا أصناف في البيعة")

    location = session.register.location

    # ── ١. التسعير ─────────────────────────────────────────
    # ⚠️  **نفس الدالة التي تغذّي شاشة الكاشير.**
    #
    #     تكرار الحساب هنا كان يعني إجماليين ينفصلان عند أول تعديل
    #     في التسعير — أحدهما على الشاشة والآخر على الإيصال.
    priced = quote(session, lines, customer=customer, discount_percent=discount_percent)
    priced_lines = priced.lines
    subtotal = priced.subtotal
    tax_total = priced.tax_total
    total = priced.total

    _assert_payments_cover(total, payments)

    # ── ٢. خصم المخزون فورًا ───────────────────────────────
    #
    # ⚠️  المرجع هنا **الوردية** لأن الطلب لم يُنشأ بعد.
    #
    #     الترتيب مقصود: لو نفد صنف تُلغى المعاملة بلا طلب يتيم.
    #     لكنه يترك الحركات مربوطة بالوردية لا بالبيعة — ويُعاد
    #     توجيهها إلى الطلب بعد إنشائه مباشرةً (الخطوة ٣ب).
    movements = []
    for line, _priced in priced_lines:
        movements.extend(
            inventory_services.sell_immediately(
                line.product,
                line.quantity,
                location=location,
                variant=line.variant,
                reference_type="pos_session",
                reference_id=str(session.pk),
                performed_by=session.cashier,
            )
        )

    # ── ٣. الطلب ───────────────────────────────────────────
    from orders import services as order_services

    order = order_services.create_pos_order(
        customer=customer,
        location=location,
        cashier=session.cashier,
        lines=[
            {
                "product": line.product,
                "variant": line.variant,
                "quantity": line.quantity,
                "unit_price": priced.unit_price,
                "tax_rate": priced.tax_rate,
                "tax_amount": priced.tax_amount,
                "discount_amount": priced.discount_amount,
            }
            for line, priced in priced_lines
        ],
        totals={
            "subtotal": subtotal,
            "discount_total": priced.discount_total,
            "tax_total": tax_total,
            "grand_total": total,
        },
        note=note,
    )

    # ── ٣ب. إعادة توجيه حركات المخزون إلى الطلب ────────────
    #
    # ⚠️  **بدونها تغيب تكلفة كل بيعة كاونتر عن قائمة الأرباح.**
    #
    #     المالية تحسب تكلفة البضاعة المباعة من حركات المخزون
    #     المرتبطة بالطلب (`reference_type="order"`). حركات نقطة
    #     البيع كانت مربوطة بالوردية، فكانت مبيعات الفرع تُقيَّد
    #     إيرادًا **بتكلفة صفر** — أي بربح يساوي ثمن البيع كاملًا.
    #     وهو خطأ في الاتجاه الأسوأ: يجعل التقرير يبدو ممتازًا.
    #
    # ⚠️  والوردية تبقى في `note` لا تضيع.
    #
    #     لا مفتاح أجنبي من `Order` إلى `POSSession`: `orders`
    #     **تحت** `pos` في ترتيب الطبقات، والمفتاح كان سيقلب
    #     الاتجاه ويكسر العقد. النص يكفي للتتبع اليدوي، والربط
    #     التحليلي يمرّ عبر `CashMovement` التي تحمل معرّف الطلب.
    if movements:
        touched = StockMovement.objects.filter(pk__in=[m.pk for m in movements])
        touched.update(reference_type="order", reference_id=str(order.pk))

        # ⚠️  الملاحظة الفارغة وحدها تُكتب.
        #
        #     الحركة بلا دفعة تحمل «بلا دفعة مرتبطة» — وهي أثر
        #     بضاعة مجهولة التكلفة. الكتابة فوقها تمحو التفسير
        #     الوحيد لبند سيظهر في التقرير بتكلفة ناقصة.
        touched.filter(note="").update(note=f"وردية {session.number}")

    # ── ٤. الدفعات ─────────────────────────────────────────
    transactions = []
    for entry in payments:
        transactions.append(
            payment_services.charge(
                amount=entry.amount,
                method=entry.method,
                channel="POS",
                reference_type="order",
                reference_id=str(order.pk),
                customer=customer,
                # ⚠️  مفتاح فريد لكل جزء: نقرة مزدوجة على «تحصيل»
                #     كانت ستنتج دفعتين لنفس البيعة.
                idempotency_key=f"pos-{order.pk}-{entry.method}-{entry.amount}",
            )
        )

    # ── ٥. النقد في الدرج ──────────────────────────────────
    cash_total = quantize(sum((entry.amount for entry in payments if entry.method == "CASH"), ZERO))

    movement = None
    if cash_total > ZERO:
        movement = record_cash(
            session,
            kind=CashMovementKind.SALE,
            amount=cash_total,
            performed_by=session.cashier,
            reference_type="order",
            reference_id=str(order.pk),
        )

    pos_sale_completed.send(sender=POSSession, session=session, order=order)

    return SaleResult(order=order, payments=transactions, cash_movement=movement)


# ═══════════════════════════════════════════════════════════
#  المرتجع
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def refund_sale(
    session: POSSession,
    order,
    *,
    reason: str,
    cash_amount: Decimal | None = None,
    performed_by=None,
):
    """
    مرتجع داخل نقطة البيع.

    ⚠️  المرتجع يُنتج **حركة مخزون عكسية** لا حذفًا للطلب.

        حذف الطلب يمحو بيعة وقعت فعلًا، فينكسر تقرير اليوم وتختفي
        الضريبة المحصَّلة عليها. الطلب يبقى ويُعلَّم `REFUNDED`.

    ⚠️  والنقد المُعاد يخرج من الدرج بحركة مسجَّلة — وإلا بدا
        الفرق عجزًا عند الإغلاق.
    """
    if not session.is_open:
        raise BusinessError(ErrorCode.CONFLICT, detail="لا مرتجع على وردية مغلقة", status_code=409)

    from orders import services as order_services

    order = order_services.refund_pos_order(order, reason=reason, actor=performed_by)

    # إعادة الأصناف إلى مخزون الموقع
    for line in order.lines.select_related("product", "variant").all():
        inventory_services.adjust(
            line.product,
            line.quantity,
            location=session.register.location,
            variant=line.variant,
            reason=f"مرتجع نقطة بيع — {order.number}",
            performed_by=performed_by,
        )

    movement = None
    if cash_amount and cash_amount > ZERO:
        movement = record_cash(
            session,
            kind=CashMovementKind.REFUND,
            amount=cash_amount,
            reason=reason,
            performed_by=performed_by,
            reference_type="order",
            reference_id=str(order.pk),
        )

    return SaleResult(order=order, cash_movement=movement)
