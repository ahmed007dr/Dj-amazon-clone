"""
قياس تحقيق الأهداف.

⚠️  **المُحقَّق يُقاس من الطلبات — ولا يُخزَّن قبل الإقفال.**

    رقم مخزَّن يُحدَّث بكل طلب ينحرف عند أول إلغاء أو مرتجع لا يمرّ
    بمسار التحديث. والقياس اللحظي يعيد الحقيقة دائمًا؛ والإقفال
    وحده يُجمّدها لأنها صارت مستندًا.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import DecimalField, Sum, Value
from django.db.models.functions import Coalesce

from core.errors import BusinessError, ErrorCode
from core.money import ZERO, quantize
from targets.models import MonthlyTarget, TargetStatus, TargetType


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """
    ⚠️  آخر يوم من `calendar.monthrange` لا رقمًا مكتوبًا.

        «٣٠» تكسر يناير، و«٣١» تكسر فبراير — والخطأ يظهر كطلب
        يسقط من قياس شهره أو يُحتسب مرتين.
    """
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


@dataclass(frozen=True)
class Achievement:
    """
    قياس تحقيق — **بكل مدخلاته**.

    ⚠️  «كم حقّق؟» سؤال يُجاب برقم؛ و«لماذا؟» يُجاب بهذه الحقول.
        حجبها يجعل كل خلاف مع المندوب بلا مرجع.
    """

    target: MonthlyTarget
    start: date
    end: date

    gross_sales: Decimal
    returns_total: Decimal
    net_sales: Decimal
    gross_profit: Decimal
    orders_count: int
    customers_count: int

    achieved_value: Decimal
    achievement_percent: Decimal

    @property
    def meets_minimum(self) -> bool:
        return self.achievement_percent >= self.target.minimum_achievement_percent


def _money(queryset, field: str) -> Decimal:
    total = queryset.aggregate(
        total=Coalesce(
            Sum(field),
            Value(ZERO),
            output_field=DecimalField(max_digits=16, decimal_places=2),
        )
    )["total"]
    return quantize(total)


def measure(target: MonthlyTarget) -> Achievement:
    """
    يقيس تحقيق هدف من طلبات صاحبه في شهره.

    ⚠️  **المرتجعات تُخصم من المُحقَّق** (قاعدة العمل ١٦ — توصية).

        عدم خصمها يجعل مندوبًا يبيع ويُرجِع ويبيع ثانيةً يحقّق
        هدفه مرتين على نفس البضاعة. والخصم من الموظف **الأصلي**
        لا من مَن عالج المرتجع: هو صاحب البيعة التي انعكست.
    """
    from orders.models import Order, OrderStatus

    start, end = month_bounds(target.year, target.month)

    period = Order.objects.filter(
        owner_employee=target.employee.user,
        created_at__date__gte=start,
        created_at__date__lte=end,
    )

    # ⚠️  الملغى خارج القياس كليًا: لم يُبَع شيء فيه.
    #     أما المرتجع فقد بيع ثم عاد — يُطرح ولا يُتجاهَل.
    sold = period.exclude(status__in=[OrderStatus.CANCELLED, OrderStatus.REFUNDED])
    returned = period.filter(status=OrderStatus.REFUNDED)

    gross = _money(sold, "grand_total")
    returns_total = _money(returned, "grand_total")
    net = quantize(gross - returns_total)

    orders_count = sold.count()
    customers_count = sold.values("customer").distinct().count()
    profit = _gross_profit(sold, returned)

    achieved = {
        TargetType.SALES_AMOUNT: gross,
        TargetType.NET_SALES: net,
        TargetType.GROSS_PROFIT: profit,
        TargetType.ORDER_COUNT: Decimal(orders_count),
        TargetType.CUSTOMER_COUNT: Decimal(customers_count),
    }[target.target_type]

    # ⚠️  حارس القسمة على صفر: هدف بقيمة صفر ممكن (شهر تدريب).
    percent = (
        quantize(achieved / target.target_value * Decimal("100"))
        if target.target_value > ZERO
        else ZERO
    )

    return Achievement(
        target=target,
        start=start,
        end=end,
        gross_sales=gross,
        returns_total=returns_total,
        net_sales=net,
        gross_profit=profit,
        orders_count=orders_count,
        customers_count=customers_count,
        achieved_value=quantize(achieved),
        achievement_percent=percent,
    )


def _gross_profit(sold, returned) -> Decimal:
    """
    مجمل الربح = صافي المبيعات − تكلفة البضاعة المباعة.

    ⚠️  **التكلفة من `finance` لا من حساب موازٍ.**

        `COGSEntry` محسوبة من الدفعة التي خرجت فعلًا (FEFO).
        إعادة حسابها هنا تُنتج رقم ربح يخالف قائمة الأرباح — ولا
        أحد يعرف أيّهما يُصدَّق حين تُصرَف عمولة على أحدهما.

    ⚠️  والطلب **مجهول التكلفة يخرج من الحساب كليًا**.

        قيد تكلفة بكمية صفر يعني أنه لم يُعثر على حركة مخزون
        للطلب — لا أن بضاعته مجانية. إدخاله بتكلفة صفر يجعل ربحه
        **يساوي ثمن بيعه كاملًا**، فتُصرف عمولة على ربح لم يتحقّق.

        الاستبعاد هو الاتجاه الآمن: عمولة أقل من المستحق تُصحَّح
        بقيد؛ أما المصروفة على وهم فلا تُسترد.
    """
    from finance.models import COGSEntry, RevenueEntry, RevenueSource

    sold_ids = list(sold.values_list("id", flat=True))
    if not sold_ids:
        return ZERO

    entries = RevenueEntry.objects.filter(source=RevenueSource.ORDER, order_id__in=sold_ids)

    # ⚠️  الطلبات ذات التكلفة **المُثبَتة** وحدها.
    #
    #     `quantity > 0` تعني أن حركات مخزون وُجدت فعلًا،
    #     و`unknown_quantity = 0` تعني أن كل وحدة منها عُرفت
    #     تكلفتها. ما عدا ذلك ربح غير قابل للإثبات.
    priced = COGSEntry.objects.filter(revenue_entry__in=entries, quantity__gt=0, unknown_quantity=0)
    entries = entries.filter(cogs__in=priced)

    net_revenue = _money(entries, "net")
    cost = _money(priced, "amount")

    # المرتجعات تُخصم من الربح أيضًا — بصافيها لا بإجماليها
    returned_ids = list(returned.values_list("id", flat=True))
    if returned_ids:
        refunds = RevenueEntry.objects.filter(
            source=RevenueSource.REFUND, order_id__in=returned_ids
        )
        # قيود المرتجع سالبة أصلًا فتُجمَع
        net_revenue = quantize(net_revenue + _money(refunds, "net"))

    return quantize(net_revenue - cost)


@transaction.atomic
def close_target(target: MonthlyTarget, *, by=None) -> MonthlyTarget:
    """
    ⚠️  الإقفال **مرة واحدة** — وإعادته ترفض صراحةً.

        اللقطة تُبنى عليها عمولة تُصرَف؛ وإعادة كتابتها تغيّر
        مبلغًا خرج من الخزينة.
    """
    if target.is_closed:
        raise BusinessError(ErrorCode.CONFLICT, detail="الهدف مقفل سلفًا", status_code=409)

    if target.status != TargetStatus.ACTIVE:
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail="لا يُقفَل إلا هدف نشط — فعّله أولًا",
            status_code=409,
        )

    result = measure(target)
    target.close(achieved=result.achieved_value, percent=result.achievement_percent, by=by)
    return target


def activate(target: MonthlyTarget) -> MonthlyTarget:
    if target.is_closed:
        raise BusinessError(
            ErrorCode.CONFLICT, detail="الهدف مقفل — لا يُعاد تفعيله", status_code=409
        )

    target.status = TargetStatus.ACTIVE
    target.save(update_fields=["status", "updated_at"])
    return target


def current_target(employee, on_date: date | None = None) -> MonthlyTarget | None:
    """
    هدف الشهر الجاري — **النشط وحده**.

    ⚠️  المسوّدة لا تُعرَض للمندوب: رقم لم يُعتمَد بعد يبني عليه
        توقّعًا ثم يتغيّر.
    """
    today = on_date or date.today()
    return MonthlyTarget.objects.filter(
        employee=employee,
        year=today.year,
        month=today.month,
        status__in=[TargetStatus.ACTIVE, TargetStatus.CLOSED],
    ).first()


def bulk_create_month(year: int, month: int, rows: list[dict], *, actor=None) -> int:
    """
    إنشاء أهداف شهر لفريق كامل.

    ⚠️  الموجود **يُتخطّى لا يُكتب فوقه**.

        الإنشاء الجماعي يُشغَّل مرارًا لإضافة موظف جديد؛ والكتابة
        فوق الموجود تمحو تعديلًا يدويًا على هدف مندوب بعينه.
    """
    from employees.models import EmployeeProfile

    created = 0
    for row in rows:
        employee = EmployeeProfile.objects.filter(pk=row["employee"]).first()
        if employee is None:
            continue

        _, was_created = MonthlyTarget.objects.get_or_create(
            employee=employee,
            year=year,
            month=month,
            defaults={
                "target_type": row.get("target_type", TargetType.NET_SALES),
                "target_value": row["target_value"],
                "minimum_achievement_percent": row.get("minimum_achievement_percent", ZERO),
                "note": row.get("note", ""),
            },
        )
        created += int(was_created)

    return created
