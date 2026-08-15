"""
خدمات المالية.

⚠️  **الالتقاط لا الحساب.**

    الإيراد يُقيَّد لحظة اكتمال الطلب من أرقام الطلب المخزَّنة
    (ADR-30)، والتكلفة من حركات المخزون التي وقعت فعلًا. لا شيء
    هنا يعيد حساب سعر أو ضريبة — إعادة الحساب من قيم اليوم تنتج
    تقريرًا يخالف الفواتير الصادرة.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.errors import BusinessError, ErrorCode
from core.money import ZERO, quantize
from finance.models import (
    COGSEntry,
    Expense,
    ExpenseStatus,
    FiscalPeriod,
    RevenueEntry,
    RevenueSource,
)

logger = logging.getLogger(__name__)


def _money_sum(queryset, field: str) -> Decimal:
    """مجموع مالي لا يعيد `None` أبدًا."""
    total = queryset.aggregate(
        total=Coalesce(
            Sum(field), Value(ZERO), output_field=DecimalField(max_digits=14, decimal_places=2)
        )
    )["total"]
    return quantize(total)


# ═══════════════════════════════════════════════════════════
#  التقاط الإيراد
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def record_order_revenue(order) -> RevenueEntry | None:
    """
    يقيّد إيراد طلب مكتمل — **مرة واحدة مهما تكرّر الحدث**.

    ⚠️  الازدواج يُمنع بقيد قاعدة البيانات لا بفحص هنا وحده.

        الفحص المسبق يخسر السباق بين حدثين متزامنين؛ والقيد
        الفريد يحسمه. الفحص هنا يوفّر الاستثناء في الحالة الشائعة.
    """
    existing = RevenueEntry.objects.filter(source=RevenueSource.ORDER, order=order).first()
    if existing is not None:
        logger.info("إيراد الطلب %s مقيَّد سلفًا — تجاهل", order.number)
        return existing

    # ⚠️  الضريبة تُطرح من الإيراد.
    #
    #     المتجر يحصّلها نيابةً عن الدولة ولا يملكها. احتسابها
    #     إيرادًا يضخّم الربح بنسبتها كاملة — وهو خطأ يمرّ صامتًا
    #     لأن الرقم يبدو أكبر لا أصغر.
    net = quantize(order.grand_total - order.tax_total)

    entry = RevenueEntry.objects.create(
        source=RevenueSource.ORDER,
        order=order,
        gross=order.subtotal,
        discounts=order.discount_total,
        tax=order.tax_total,
        net=net,
        channel=order.channel,
        # ⚠️  تاريخ اكتمال الطلب لا تاريخ اليوم: إعادة تشغيل
        #     الالتقاط لطلبات قديمة كانت ستكدّسها في شهر واحد.
        occurred_on=(order.completed_at or timezone.now()).date(),
    )

    record_cogs(entry)
    return entry


@transaction.atomic
def record_refund(order, amount: Decimal | None = None) -> RevenueEntry | None:
    """
    قيد مرتجع — **سالب**.

    ⚠️  لا يُحذف قيد الإيراد الأصلي.

        حذفه يمحو أن البيعة وقعت، فيختل عدد الطلبات ومتوسط قيمة
        الطلب وكل ما يُبنى عليهما. التصحيح بقيد معاكس.
    """
    if RevenueEntry.objects.filter(source=RevenueSource.REFUND, order=order).exists():
        return None

    original = RevenueEntry.objects.filter(source=RevenueSource.ORDER, order=order).first()
    if original is None:
        # مرتجع لطلب لم يُقيَّد إيراده — لا شيء يُعكَس
        logger.warning("مرتجع الطلب %s بلا قيد إيراد أصلي", order.number)
        return None

    refunded = original.net if amount is None else quantize(amount)

    return RevenueEntry.objects.create(
        source=RevenueSource.REFUND,
        order=order,
        gross=-original.gross,
        discounts=-original.discounts,
        tax=-original.tax,
        net=-refunded,
        channel=original.channel,
        occurred_on=timezone.now().date(),
    )


@transaction.atomic
def record_cogs(entry: RevenueEntry) -> COGSEntry:
    """
    تكلفة البضاعة المباعة لقيد إيراد.

    ⚠️  **من حركات المخزون لا من الكتالوج.**

        الحركة تحمل الدفعة التي خرجت منها البضاعة وتكلفتها
        وقتها (FEFO). أي حساب آخر — متوسط · آخر تكلفة شراء —
        يعطي ربحًا لا يطابق بيعة وقعت، ويتغيّر بأثر رجعي كلما
        وصلت دفعة جديدة.

    ⚠️  و**تُحدِّث القيد القائم لا تُنشئ ثانيًا**.

        بيعة الكاونتر تُنشئ الطلب قبل أن تُربَط حركات مخزونها به،
        فأول حساب يقع على صفر حركات. `pos_sale_completed` تُعيد
        الاستدعاء بعد الربط — ولولا التحديث لانفجرت على قيد
        `OneToOne` قائم، ولبقيت كل بيعة كاونتر بتكلفة صفر.
    """
    from inventory.models import MovementType, StockMovement

    movements = StockMovement.objects.filter(
        movement_type=MovementType.SALE,
        reference_type="order",
        reference_id=str(entry.order_id),
    )

    total = ZERO
    quantity = 0
    unknown = 0

    for movement in movements:
        quantity += movement.quantity
        if movement.unit_cost is None:
            # ⚠️  بضاعة بلا دفعة: تكلفتها مجهولة لا صفر.
            #     الصفر يجعل الربح يظهر أعلى بثمنها كاملًا.
            unknown += movement.quantity
            continue
        total += movement.unit_cost * movement.quantity

    if unknown:
        logger.warning(
            "تكلفة مجهولة لـ %s وحدة في الطلب %s — بضاعة بلا دفعة",
            unknown,
            entry.order_id,
        )

    cogs, _ = COGSEntry.objects.update_or_create(
        revenue_entry=entry,
        defaults={
            "amount": quantize(total),
            "quantity": quantity,
            "unknown_quantity": unknown,
        },
    )
    return cogs


# ═══════════════════════════════════════════════════════════
#  المصروفات
# ═══════════════════════════════════════════════════════════


def assert_period_open(on_date: date) -> None:
    """
    ⚠️  الفترة المقفلة ترفض الكتابة.

        تقرير صدر واتُّخذ عليه قرار ثم تغيّر بأثر رجعي هو أسوأ ما
        يقع في نظام مالي: لا أحد يعرف أي نسخة كانت صحيحة.
    """
    if FiscalPeriod.is_locked(on_date):
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail=f"الفترة {on_date.year}-{on_date.month:02d} مقفلة — قيّد التصحيح في فترة مفتوحة",
            status_code=409,
        )


@transaction.atomic
def approve_expense(expense: Expense, *, approved_by) -> Expense:
    """
    ⚠️  الاعتماد **فعل منفصل عن الإدخال** — ومن شخص آخر مبدئيًا.

        قاعدة العمل ١٣ لم تُحسم بعد فيمن يعتمد؛ الحالي: أي مالي
        مخوَّل. الفصل نفسه هو ما يجعل تشديدها لاحقًا تعديل صلاحية
        لا إعادة بناء.
    """
    if expense.status == ExpenseStatus.APPROVED:
        raise BusinessError(ErrorCode.CONFLICT, detail="المصروف معتمد سلفًا", status_code=409)

    assert_period_open(expense.incurred_on)

    expense.status = ExpenseStatus.APPROVED
    expense.approved_by = approved_by
    expense.approved_at = timezone.now()
    expense.rejection_reason = ""
    expense.save(
        update_fields=["status", "approved_by", "approved_at", "rejection_reason", "updated_at"]
    )
    return expense


@transaction.atomic
def reject_expense(expense: Expense, *, rejected_by, reason: str) -> Expense:
    """⚠️  السبب إلزامي: رفض بلا سبب يُعاد إدخاله كما هو."""
    if not reason.strip():
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="سبب الرفض إلزامي")

    expense.status = ExpenseStatus.REJECTED
    expense.approved_by = rejected_by
    expense.approved_at = timezone.now()
    expense.rejection_reason = reason
    expense.save(
        update_fields=["status", "approved_by", "approved_at", "rejection_reason", "updated_at"]
    )
    return expense


# ═══════════════════════════════════════════════════════════
#  قائمة الأرباح والخسائر
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ProfitAndLoss:
    """
    قائمة أرباح لفترة.

    ⚠️  كل حقل هنا **مجموع صفوف قابلة للعرض** لا رقم مشتق.

        `net_profit` وحده محسوب — وبقية الحقول تُفتح على قيودها.
    """

    start: date
    end: date

    revenue: Decimal
    refunds: Decimal
    discounts: Decimal
    tax_collected: Decimal
    net_sales: Decimal

    cogs: Decimal
    gross_profit: Decimal

    expenses: Decimal
    net_profit: Decimal

    #: ⚠️  عدد الوحدات المباعة بتكلفة مجهولة — يجعل مجمل الربح
    #:     أعلى من حقيقته. يُعرَض ولا يُبتلع.
    unknown_cost_units: int

    #: مصروفات مسوّدة لم تُعتمد — خارج الحساب لكن يجب أن تُرى
    pending_expenses: Decimal

    @property
    def gross_margin(self) -> Decimal:
        """هامش مجمل الربح ٪ — أو صفر بلا مبيعات (لا قسمة على صفر)."""
        if self.net_sales == ZERO:
            return ZERO
        return quantize(self.gross_profit / self.net_sales * Decimal("100"))

    @property
    def is_reliable(self) -> bool:
        """⚠️  تقرير فيه تكلفة مجهولة يُقرأ بحذر — ويُقال ذلك صراحةً."""
        return self.unknown_cost_units == 0


def profit_and_loss(start: date, end: date) -> ProfitAndLoss:
    """
    ```text
    الإيراد − المرتجعات − الخصومات
      = صافي المبيعات
      − تكلفة البضاعة المباعة
      = مجمل الربح
      − المصروفات التشغيلية
      = صافي الربح
    ```

    ⚠️  المرتجعات **قيود سالبة أصلًا** فتُجمَع لا تُطرح.

        طرحها مرة ثانية كان يضاعف أثرها — وهو خطأ إشارة لا يظهر
        إلا حين يقع مرتجع، أي بعد أن يكون التقرير قد صدر مرارًا.
    """
    entries = RevenueEntry.objects.filter(occurred_on__gte=start, occurred_on__lte=end)

    sales = entries.filter(source=RevenueSource.ORDER)
    refunds = entries.filter(source=RevenueSource.REFUND)

    revenue = _money_sum(sales, "net")
    refunded = _money_sum(refunds, "net")  # سالب سلفًا
    discounts = _money_sum(sales, "discounts")
    tax = _money_sum(sales, "tax")

    net_sales = quantize(revenue + refunded)

    cogs_rows = COGSEntry.objects.filter(revenue_entry__in=entries)
    cogs = _money_sum(cogs_rows.filter(revenue_entry__source=RevenueSource.ORDER), "amount")
    unknown_units = (
        cogs_rows.aggregate(total=Coalesce(Sum("unknown_quantity"), Value(0)))["total"] or 0
    )

    gross_profit = quantize(net_sales - cogs)

    period_expenses = Expense.objects.filter(incurred_on__gte=start, incurred_on__lte=end)
    expenses = _money_sum(period_expenses.filter(status=ExpenseStatus.APPROVED), "amount")
    pending = _money_sum(period_expenses.filter(status=ExpenseStatus.DRAFT), "amount")

    return ProfitAndLoss(
        start=start,
        end=end,
        revenue=revenue,
        refunds=refunded,
        discounts=discounts,
        tax_collected=tax,
        net_sales=net_sales,
        cogs=cogs,
        gross_profit=gross_profit,
        expenses=expenses,
        net_profit=quantize(gross_profit - expenses),
        unknown_cost_units=unknown_units,
        pending_expenses=pending,
    )


def expenses_by_category(start: date, end: date) -> list[dict]:
    """تفصيل المصروفات المعتمدة ببندها — لقراءة «أين صُرف المال»."""
    rows = (
        Expense.objects.filter(
            incurred_on__gte=start,
            incurred_on__lte=end,
            status=ExpenseStatus.APPROVED,
        )
        .values("category__code", "category__name_ar", "category__name_en")
        .annotate(total=Sum("amount"))
        .order_by("-total")
    )

    return [
        {
            "code": row["category__code"],
            "name_ar": row["category__name_ar"],
            "name_en": row["category__name_en"],
            "total": str(quantize(row["total"])),
        }
        for row in rows
    ]


def revenue_by_channel(start: date, end: date) -> list[dict]:
    """
    الإيراد بالقناة — أونلاين مقابل الكاونتر.

    ⚠️  يشمل المرتجعات في نفس القناة، وإلا بدت قناة كثيرة
        المرتجعات أربح مما هي.
    """
    rows = (
        RevenueEntry.objects.filter(occurred_on__gte=start, occurred_on__lte=end)
        .values("channel")
        .annotate(total=Sum("net"))
        .order_by("-total")
    )
    return [
        {"channel": row["channel"] or "—", "total": str(quantize(row["total"]))} for row in rows
    ]


# ═══════════════════════════════════════════════════════════
#  التدفق النقدي
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CashFlow:
    """
    الوارد والصادر النقدي.

    ⚠️  **مشتق لا مخزَّن — وهذا قرار.**

        الوارد يعرفه `payments` والصادر تعرفه المصروفات. تخزينه
        ثالثًا ينشئ رقمًا يجب أن يوازي مصدرين، وأول انحراف بينهما
        لا يملك أحد حسمه. الاشتقاق أبطأ بقدر لا يُلاحَظ على مدى
        شهر، ولا يكذب أبدًا.
    """

    start: date
    end: date
    cash_in: Decimal
    cash_out: Decimal

    @property
    def net(self) -> Decimal:
        return quantize(self.cash_in - self.cash_out)


def cash_flow(start: date, end: date) -> CashFlow:
    from payments.models import PaymentTransaction, TransactionStatus

    incoming = PaymentTransaction.objects.filter(
        created_at__date__gte=start,
        created_at__date__lte=end,
        status__in=[TransactionStatus.CAPTURED, TransactionStatus.AUTHORIZED],
    )

    outgoing = Expense.objects.filter(
        incurred_on__gte=start,
        incurred_on__lte=end,
        status=ExpenseStatus.APPROVED,
    )

    return CashFlow(
        start=start,
        end=end,
        cash_in=_money_sum(incoming, "amount"),
        cash_out=_money_sum(outgoing, "amount"),
    )
