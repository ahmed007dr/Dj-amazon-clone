"""
خدمات B2B.

⚠️  **فحص الائتمان هو الوظيفة الحرجة في هذا الملف.**

    كل ما عداه عرض وتقرير. أما هذا الفحص فيقرّر خروج بضاعة مقابل
    وعد بالدفع — وخطؤه في اتجاه واحد يعني خسارة نقدية مباشرة.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Case, DecimalField, F, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from b2b.models import (
    DEBIT_KINDS,
    OPEN_INVOICE_STATUSES,
    BusinessProfile,
    CreditStatus,
    Invoice,
    InvoiceStatus,
    LedgerEntry,
    LedgerKind,
)
from core.errors import BusinessError, ErrorCode
from core.money import ZERO, quantize

logger = logging.getLogger(__name__)

#: حدود التقادم بالأيام — تطابق ما يقرأه المحاسب في أي كشف
AGING_BUCKETS = [(0, 30), (31, 60), (61, 90)]


def _signed_sum(queryset) -> Decimal:
    """
    مجموع الحركات بإشاراتها.

    ⚠️  الإشارة تُحسَب في قاعدة البيانات لا في بايثون.

        جرّ كل حركات عميل له ألف طلب إلى الذاكرة لجمعها يجعل فتح
        كشف الحساب أبطأ كلما زاد ولاؤه.
    """
    total = queryset.aggregate(
        total=Coalesce(
            Sum(
                Case(
                    When(kind__in=list(DEBIT_KINDS), then=F("amount")),
                    default=-F("amount"),
                    output_field=DecimalField(max_digits=14, decimal_places=2),
                )
            ),
            Value(ZERO),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )["total"]
    return quantize(total)


def outstanding_balance(business: BusinessProfile) -> Decimal:
    """
    ما على العميل الآن — **مشتق من الدفتر**.

    ⚠️  لا حقل `balance` مخزَّن.

        الحقل المُحدَّث بالجمع والطرح ينحرف عند أول استثناء في
        منتصف معاملة أو أول تصحيح يدوي. وانحراف الرصيد الائتماني
        يعني منع عميل ملتزم أو تمديد ائتمان لمتعثّر — بلا أن
        يعرف أحد أيّهما وقع.
    """
    return _signed_sum(LedgerEntry.objects.filter(business=business))


def available_credit(business: BusinessProfile) -> Decimal:
    """
    ⚠️  لا يقلّ عن صفر.

        عميل سدّد أكثر مما عليه يصير رصيده سالبًا، فيبدو حده
        الائتماني أكبر مما مُنح له. الرصيد الدائن ميزة للعميل لا
        توسيع لسقفه.
    """
    remaining = business.credit_limit - outstanding_balance(business)

    # ⚠️  محصور بين الصفر والحد الممنوح — **من الطرفين**.
    #
    #     الأرضية تمنع رقمًا سالبًا يُقرأ كأنه متاح. والسقف يمنع ما
    #     هو أخطر: عميل سدّد أكثر مما عليه يصير رصيده سالبًا،
    #     فيرفع الطرح متاحه فوق ما مُنح له — فيشتري بحدٍّ لم يوافق
    #     عليه أحد. الرصيد الدائن ميزة له لا توسيع لسقفه.
    return min(max(remaining, ZERO), business.credit_limit)


def overdue_invoices(business: BusinessProfile):
    """الفواتير التي تجاوزت استحقاقها ولم تُسدَّد."""
    return Invoice.objects.filter(
        business=business,
        # ⚠️  `OPEN_...` لا `ISSUED`: الفاتورة المعلَّمة «متأخرة»
        #     ما زالت مستحقة، واستبعادها كان يجعل تعليمها يخفيها
        #     من بوابة الائتمان — فتسقط أقدم الديون من الحساب.
        status__in=OPEN_INVOICE_STATUSES,
        due_on__lt=timezone.localdate(),
    )


# ═══════════════════════════════════════════════════════════
#  البوابة الائتمانية
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CreditDecision:
    """
    ⚠️  القرار يحمل **سببه** لا نعم/لا فقط.

        «مرفوض» بلا سبب يجعل مندوب المبيعات يتصل بالإدارة في كل
        طلب. والسبب يُعرَض للعميل ليتصرّف: يسدّد أو يجدّد ترخيصه.
    """

    allowed: bool
    reason: str = ""
    available: Decimal = ZERO


def evaluate_credit(business: BusinessProfile, amount: Decimal) -> CreditDecision:
    """
    هل يُسمح بطلب آجل بهذا المبلغ؟

    ⚠️  الترتيب مقصود: **الأسباب البنيوية قبل الحسابية.**

        عميل موقوف ترخيصه يجب أن يقرأ «ترخيصك منتهٍ» لا «تجاوزت
        حدك» — فالثاني يدفعه إلى السداد بلا فائدة.
    """
    if business.credit_status == CreditStatus.SUSPENDED:
        return CreditDecision(False, "الحساب الائتماني موقوف — راجع خدمة العملاء")

    if not business.allows_credit:
        return CreditDecision(False, "لا ائتمان على هذا الحساب — الدفع مقدَّم")

    # ⚠️  الترخيص المنتهي يمنع الآجل لا البيع.
    #
    #     الصيدلية بترخيص منتهٍ ما زالت قائمة وقد تسدّد؛ لكن
    #     منحها بضاعة على وعد بينما وضعها القانوني معلّق مخاطرة
    #     لا تُقاس بالمال وحده.
    if not business.license_is_valid:
        return CreditDecision(
            False, f"الترخيص منتهٍ منذ {business.license_expires_on} — جدّده أو ادفع مقدَّمًا"
        )

    overdue = overdue_invoices(business)
    if overdue.exists():
        oldest = overdue.order_by("due_on").first()
        return CreditDecision(
            False,
            f"فاتورة متأخرة {oldest.number} منذ {oldest.days_overdue} يومًا — سدّدها أولًا",
        )

    available = available_credit(business)
    if amount > available:
        return CreditDecision(
            False,
            f"المتاح {available} والمطلوب {quantize(amount)} — سدّد أو اطلب رفع الحد",
            available,
        )

    return CreditDecision(True, available=available)


@transaction.atomic
def charge_on_credit(business: BusinessProfile, order, *, actor=None) -> LedgerEntry:
    """
    يقيّد طلبًا على الحساب ويُصدر فاتورته.

    ⚠️  **`select_for_update` على الملف التجاري — وليس تجميلًا.**

        طلبان متزامنان يقرأ كلٌّ منهما رصيدًا قبل أن يكتب الآخر،
        فيمرّان معًا ويتجاوز المجموع الحد. القفل يجعل الثاني
        ينتظر ويقرأ أثر الأول.

        وهذا السيناريو **ليس نادرًا** في B2B: نقرة مزدوجة على زر
        الإتمام تكفي.
    """
    locked = BusinessProfile.objects.select_for_update().get(pk=business.pk)

    decision = evaluate_credit(locked, order.grand_total)
    if not decision.allowed:
        raise BusinessError(ErrorCode.PERMISSION_DENIED, detail=decision.reason, status_code=403)

    due_on = timezone.localdate() + timedelta(days=locked.payment_terms_days)

    entry = LedgerEntry.objects.create(
        business=locked,
        kind=LedgerKind.CHARGE,
        amount=order.grand_total,
        order=order,
        due_on=due_on,
        reference=order.number,
        recorded_by=actor,
    )

    Invoice.objects.create(
        business=locked,
        order=order,
        due_on=due_on,
        subtotal=order.subtotal,
        discount_total=order.discount_total,
        tax_total=order.tax_total,
        total=order.grand_total,
    )

    return entry


@transaction.atomic
def record_payment(
    business: BusinessProfile,
    amount: Decimal,
    *,
    reference: str = "",
    note: str = "",
    actor=None,
) -> LedgerEntry:
    """
    سداد من العميل — ويُسوّي أقدم الفواتير أولًا.

    ⚠️  **الأقدم أولًا (FIFO) لا الأحدث.**

        تسوية الأحدث تُبقي الفاتورة القديمة مفتوحة إلى الأبد،
        فيظهر العميل متأخرًا وهو يسدّد بانتظام — ويُمنَع من الشراء
        بسبب دين سدّده فعلًا.
    """
    if amount <= ZERO:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="مبلغ السداد يجب أن يكون موجبًا")

    entry = LedgerEntry.objects.create(
        business=business,
        kind=LedgerKind.PAYMENT,
        amount=quantize(amount),
        reference=reference,
        note=note,
        recorded_by=actor,
    )

    _settle_oldest_first(business, quantize(amount))
    return entry


def _settle_oldest_first(business: BusinessProfile, amount: Decimal) -> None:
    """
    ⚠️  السداد الجزئي **لا يغلق فاتورة**.

        إغلاقها بمبلغ أقل يخفي الباقي من كشف الحساب، فيختفي دين
        قائم من كل تقرير — والعميل نفسه لا يعرف أنه مدين به.
    """
    remaining = amount

    open_invoices = Invoice.objects.filter(
        business=business, status__in=OPEN_INVOICE_STATUSES
    ).order_by("due_on", "issued_on")

    for invoice in open_invoices:
        if remaining < invoice.total:
            break
        invoice.status = InvoiceStatus.PAID
        invoice.save(update_fields=["status", "updated_at"])
        remaining -= invoice.total


@transaction.atomic
def record_credit_note(business: BusinessProfile, order, *, note: str = "", actor=None):
    """
    إشعار دائن — مرتجع على طلب آجل.

    ⚠️  لا يُحذف قيد المديونية الأصلي: الفاتورة صدرت وسُلّمت،
        وإلغاؤها بأثر رجعي يترك محاسب العميل بمستند بلا نظير.
    """
    charge = LedgerEntry.objects.filter(
        business=business, order=order, kind=LedgerKind.CHARGE
    ).first()
    if charge is None:
        return None

    if LedgerEntry.objects.filter(
        business=business, order=order, kind=LedgerKind.CREDIT_NOTE
    ).exists():
        return None

    invoice = Invoice.objects.filter(business=business, order=order).first()
    if invoice is not None:
        invoice.status = InvoiceStatus.CANCELLED
        invoice.save(update_fields=["status", "updated_at"])

    return LedgerEntry.objects.create(
        business=business,
        kind=LedgerKind.CREDIT_NOTE,
        amount=charge.amount,
        order=order,
        reference=order.number,
        note=note or "مرتجع",
        recorded_by=actor,
    )


# ═══════════════════════════════════════════════════════════
#  كشف الحساب والتقادم
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class AgingBucket:
    label: str
    amount: Decimal


@dataclass(frozen=True)
class Statement:
    """
    كشف حساب — **مستند يُرسَل للعميل**.

    ⚠️  الرصيد الافتتاحي والحركات والختامي معًا.

        كشف بالحركات وحدها يجبر العميل على جمعها ليعرف موقفه،
        وكشف بالرصيد وحده لا يُراجَع. الثلاثة معًا هي ما يجعل
        النزاع قابلًا للحسم.
    """

    business: BusinessProfile
    start: date
    end: date
    opening_balance: Decimal
    entries: list
    closing_balance: Decimal
    aging: list


def statement(business: BusinessProfile, start: date, end: date) -> Statement:
    if start > end:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="بداية الفترة بعد نهايتها")

    opening = _signed_sum(LedgerEntry.objects.filter(business=business, occurred_on__lt=start))

    entries = list(
        LedgerEntry.objects.filter(business=business, occurred_on__gte=start, occurred_on__lte=end)
        .select_related("order")
        .order_by("occurred_on", "created_at")
    )

    period = _signed_sum(
        LedgerEntry.objects.filter(business=business, occurred_on__gte=start, occurred_on__lte=end)
    )

    return Statement(
        business=business,
        start=start,
        end=end,
        opening_balance=opening,
        entries=entries,
        closing_balance=quantize(opening + period),
        aging=aging(business),
    )


def aging(business: BusinessProfile) -> list[AgingBucket]:
    """
    تقادم المديونية — **من الفواتير المفتوحة**.

    ⚠️  يُحسب من الفواتير لا من الدفتر.

        الدفتر يحمل السداد بلا ربط بفاتورة بعينها، فحساب التقادم
        منه يحتاج تخصيصًا يعيد اختراع ما تفعله الفواتير أصلًا.
    """
    today = timezone.localdate()
    open_invoices = Invoice.objects.filter(business=business, status__in=OPEN_INVOICE_STATUSES)

    buckets = []
    for low, high in AGING_BUCKETS:
        total = open_invoices.filter(
            due_on__lte=today - timedelta(days=low),
            due_on__gt=today - timedelta(days=high + 1),
        ).aggregate(
            total=Coalesce(
                Sum("total"),
                Value(ZERO),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            )
        )["total"]
        buckets.append(AgingBucket(label=f"{low}-{high}", amount=quantize(total)))

    # ⚠️  السلة الأخيرة مفتوحة من الأعلى: دين عمره سنة يجب أن
    #     يظهر لا أن يسقط من الكشف لأنه تجاوز آخر حد مكتوب.
    oldest_edge = AGING_BUCKETS[-1][1]
    beyond = open_invoices.filter(due_on__lt=today - timedelta(days=oldest_edge)).aggregate(
        total=Coalesce(
            Sum("total"),
            Value(ZERO),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )["total"]
    buckets.append(AgingBucket(label=f"{oldest_edge}+", amount=quantize(beyond)))

    # ⚠️  غير المستحق بعد يُعرَض منفصلًا: خلطه بالمتأخر يجعل عميلًا
    #     ملتزمًا يبدو متعثّرًا بمبلغ لم يحن موعده.
    not_due = open_invoices.filter(due_on__gt=today).aggregate(
        total=Coalesce(
            Sum("total"),
            Value(ZERO),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )["total"]
    buckets.insert(0, AgingBucket(label="not_due", amount=quantize(not_due)))

    return buckets


# ═══════════════════════════════════════════════════════════
#  إعادة الطلب السريع
# ═══════════════════════════════════════════════════════════


def frequently_ordered(customer, limit: int = 20) -> list[dict]:
    """
    أكثر ما يطلبه هذا العميل.

    ⚠️  **الأكثر تكرارًا لا الأحدث.**

        الصيدلية تعيد طلب نفس العشرين صنفًا كل أسبوعين. «آخر طلب»
        يعطي طلبًا واحدًا قد يكون استثنائيًا؛ والتكرار يعطي سلّتها
        المعتادة فعلًا.
    """
    from orders.models import OrderLine, OrderStatus

    rows = (
        OrderLine.objects.filter(
            order__customer=customer,
            order__status__in=[OrderStatus.DELIVERED, OrderStatus.COMPLETED],
        )
        .values("product_id", "product_sku", "product_name_ar", "product_name_en")
        .annotate(times=Sum(Value(1)), quantity=Sum("quantity"))
        .order_by("-times", "-quantity")[:limit]
    )

    return [
        {
            "product": str(row["product_id"]),
            "sku": row["product_sku"],
            "name_ar": row["product_name_ar"],
            "name_en": row["product_name_en"],
            "times": row["times"],
            "total_quantity": row["quantity"],
        }
        for row in rows
    ]


@transaction.atomic
def grant_credit(
    business: BusinessProfile,
    *,
    limit: Decimal,
    terms_days: int,
    actor,
    note: str = "",
) -> BusinessProfile:
    """
    ⚠️  المنح **فعل موثَّق** لا تعديل حقل.

        «من رفع حد هذا العميل إلى مئة ألف ومتى؟» سؤال يُطرَح بعد
        أول تعثّر — ولا بد أن يُجاب من الصف نفسه.
    """
    if limit < ZERO:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الحد الائتماني لا يكون سالبًا")

    business.credit_limit = quantize(limit)
    business.payment_terms_days = terms_days
    business.credit_status = CreditStatus.ACTIVE if limit > ZERO else CreditStatus.NONE
    business.credit_approved_by = actor
    business.credit_approved_at = timezone.now()
    business.credit_note = note
    business.save(
        update_fields=[
            "credit_limit",
            "payment_terms_days",
            "credit_status",
            "credit_approved_by",
            "credit_approved_at",
            "credit_note",
            "updated_at",
        ]
    )
    return business


def suspend_credit(business: BusinessProfile, *, actor, reason: str) -> BusinessProfile:
    """
    ⚠️  الإيقاف **لا يمسّ الحد** — يعطّله فقط.

        تصفير الحد يفقد ما كان ممنوحًا، فتحتاج إعادة التفعيل قرارًا
        جديدًا من الصفر بدل رفع الإيقاف.
    """
    if not reason.strip():
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="سبب الإيقاف إلزامي")

    business.credit_status = CreditStatus.SUSPENDED
    business.credit_note = reason
    business.credit_approved_by = actor
    business.credit_approved_at = timezone.now()
    business.save(
        update_fields=[
            "credit_status",
            "credit_note",
            "credit_approved_by",
            "credit_approved_at",
            "updated_at",
        ]
    )
    return business


def refresh_overdue_flags() -> int:
    """
    يعلّم الفواتير المتأخرة — **للعرض والتقارير فقط**.

    ⚠️  قرارات المنع **لا تعتمد على هذا الحقل**.

        `evaluate_credit` تستعلم عن `due_on` مباشرةً. لو اعتمدت
        على الحالة المخزَّنة لصار تعطّل المهمة الدورية ثغرة صامتة:
        فواتير متأخرة تبدو سليمة فيستمر الائتمان.
    """
    updated = Invoice.objects.filter(
        status=InvoiceStatus.ISSUED, due_on__lt=timezone.localdate()
    ).update(status=InvoiceStatus.OVERDUE)

    if updated:
        logger.info("عُلّمت %s فاتورة كمتأخرة", updated)
    return updated
