"""
Order and payment datasets.

⚠️  **Order lines are the dataset an analyst actually wants.**

    The order header answers "how many orders and for how much". Every real
    question — which product sells with which, what the margin per line was,
    which category carries the discounts — is one grain finer than that. So the
    line-level sheet is here as a first-class dataset rather than something to
    be reconstructed by joining two exports in Excel.

⚠️  And the line carries the **name and price as they were at the time of sale.**

    `OrderLine` stores `product_sku` and `product_name_ar` as text alongside the
    foreign key, precisely because a product gets renamed and repriced. Reading
    the current product's name instead would rewrite history: last year's report
    would show this year's names, and its revenue would stop reconciling with
    the invoice the customer holds.
"""

from __future__ import annotations

from core.permissions import CanManageOrders
from orders.models import Order, OrderChannel, OrderLine, OrderStatus, PaymentStatus
from payments.models import PaymentTransaction, TransactionStatus
from reporting.export.datasets import _common
from reporting.export.registry import Column, Dataset, Filter, Group, register
from reporting.export.writer import Kind

# ═══════════════════════════════════════════════════════════
#  Orders
# ═══════════════════════════════════════════════════════════


def _order_qs(filters: dict):
    queryset = Order.objects.select_related("customer", "location", "owner_employee")
    queryset = _common.apply_period(queryset, filters, "created_at")

    if status := filters.get("status"):
        queryset = queryset.filter(status=status)
    if channel := filters.get("channel"):
        queryset = queryset.filter(channel=channel)
    if payment_status := filters.get("payment_status"):
        queryset = queryset.filter(payment_status=payment_status)

    return queryset.order_by("-created_at")


def _order_columns(include_contact: bool) -> list[Column]:
    columns = [
        Column("رقم الطلب", width=20),
        Column("التاريخ", Kind.DATETIME),
        Column("الحالة", width=18),
        Column("حالة الدفع", width=18),
        Column("القناة", width=14),
        Column("رقم العميل", width=18),
        Column("الفرع", width=16),
        Column("الإجمالي قبل الخصم", Kind.MONEY),
        Column("الخصم", Kind.MONEY),
        Column("خصم الكوبون", Kind.MONEY),
        Column("الضريبة", Kind.MONEY),
        Column("الشحن", Kind.MONEY),
        Column("الإجمالي النهائي", Kind.MONEY),
        Column("الكوبون", width=16),
        Column("المحافظة", width=16),
        Column("المدينة", width=16),
        Column("تاريخ التأكيد", Kind.DATETIME),
        Column("تاريخ الإتمام", Kind.DATETIME),
    ]
    if include_contact:
        # ⚠️  The recipient's name and phone are on the **order**, not only on
        #     the customer — a counter sale has no customer record at all. Same
        #     gate, same reason.
        columns += [
            Column("المستلم", width=24, sensitive=True),
            Column("هاتف المستلم", width=18, sensitive=True),
        ]
    return columns


def _order_rows(filters: dict, include_contact: bool):
    fields = (
        "number",
        "created_at",
        "status",
        "payment_status",
        "channel",
        "customer__customer_number",
        "location__code",
        "subtotal",
        "discount_total",
        "coupon_discount",
        "tax_total",
        "shipping_total",
        "grand_total",
        "coupon_code",
        "governorate",
        "city",
        "confirmed_at",
        "completed_at",
    )
    if include_contact:
        fields += ("recipient_name", "recipient_phone")

    for row in _order_qs(filters).values_list(*fields).iterator(chunk_size=_common.CHUNK):
        yield (
            *row[:2],
            _common.labelled(row[2], OrderStatus.choices),
            _common.labelled(row[3], PaymentStatus.choices),
            _common.labelled(row[4], OrderChannel.choices),
            *row[5:],
        )


register(
    Dataset(
        key="orders",
        label="الطلبات",
        group=Group.SALES,
        permission=CanManageOrders,
        has_contact=True,
        note="رأس الطلب بمبالغه — وبنود الطلبات مجموعة منفصلة",
        filters=[
            Filter(key="start", label="من تاريخ", kind="date"),
            Filter(key="end", label="إلى تاريخ", kind="date"),
            Filter(key="status", label="الحالة", kind="choice", source="order_statuses"),
            Filter(
                key="payment_status",
                label="حالة الدفع",
                kind="choice",
                source="payment_statuses",
            ),
            Filter(key="channel", label="القناة", kind="choice", source="order_channels"),
        ],
        columns=_order_columns,
        rows=_order_rows,
        count=lambda filters: _order_qs(filters).count(),
    )
)


# ═══════════════════════════════════════════════════════════
#  Order lines
# ═══════════════════════════════════════════════════════════


def _line_qs(filters: dict):
    queryset = OrderLine.objects.select_related("order", "order__customer", "product")

    # ⚠️  Mandatory period, like stock movements: this table grows by several
    #     rows per order forever, and it is the largest thing anybody will try
    #     to export.
    queryset = _common.apply_period(queryset, filters, "order__created_at", required=True)

    if status := filters.get("status"):
        queryset = queryset.filter(order__status=status)
    if channel := filters.get("channel"):
        queryset = queryset.filter(order__channel=channel)
    if sku := filters.get("sku"):
        queryset = queryset.filter(product_sku=sku)

    return queryset.order_by("-order__created_at", "order__number")


