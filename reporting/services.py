"""
التقارير.

⚠️  **هذا النطاق يقرأ ولا يكتب — أبدًا.**

    لا موديل فيه ولا `migrations`. كل رقم يُشتق من مصدره لحظة
    الطلب: المبيعات من `orders`، والمخزون من `inventory`، والربح
    من `finance`.

    تخزين نسخة مُجمَّعة هنا ينشئ رقمًا ثالثًا يجب أن يوازي مصدرين،
    وأول انحراف بينهما لا يملك أحد حسمه. وحين يكبر الحجم يُضاف
    تخزين مؤقت (cache) بمدة صلاحية — لا جدول حقيقة موازٍ.

⚠️  ولا نطاق يستورد `reporting`.

    هو الطبقة العليا: يعرف الجميع ولا يعرفه أحد — كـ`devtools`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Sum, Value
from django.db.models.functions import (
    Coalesce,
    ExtractHour,
    ExtractIsoWeekDay,
    TruncDate,
)
from django.utils import timezone

from core.errors import BusinessError, ErrorCode
from core.money import ZERO, quantize

#: ⚠️  `unit_price × quantity` يخلط `Decimal` بعدد صحيح.
#
#     Django لا يستنتج نوع الناتج من الطرفين المختلفين، فيرفض
#     التجميع بـ`FieldError` غامضة. التصريح بالنوع مرة واحدة هنا
#     أوضح من تكراره في كل استعلام — والدقة المالية تتبعه.
#
# ⚠️  ولا تُسمَّ أي حزمة تجميع في نفس الاستدعاء `quantity`.
#
#     الأسماء تُحَلّ بالترتيب داخل `annotate` الواحدة: تسمية
#     `quantity=Sum("quantity")` تجعل `F("quantity")` هنا يشير
#     إلى **التجميع** لا إلى الحقل — فيرفض Django «تجميعًا داخل
#     تجميع» برسالة لا تدلّ على السبب إطلاقًا. ولذلك الاسم
#     `units_sold`.
LINE_REVENUE = ExpressionWrapper(
    F("unit_price") * F("quantity"),
    output_field=DecimalField(max_digits=18, decimal_places=2),
)


def _money(queryset, field: str) -> Decimal:
    total = queryset.aggregate(
        total=Coalesce(
            Sum(field),
            Value(ZERO),
            output_field=DecimalField(max_digits=18, decimal_places=2),
        )
    )["total"]
    return quantize(total)


def assert_period(start: date, end: date) -> None:
    """
    ⚠️  المدى المقلوب يُنتج تقريرًا بأصفار **يبدو حقيقيًا**.

        لا خطأ ولا صفوف، فيُقرأ «شهر بلا مبيعات» بدل «مدى خاطئ».
    """
    if start > end:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="بداية الفترة بعد نهايتها")


def _sold_orders(start: date, end: date):
    """
    الطلبات المحتسَبة مبيعاتٍ في فترة.

    ⚠️  **مصدر واحد لتعريف «مبيعة»** يستخدمه كل تقرير هنا.

        تعريفه في كل دالة يجعل تقرير المبيعات يستبعد الملغى
        وتقرير الأصناف يشمله — فيختلف رقمان في نفس الشاشة ولا
        يعرف أحد أيّهما صحيح.
    """
    from orders.models import Order, OrderStatus

    return Order.objects.filter(created_at__date__gte=start, created_at__date__lte=end).exclude(
        status__in=[OrderStatus.CANCELLED, OrderStatus.REFUNDED]
    )


# ═══════════════════════════════════════════════════════════
#  المبيعات
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SalesSummary:
    start: date
    end: date
    orders_count: int
    gross_sales: Decimal
    returns_total: Decimal
    net_sales: Decimal
    average_order: Decimal
    customers_count: int


def sales_summary(start: date, end: date) -> SalesSummary:
    from orders.models import Order, OrderStatus

    assert_period(start, end)

    sold = _sold_orders(start, end)
    returned = Order.objects.filter(
        created_at__date__gte=start,
        created_at__date__lte=end,
        status=OrderStatus.REFUNDED,
    )

    gross = _money(sold, "grand_total")
    returns_total = _money(returned, "grand_total")
    count = sold.count()

    return SalesSummary(
        start=start,
        end=end,
        orders_count=count,
        gross_sales=gross,
        returns_total=returns_total,
        net_sales=quantize(gross - returns_total),
        # ⚠️  حارس القسمة على صفر — فترة بلا طلبات حالة عادية
        average_order=quantize(gross / count) if count else ZERO,
        customers_count=sold.values("customer").distinct().count(),
    )


def sales_by_day(start: date, end: date) -> list[dict]:
    """
    ⚠️  استعلام واحد بالتجميع لا استعلام لكل يوم.

        حلقة على ثلاثين يومًا تعني ثلاثين استعلامًا في كل فتح
        للوحة — وهي أول شاشة يفتحها الأدمن كل صباح.
    """
    assert_period(start, end)

    rows = (
        _sold_orders(start, end)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(orders=Count("id"), total=Sum("grand_total"))
        .order_by("day")
    )

    return [
        {
            "day": row["day"].isoformat(),
            "orders": row["orders"],
            "total": str(quantize(row["total"] or ZERO)),
        }
        for row in rows
    ]


def sales_by_channel(start: date, end: date) -> list[dict]:
    assert_period(start, end)

    rows = (
        _sold_orders(start, end)
        .values("channel")
        .annotate(orders=Count("id"), total=Sum("grand_total"))
        .order_by("-total")
    )
    return [
        {
            "channel": row["channel"] or "—",
            "orders": row["orders"],
            "total": str(quantize(row["total"] or ZERO)),
        }
        for row in rows
    ]


#: ترتيب «الأكثر طلبًا» — القيمة أو العدد.
TOP_PRODUCT_ORDERINGS = {"revenue": "-revenue", "quantity": "-units_sold"}


def top_products(start: date, end: date, limit: int = 20, by: str = "revenue") -> list[dict]:
    """
    الأصناف الأكثر طلبًا.

    ⚠️  **المقياسان مختلفان وكلاهما صحيح.**

        بالقيمة: علبة كمامات بجنيهين تُباع ألف مرة لا تسبق جهازًا
        بألف جنيه بيع عشرين — والقرار الشرائي يُبنى على القيمة.

        بالعدد: «الأكثر طلبًا» بمعناه الحرفي، وهو ما يُبنى عليه
        قرار المخزون ومساحة الرفّ.

        ولذلك الرقمان يُعرضان معًا دائمًا، والفرز خيار لا حكم.

    ⚠️  والمفتاح غير المعروف **يُرفض ولا يُتجاهَل**.

        السقوط الصامت على الافتراضي يجعل `?by=units` يُرجع ترتيبًا
        بالقيمة بلا أي إشارة — فيقرأ الأدمن جدولًا يظن أنه فرزه.
    """
    from orders.models import OrderLine

    assert_period(start, end)

    ordering = TOP_PRODUCT_ORDERINGS.get(by)
    if ordering is None:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            detail=f"ترتيب غير معروف: {by} — المتاح: {' · '.join(TOP_PRODUCT_ORDERINGS)}",
        )

    rows = (
        OrderLine.objects.filter(order__in=_sold_orders(start, end))
        .values("product_id", "product_sku", "product_name_ar", "product_name_en")
        .annotate(units_sold=Sum("quantity"), revenue=Sum(LINE_REVENUE))
        .order_by(ordering)[:limit]
    )

    return [
        {
            "product": str(row["product_id"]),
            "sku": row["product_sku"],
            "name_ar": row["product_name_ar"],
            "name_en": row["product_name_en"],
            "quantity": row["units_sold"],
            "revenue": str(quantize(row["revenue"] or ZERO)),
        }
        for row in rows
    ]


def sales_by_category(start: date, end: date, limit: int = 20) -> list[dict]:
    from orders.models import OrderLine

    assert_period(start, end)

    rows = (
        OrderLine.objects.filter(order__in=_sold_orders(start, end))
        .values(
            "product__category__slug", "product__category__name_ar", "product__category__name_en"
        )
        .annotate(units_sold=Sum("quantity"), revenue=Sum(LINE_REVENUE))
        .order_by("-revenue")[:limit]
    )

    return [
        {
            "slug": row["product__category__slug"] or "—",
            "name_ar": row["product__category__name_ar"] or "—",
            "name_en": row["product__category__name_en"] or "—",
            "quantity": row["units_sold"],
            "revenue": str(quantize(row["revenue"] or ZERO)),
        }
        for row in rows
    ]


# ═══════════════════════════════════════════════════════════
#  أوقات الضغط
# ═══════════════════════════════════════════════════════════


#: أيام الأسبوع بترتيب ISO — الاثنين ١ والأحد ٧.
WEEKDAY_NAMES = {
    1: ("الاثنين", "Monday"),
    2: ("الثلاثاء", "Tuesday"),
    3: ("الأربعاء", "Wednesday"),
    4: ("الخميس", "Thursday"),
    5: ("الجمعة", "Friday"),
    6: ("السبت", "Saturday"),
    7: ("الأحد", "Sunday"),
}


def peak_hours(start: date, end: date) -> dict:
    """
    توزيع الطلبات على ساعات الأسبوع — ١٦٨ خلية (٧ أيام × ٢٤ ساعة).

    ⚠️  **بالتوقيت المحلي لا UTC.**

        «أكثر ساعة ضغطًا ١٧:٠٠ UTC» رقم لا يُبنى عليه جدول
        مناوبات في القاهرة. `Extract` يحوّل إلى المنطقة الفعّالة
        تلقائيًا حين `USE_TZ`، والمنطقة تُقرأ من الإعدادات.

    ⚠️  والشبكة **مكتملة دائمًا**.

        الاستعلام لا يُرجع صفًا لساعة بلا طلبات، وخريطة حرارية
        بخلايا ناقصة تُرسم مشوّهة. الأصفار تُملأ هنا مرة واحدة
        لا في كل واجهة تستهلك التقرير.

    ⚠️  والأساس **وقت إنشاء الطلب** لا وقت الدفع أو التسليم.

        الضغط الذي نقيسه ضغط على المتجر والمخزون لحظة الشراء؛
        وقت التسليم يقيس ضغطًا على الشحن — سؤال آخر.
    """
    assert_period(start, end)

    rows = (
        _sold_orders(start, end)
        .annotate(weekday=ExtractIsoWeekDay("created_at"), hour=ExtractHour("created_at"))
        .values("weekday", "hour")
        .annotate(orders=Count("id"), total=Sum("grand_total"))
    )

    grid = {(row["weekday"], row["hour"]): row for row in rows}

    cells = []
    for weekday in range(1, 8):
        for hour in range(24):
            row = grid.get((weekday, hour))
            cells.append(
                {
                    "weekday": weekday,
                    "hour": hour,
                    "orders": row["orders"] if row else 0,
                    "total": str(quantize(row["total"] or ZERO)) if row else str(ZERO),
                }
            )

    def _rollup(key: str, span) -> list[dict]:
        totals = {value: {"orders": 0, "total": ZERO} for value in span}
        for cell in cells:
            bucket = totals[cell[key]]
            bucket["orders"] += cell["orders"]
            bucket["total"] += Decimal(cell["total"])

        return [
            {
                key: value,
                "orders": bucket["orders"],
                "total": str(quantize(bucket["total"])),
                **(
                    {
                        "name_ar": WEEKDAY_NAMES[value][0],
                        "name_en": WEEKDAY_NAMES[value][1],
                    }
                    if key == "weekday"
                    else {}
                ),
            }
            for value, bucket in totals.items()
        ]

    by_hour = _rollup("hour", range(24))
    by_weekday = _rollup("weekday", range(1, 8))

    def _busiest(rows_: list[dict]) -> dict | None:
        # ⚠️  فترة بلا طلبات تُرجع `None` لا الخلية الأولى صفرًا —
        #     «ذروتك الاثنين ١٢ ص بصفر طلب» أسوأ من لا إجابة.
        top = max(rows_, key=lambda item: item["orders"], default=None)
        return top if top and top["orders"] else None

    return {
        "start": str(start),
        "end": str(end),
        "timezone": str(timezone.get_current_timezone()),
        "orders_count": sum(cell["orders"] for cell in cells),
        "cells": cells,
        "by_hour": by_hour,
        "by_weekday": by_weekday,
        "peak_cell": _busiest(cells),
        "peak_hour": _busiest(by_hour),
        "peak_weekday": _busiest(by_weekday),
    }


# ═══════════════════════════════════════════════════════════
#  المخزون
# ═══════════════════════════════════════════════════════════


def inventory_summary() -> dict:
    """
    ⚠️  **قيمة المخزون بالتكلفة لا بسعر البيع.**

        التقييم بسعر البيع يُظهر ربحًا لم يتحقّق كأنه أصل مملوك —
        وهو خطأ محاسبي أساسي، ورقم يُقدَّم للبنك أحيانًا.
    """
    from inventory.models import Batch, Stock

    batches = Batch.objects.filter(quantity_remaining__gt=0)

    value = batches.aggregate(
        total=Coalesce(
            Sum(F("quantity_remaining") * F("unit_cost")),
            Value(ZERO),
            output_field=DecimalField(max_digits=18, decimal_places=2),
        )
    )["total"]

    below_reorder = Stock.objects.filter(quantity_physical__lte=F("reorder_point")).count()

    return {
        "stock_value_at_cost": str(quantize(value)),
        "batches": batches.count(),
        "products_below_reorder": below_reorder,
        "products_out_of_stock": Stock.objects.filter(quantity_physical=0).count(),
    }


def expiry_report(days: int = 90, limit: int = 100) -> list[dict]:
    """
    دفعات توشك على الانتهاء.

    ⚠️  **المنتهية تُدرَج أيضًا لا تُستبعَد.**

        استبعادها يجعل الشاشة تعرض ما «سينتهي» ويخفي ما **انتهى
        وما زال في المخزن** — وهو الأخطر: بضاعة قد تُباع.
    """
    from inventory.models import Batch

    horizon = timezone.localdate() + timedelta(days=days)

    rows = (
        Batch.objects.filter(
            quantity_remaining__gt=0,
            expires_at__isnull=False,
            expires_at__lte=horizon,
        )
        .select_related("product", "location")
        .order_by("expires_at")[:limit]
    )

    today = timezone.localdate()
    return [
        {
            "batch": batch.number,
            "product": str(batch.product_id),
            "sku": batch.product.sku,
            "name_ar": batch.product.name_ar,
            "name_en": batch.product.name_en,
            "location": batch.location.code,
            "quantity": batch.quantity_remaining,
            "expires_at": batch.expires_at.isoformat(),
            "days_left": (batch.expires_at - today).days,
            # ⚠️  علامة صريحة: المنتهي يُبرَز لا يُقرأ كأنه «قريب»
            "is_expired": batch.expires_at < today,
            "value_at_cost": str(quantize(batch.quantity_remaining * batch.unit_cost)),
        }
        for batch in rows
    ]


# ═══════════════════════════════════════════════════════════
#  سلوك العملاء
# ═══════════════════════════════════════════════════════════


def customer_behaviour(start: date, end: date, limit: int = 20) -> dict:
    """
    ⚠️  **العميل الجديد يُقاس بأول طلب لا بتاريخ التسجيل.**

        من سجّل قبل سنة واشترى اليوم أول مرة هو عميل جديد تجاريًا؛
        وعدّه قديمًا يجعل كل حملة تسويق تبدو بلا أثر.
    """
    from customers.models import CustomerProfile

    assert_period(start, end)

    sold = _sold_orders(start, end)

    new_customers = CustomerProfile.objects.filter(
        first_order_at__date__gte=start, first_order_at__date__lte=end
    ).count()

    returning = sold.values("customer").annotate(orders=Count("id")).filter(orders__gt=1).count()

    top = (
        CustomerProfile.objects.filter(orders__in=sold)
        .annotate(period_total=Sum("orders__grand_total"), period_orders=Count("orders"))
        .order_by("-period_total")[:limit]
    )

    return {
        "new_customers": new_customers,
        "returning_customers": returning,
        "active_customers": sold.values("customer").distinct().count(),
        "top_customers": [
            {
                "customer": str(profile.pk),
                "customer_number": profile.customer_number,
                "name": profile.display_name,
                "orders": profile.period_orders,
                "total": str(quantize(profile.period_total or ZERO)),
            }
            for profile in top
        ],
    }


def segment_breakdown(start: date, end: date) -> list[dict]:
    from customers.models import CustomerProfile

    assert_period(start, end)

    rows = (
        CustomerProfile.objects.filter(orders__in=_sold_orders(start, end))
        .values("segment")
        .annotate(customers=Count("id", distinct=True), total=Sum("orders__grand_total"))
        .order_by("-total")
    )

    return [
        {
            "segment": row["segment"],
            "customers": row["customers"],
            "total": str(quantize(row["total"] or ZERO)),
        }
        for row in rows
    ]


# ═══════════════════════════════════════════════════════════
#  أداء الموظفين والموردين
# ═══════════════════════════════════════════════════════════


def employee_leaderboard(start: date, end: date, limit: int = 20) -> list[dict]:
    """
    ⚠️  المنسوب هو `owner_employee` لا `created_by` — نفس تعريف
        `employees.services.performance`، وأي اختلاف بينهما يجعل
        المندوب يرى رقمين متعارضين في شاشتين.
    """
    from employees.models import EmployeeProfile

    assert_period(start, end)

    sold = _sold_orders(start, end)

    rows = (
        EmployeeProfile.objects.filter(user__orders_owned__in=sold)
        .annotate(
            orders=Count("user__orders_owned", distinct=True),
            total=Sum("user__orders_owned__grand_total"),
        )
        .select_related("user", "role")
        .order_by("-total")[:limit]
    )

    return [
        {
            "employee": str(profile.pk),
            "employee_number": profile.employee_number,
            "name": profile.user.full_name,
            "role": profile.role.name_ar,
            "orders": profile.orders,
            "total": str(quantize(profile.total or ZERO)),
        }
        for profile in rows
    ]


def supplier_purchases(start: date, end: date, limit: int = 20) -> list[dict]:
    """ما اشتريناه من كل مورّد — من أوامر الشراء المرسَلة."""
    from suppliers.models import PurchaseOrder, PurchaseOrderStatus

    assert_period(start, end)

    rows = (
        PurchaseOrder.objects.filter(
            created_at__date__gte=start,
            created_at__date__lte=end,
        )
        .exclude(status__in=[PurchaseOrderStatus.DRAFT, PurchaseOrderStatus.CANCELLED])
        .values("supplier_id", "supplier__name_ar", "supplier__name_en")
        .annotate(orders=Count("id"), total=Sum("subtotal"))
        .order_by("-total")[:limit]
    )

    return [
        {
            "supplier": str(row["supplier_id"]),
            "name_ar": row["supplier__name_ar"],
            "name_en": row["supplier__name_en"],
            "orders": row["orders"],
            "total": str(quantize(row["total"] or ZERO)),
        }
        for row in rows
    ]


# ═══════════════════════════════════════════════════════════
#  اللوحة الجامعة
# ═══════════════════════════════════════════════════════════


def overview(start: date, end: date) -> dict:
    """
    ⚠️  **الربح يُقرأ من `finance` لا يُحسب هنا.**

        حسابه ثانيةً يُنتج رقمًا يخالف قائمة الأرباح، ولا أحد
        يعرف أيّهما يُصدَّق — وهو نفس المبدأ الذي منع حساب التكلفة
        في `commissions`.
    """
    from finance import services as finance_services

    assert_period(start, end)

    sales = sales_summary(start, end)
    pnl = finance_services.profit_and_loss(start, end)

    return {
        "start": str(start),
        "end": str(end),
        "orders_count": sales.orders_count,
        "gross_sales": str(sales.gross_sales),
        "returns_total": str(sales.returns_total),
        "net_sales": str(sales.net_sales),
        "average_order": str(sales.average_order),
        "customers_count": sales.customers_count,
        # من `finance` — مصدر واحد للربح
        "cogs": str(pnl.cogs),
        "gross_profit": str(pnl.gross_profit),
        "gross_margin": str(pnl.gross_margin),
        "expenses": str(pnl.expenses),
        "net_profit": str(pnl.net_profit),
        "profit_is_reliable": pnl.is_reliable,
        "inventory": inventory_summary(),
        # ⚠️  خمسة لا عشرون — هذه لوحة لا تقرير. القائمة الكاملة
        #     في `/reports/sales/` بفرزها وحدّها.
        "top_products": top_products(start, end, limit=5),
    }