def _line_rows(filters: dict, include_contact: bool):
    for row in (
        _line_qs(filters)
        .values_list(
            "order__number",
            "order__created_at",
            "order__status",
            "order__channel",
            "order__customer__customer_number",
            "product_sku",
            "product_name_ar",
            "product__category__path",
            "quantity",
            "list_price",
            "unit_price",
            "discount_amount",
            "tax_rate",
            "tax_amount",
            "unit_cost",
        )
        .iterator(chunk_size=_common.CHUNK)
    ):
        quantity, unit_price, discount = row[8], row[10], row[11]
        unit_cost = row[14]

        # ⚠️  The line total and the margin are computed here rather than left
        #     as Excel formulas.
        #
        #     An exported formula recalculates when the file is opened, so a
        #     report saved in March quietly changes its own numbers when someone
        #     reopens it — and worse, a formula referencing a column that a
        #     reader has sorted or inserted into produces a plausible wrong number.
        line_total = (unit_price or 0) * quantity - (discount or 0)
        margin = line_total - (unit_cost or 0) * quantity if unit_cost is not None else None

        yield (
            row[0],
            row[1],
            _common.labelled(row[2], OrderStatus.choices),
            _common.labelled(row[3], OrderChannel.choices),
            *row[4:14],
            line_total,
            unit_cost,
            margin,
        )


register(
    Dataset(
        key="order-lines",
        label="بنود الطلبات",
        group=Group.SALES,
        permission=CanManageOrders,
        note="سطر لكل منتج في كل طلب — بالتكلفة وهامش الربح. الفترة إلزامية",
        filters=[
            Filter(key="start", label="من تاريخ", kind="date", required=True),
            Filter(key="end", label="إلى تاريخ", kind="date", required=True),
            Filter(key="status", label="حالة الطلب", kind="choice", source="order_statuses"),
            Filter(key="channel", label="القناة", kind="choice", source="order_channels"),
            Filter(key="sku", label="رمز منتج بعينه", kind="text"),
        ],
        columns=lambda contact: [
            Column("رقم الطلب", width=20),
            Column("تاريخ الطلب", Kind.DATETIME),
            Column("حالة الطلب", width=18),
            Column("القناة", width=14),
            Column("رقم العميل", width=18),
            Column("رمز المنتج", width=18),
            Column("اسم المنتج وقت البيع", width=32),
            Column("مسار الفئة", width=26),
            Column("الكمية", Kind.INT),
            Column("سعر القائمة", Kind.MONEY),
            Column("سعر البيع", Kind.MONEY),
            Column("الخصم", Kind.MONEY),
            Column("نسبة الضريبة", Kind.MONEY),
            Column("مبلغ الضريبة", Kind.MONEY),
            Column("إجمالي السطر", Kind.MONEY),
            Column("تكلفة الوحدة", Kind.MONEY),
            Column("هامش السطر", Kind.MONEY),
        ],
        rows=_line_rows,
        count=lambda filters: _line_qs(filters).count(),
    )
)


# ═══════════════════════════════════════════════════════════
#  Payments
# ═══════════════════════════════════════════════════════════


def _payment_qs(filters: dict):
    queryset = PaymentTransaction.objects.select_related("provider", "customer")
    queryset = _common.apply_period(queryset, filters, "created_at")

    if status := filters.get("status"):
        queryset = queryset.filter(status=status)
    if provider := filters.get("provider"):
        queryset = queryset.filter(provider__code=provider)

    return queryset.order_by("-created_at")


def _payment_rows(filters: dict, include_contact: bool):
    # ⚠️  No `provider_response`, no `idempotency_key`, no provider credential.
    #
    #     The gateway's raw response is an opaque blob that can carry card
    #     metadata and internal identifiers; the idempotency key is a replay
    #     token. Neither answers any analytical question, and both are exactly
    #     what section 10 of the API conventions forbids putting in a response.
    for row in (
        _payment_qs(filters)
        .values_list(
            "reference",
            "created_at",
            "provider__code",
            "method",
            "amount",
            "currency",
            "status",
            "reference_type",
            "customer__customer_number",
            "failure_code",
            "authorized_at",
            "captured_at",
        )
        .iterator(chunk_size=_common.CHUNK)
    ):
        yield (*row[:6], _common.labelled(row[6], TransactionStatus.choices), *row[7:])


register(
    Dataset(
        key="payments",
        label="المدفوعات",
        group=Group.SALES,
        permission=CanManageOrders,
        note="بلا استجابة البوابة ولا مفاتيح التكرار — تلك ليست بيانات تحليل",
        filters=[
            Filter(key="start", label="من تاريخ", kind="date"),
            Filter(key="end", label="إلى تاريخ", kind="date"),
            Filter(key="status", label="الحالة", kind="choice", source="transaction_statuses"),
            Filter(key="provider", label="البوابة", kind="choice", source="providers"),
        ],
        columns=lambda contact: [
            Column("المرجع", width=22),
            Column("الوقت", Kind.DATETIME),
            Column("البوابة", width=16),
            Column("الوسيلة", width=16),
            Column("المبلغ", Kind.MONEY),
            Column("العملة", width=10),
            Column("الحالة", width=16),
            Column("نوع المرجع", width=16),
            Column("رقم العميل", width=18),
            Column("كود الفشل", width=18),
            Column("وقت التفويض", Kind.DATETIME),
            Column("وقت التحصيل", Kind.DATETIME),
        ],
        rows=_payment_rows,
        count=lambda filters: _payment_qs(filters).count(),
    )
)
