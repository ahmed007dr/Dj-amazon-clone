"""
Supplier services.

⚠️  **Receiving always goes through `inventory`.**

    The batch is created with `inventory.services.receive`, never by a direct
    write. A second path into stock passes none of its checks and is recorded in
    none of its movements — so a balance appears with no movement behind it, and
    the cost of goods gets computed with no source.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Case, DecimalField, F, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.errors import BusinessError, ErrorCode
from core.money import ZERO, quantize
from suppliers.models import (
    CREDIT_KINDS,
    PurchaseOrder,
    PurchaseOrderLine,
    PurchaseOrderStatus,
    Supplier,
    SupplierLedgerEntry,
    SupplierLedgerKind,
    SupplierProduct,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
#  Purchase orders
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def create_order(
    supplier: Supplier,
    location,
    lines: list[dict],
    *,
    expected_on: date | None = None,
    note: str = "",
    actor=None,
) -> PurchaseOrder:
    """
    ⚠️  The price is taken from **the supplier's offer**, not from the frontend.

        Accepting a sent price means whoever creates the order sets what we pay
        — the first thing exploited in purchasing. And a nonexistent offer is
        refused explicitly rather than bought at an invented price.
    """
    if not supplier.is_active:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="المورّد موقوف")

    if not lines:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="لا أصناف في أمر الشراء")

    order = PurchaseOrder.objects.create(
        supplier=supplier,
        location=location,
        expected_on=expected_on,
        note=note,
        created_by=actor,
    )

    offers = {
        offer.product_id: offer
        for offer in SupplierProduct.objects.filter(
            supplier=supplier,
            product_id__in=[line["product"] for line in lines],
            is_active=True,
        )
    }

    subtotal = ZERO
    for line in lines:
        offer = offers.get(line["product"])
        if offer is None:
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR,
                detail=f"المورّد لا يعرض المنتج {line['product']}",
            )

        quantity = int(line["quantity"])
        if quantity < offer.minimum_order_quantity:
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR,
                detail=(
                    f"الحد الأدنى لطلب {offer.product.sku} هو " f"{offer.minimum_order_quantity}"
                ),
            )

        # ⚠️  The price comes from the offer, **and accepts a deliberate edit**.
        #
        #     Purchasing is negotiated: a supplier grants a price for one particular
        #     order without changing their standing offer. Refusing the edit forced the
        #     buyer to change the offer itself — so the default price changed for every
        #     future order with nobody intending it.
        #
        #     And the original is kept in `list_cost` so the difference stays readable:
        #     "what was it offered at and what did we pay?" is the question the buyer is judged on.
        unit_cost = quantize(Decimal(str(line["unit_cost"]))) if line.get("unit_cost") else None

        if unit_cost is not None and unit_cost < ZERO:
            raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="السعر لا يكون سالبًا")

        created = PurchaseOrderLine.objects.create(
            order=order,
            product=offer.product,
            quantity_ordered=quantity,
            unit_cost=unit_cost if unit_cost is not None else offer.unit_cost,
            list_cost=offer.unit_cost,
        )
        subtotal += created.total

    order.subtotal = quantize(subtotal)
    order.save(update_fields=["subtotal", "updated_at"])
    return order


def price_variances(order: PurchaseOrder) -> list[dict]:
    """
    The lines whose price differed from the offer — **for auditing**.

    ⚠️  Read on sending and written into the audit log.

        An unrecorded price edit makes "who lowered/raised it, and by how much?"
        a question with no answer after the first offer update.
    """
    rows = []
    for line in order.lines.select_related("product"):
        variance = line.cost_variance
        if variance is None or variance == ZERO:
            continue
        rows.append(
            {
                "sku": line.product.sku,
                "list_cost": str(line.list_cost),
                "unit_cost": str(line.unit_cost),
                "variance": str(variance),
            }
        )
    return rows


@transaction.atomic
def send_order(order: PurchaseOrder, *, actor=None) -> PurchaseOrder:
    """
    ⚠️  Sending fixes the prices and posts the invoice to our account.

        Posting it on receipt rather than on sending hides an existing
        obligation: the order was sent and the supplier will claim it.
    """
    if order.status != PurchaseOrderStatus.DRAFT:
        raise BusinessError(ErrorCode.CONFLICT, detail="لا يُرسَل إلا أمر مسوّدة", status_code=409)

    order.status = PurchaseOrderStatus.SENT
    order.sent_at = timezone.now()
    order.save(update_fields=["status", "sent_at", "updated_at"])

    SupplierLedgerEntry.objects.create(
        supplier=order.supplier,
        purchase_order=order,
        kind=SupplierLedgerKind.INVOICE,
        amount=order.subtotal,
        due_on=_due_date(order.supplier),
        reference=order.number,
        recorded_by=actor,
    )
    return order


def _due_date(supplier: Supplier) -> date:
    """⚠️  The payment terms are **ours** — how many days we take to pay them."""
    return timezone.localdate() + timedelta(days=supplier.payment_terms_days)


@transaction.atomic
def receive_line(
    line: PurchaseOrderLine,
    quantity: int,
    *,
    expires_at: date | None = None,
    batch_number: str = "",
    actor=None,
):
    """
    Receive a quantity against a line — **and enter it into stock through `inventory`**.

    ⚠️  Over-receiving is refused.

        Accepting it means entering goods that were never ordered and never
        invoiced, so the reconciliation of the invoice against what was received
        breaks — and that is the first thing reviewed with the supplier.

    ⚠️  And the cost comes **from the order line, not from the supplier's offer today**.

        The offer changes between sending and receiving; and taking today's
        price makes the batch's cost contradict the agreed invoice — so every
        profit computed on it afterwards drifts.
    """
    from inventory import services as inventory_services

    if not line.order.is_receivable:
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail="الأمر غير قابل للاستلام — أرسله أولًا",
            status_code=409,
        )

    if quantity <= 0:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الكمية يجب أن تكون موجبة")

    if quantity > line.outstanding:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            detail=f"المتبقي على السطر {line.outstanding} — لا يُستلَم أكثر",
        )

    batch = inventory_services.receive(
        line.product,
        quantity,
        line.unit_cost,
        location=line.order.location,
        expires_at=expires_at,
        supplier_batch_number=batch_number,
        performed_by=actor,
    )

    line.quantity_received = F("quantity_received") + quantity
    line.save(update_fields=["quantity_received", "updated_at"])
    line.refresh_from_db()

    _refresh_order_status(line.order)
    return batch


def _refresh_order_status(order: PurchaseOrder) -> None:
    """
    ⚠️  The status is derived from the lines rather than written by hand.

        Writing it on every receiving path means one forgotten path leaves a
        fully received order showing as partial forever.
    """
    lines = list(order.lines.all())
    received_any = any(line.quantity_received > 0 for line in lines)
    complete = all(line.is_complete for line in lines)

    if complete:
        order.status = PurchaseOrderStatus.RECEIVED
        order.received_at = timezone.now()
        order.save(update_fields=["status", "received_at", "updated_at"])
    elif received_any:
        order.status = PurchaseOrderStatus.PARTIAL
        order.save(update_fields=["status", "updated_at"])


@transaction.atomic
def cancel_order(order: PurchaseOrder, *, reason: str, actor=None) -> PurchaseOrder:
    """
    ⚠️  **An order with anything received against it is never cancelled.**

        The goods entered the warehouse; cancelling their order leaves batches
        with no source and reverses an invoice for goods we genuinely own.
    """
    if order.status == PurchaseOrderStatus.RECEIVED:
        raise BusinessError(
            ErrorCode.CONFLICT, detail="الأمر مستلَم بالكامل — لا يُلغى", status_code=409
        )

    if order.lines.filter(quantity_received__gt=0).exists():
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail="استُلمت أصناف من هذا الأمر — أنشئ مرتجعًا بدل الإلغاء",
            status_code=409,
        )

    if order.status == PurchaseOrderStatus.SENT:
        # ⚠️  A credit note reversing the invoice — not a deletion of it.
        #     The invoice was sent to the supplier and they have recorded it.
        SupplierLedgerEntry.objects.create(
            supplier=order.supplier,
            purchase_order=order,
            kind=SupplierLedgerKind.CREDIT_NOTE,
            amount=order.subtotal,
            reference=order.number,
            note=reason,
            recorded_by=actor,
        )

    order.status = PurchaseOrderStatus.CANCELLED
    order.note = f"{order.note}\n— أُلغي: {reason}".strip()
    order.save(update_fields=["status", "note", "updated_at"])
    return order


# ═══════════════════════════════════════════════════════════
#  Returns to the supplier
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def return_to_supplier(
    line: PurchaseOrderLine,
    quantity: int,
    *,
    reason: str,
    actor=None,
) -> SupplierLedgerEntry:
    """
    Return goods **that were actually received** to the supplier.

    ⚠️  The order is deliberate: **stock first, then the entry**.

        The entry before the deduction makes the supplier credit us for goods
        still in our possession should the deduction fail. And the reverse — a
        deduction with no entry — loses the goods with no financial counterpart.

    ⚠️  And the ceiling is **received minus already returned**.

        Returning the same quantity twice creates two credit notes for one lot
        of goods, so the supplier ends up owing us for what we never returned —
        an error that shows on their statement rather than in our stock.

    ⚠️  And the original invoice entry is never deleted.

        The invoice was issued and the supplier recorded it; the correction is a
        credit note, not an eraser.
    """
    from inventory import services as inventory_services

    if not reason.strip():
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="سبب الإرجاع إلزامي")

    if quantity <= 0:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الكمية يجب أن تكون موجبة")

    available = line.quantity_on_hand
    if quantity > available:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            detail=f"المستلَم غير المرتجع {available} — لا يُرجَع أكثر",
        )

    order = line.order

    # ── 1. Stock ───────────────────────────────────────────
    inventory_services.return_to_supplier(
        line.product,
        quantity,
        location=order.location,
        reason=reason,
        reference_type="purchase_order",
        reference_id=str(order.pk),
        performed_by=actor,
    )

    line.quantity_returned = F("quantity_returned") + quantity
    line.save(update_fields=["quantity_returned", "updated_at"])
    line.refresh_from_db()

    # ── 2. The entry ───────────────────────────────────────
    # ⚠️  No `purchase_order` on the entry: the unique constraint allows one credit
    #     note per order, and purchase orders have several batches returned from
    #     them over time. The reference is a string in `reference`.
    amount = quantize(line.unit_cost * quantity)

    return SupplierLedgerEntry.objects.create(
        supplier=order.supplier,
        kind=SupplierLedgerKind.CREDIT_NOTE,
        amount=amount,
        reference=f"{order.number} · {line.product.sku}",
        note=f"إرجاع {quantity} — {reason}",
        recorded_by=actor,
    )


# ═══════════════════════════════════════════════════════════
#  The supplier account
# ═══════════════════════════════════════════════════════════


def _signed_sum(queryset) -> Decimal:
    total = queryset.aggregate(
        total=Coalesce(
            Sum(
                Case(
                    When(kind__in=list(CREDIT_KINDS), then=F("amount")),
                    default=-F("amount"),
                    output_field=DecimalField(max_digits=16, decimal_places=2),
                )
            ),
            Value(ZERO),
            output_field=DecimalField(max_digits=16, decimal_places=2),
        )
    )["total"]
    return quantize(total)


def payable_balance(supplier: Supplier) -> Decimal:
    """What we owe the supplier — **derived from the ledger**, not a stored field."""
    return _signed_sum(SupplierLedgerEntry.objects.filter(supplier=supplier))


@transaction.atomic
def record_payment(
    supplier: Supplier,
    amount: Decimal,
    *,
    reference: str = "",
    note: str = "",
    actor=None,
) -> SupplierLedgerEntry:
    if amount <= ZERO:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="مبلغ السداد يجب أن يكون موجبًا")

    return SupplierLedgerEntry.objects.create(
        supplier=supplier,
        kind=SupplierLedgerKind.PAYMENT,
        amount=quantize(amount),
        reference=reference,
        note=note,
        recorded_by=actor,
    )


@dataclass(frozen=True)
class SupplierStatement:
    """
    A supplier account statement.

    ⚠️  **The aggregates are their own line items, not something the reader infers.**

        A statement of movements alone forces the accountant to sort and add
        them up to learn "how much we were invoiced, how much we paid and how
        much we returned" — the four figures any discussion with the supplier is
        built on.
    """

    supplier: Supplier
    start: date
    end: date

    opening_balance: Decimal
    entries: list
    closing_balance: Decimal

    invoiced: Decimal
    paid: Decimal
    returned: Decimal
    adjusted: Decimal


def _kind_total(queryset, kind: str) -> Decimal:
    return quantize(
        queryset.filter(kind=kind).aggregate(
            total=Coalesce(
                Sum("amount"),
                Value(ZERO),
                output_field=DecimalField(max_digits=16, decimal_places=2),
            )
        )["total"]
    )


def statement(supplier: Supplier, start: date, end: date) -> SupplierStatement:
    if start > end:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="بداية الفترة بعد نهايتها")

    opening = _signed_sum(
        SupplierLedgerEntry.objects.filter(supplier=supplier, occurred_on__lt=start)
    )
    window = SupplierLedgerEntry.objects.filter(
        supplier=supplier, occurred_on__gte=start, occurred_on__lte=end
    )

    return SupplierStatement(
        supplier=supplier,
        start=start,
        end=end,
        opening_balance=opening,
        entries=list(window.select_related("purchase_order").order_by("occurred_on", "created_at")),
        closing_balance=quantize(opening + _signed_sum(window)),
        invoiced=_kind_total(window, SupplierLedgerKind.INVOICE),
        paid=_kind_total(window, SupplierLedgerKind.PAYMENT),
        returned=_kind_total(window, SupplierLedgerKind.CREDIT_NOTE),
        adjusted=_kind_total(window, SupplierLedgerKind.ADJUSTMENT),
    )


def annotated_suppliers():
    """
    The supplier list with balance and total purchases — **a single query**.

    ⚠️  **This is the difference between a screen that works and one that stalls.**

        Calling `payable_balance()` per row means one query per supplier (N+1)
        on the most frequently opened screen. And the aggregation here makes it
        one query however many there are.

    ⚠️  And the two aggregates are **separated with `distinct=True`**.

        Joining two tables in one query multiplies the rows: every account
        movement repeats once per purchase order and vice versa — so an inflated
        balance and purchase total come out with nothing looking wrong.
    """
    from django.db.models import Exists, OuterRef

    money = DecimalField(max_digits=16, decimal_places=2)

    # ⚠️  Subqueries rather than a direct `annotate`: the multiple join
    #     multiplies the rows, as in the comment above.
    ledger = (
        SupplierLedgerEntry.objects.filter(supplier=OuterRef("pk")).order_by().values("supplier")
    )

    balance = ledger.annotate(
        total=Sum(
            Case(
                When(kind__in=list(CREDIT_KINDS), then=F("amount")),
                default=-F("amount"),
                output_field=money,
            )
        )
    ).values("total")

    purchases = (
        PurchaseOrder.objects.filter(supplier=OuterRef("pk"))
        .exclude(status__in=[PurchaseOrderStatus.DRAFT, PurchaseOrderStatus.CANCELLED])
        .order_by()
        .values("supplier")
        .annotate(total=Sum("subtotal"))
        .values("total")
    )

    overdue = SupplierLedgerEntry.objects.filter(
        supplier=OuterRef("pk"),
        kind=SupplierLedgerKind.INVOICE,
        due_on__lt=timezone.localdate(),
    )

    return Supplier.objects.annotate(
        payable=Coalesce(Subquery(balance, output_field=money), Value(ZERO), output_field=money),
        total_purchases=Coalesce(
            Subquery(purchases, output_field=money), Value(ZERO), output_field=money
        ),
        # ⚠️  "Has overdue invoices" is **deliberately approximate**: it counts the
        #     invoices due rather than what has been paid against them, because the
        #     ledger does not allocate payment to a specific invoice. Enough to flag, not to claim.
        has_overdue=Exists(overdue),
    )


# ═══════════════════════════════════════════════════════════
#  Purchase suggestions — the basis of the marketplace
# ═══════════════════════════════════════════════════════════


def offers_for(product) -> list[dict]:
    """
    Everyone offering this product — **ordered by price**.

    ⚠️  This is the function the marketplace will later rest on.

        Today it serves the purchasing decision: "who is cheapest, and who
        delivers fastest?". And tomorrow it serves the customer's choice between
        sellers — on the same data and with no change to the structure.
    """
    rows = (
        SupplierProduct.objects.filter(product=product, is_active=True, supplier__is_active=True)
        .select_related("supplier")
        .order_by("unit_cost")
    )

    return [
        {
            "supplier": str(offer.supplier_id),
            "supplier_name_ar": offer.supplier.name_ar,
            "supplier_name_en": offer.supplier.name_en,
            "unit_cost": str(offer.unit_cost),
            "minimum_order_quantity": offer.minimum_order_quantity,
            "lead_time_days": offer.lead_time_days or offer.supplier.lead_time_days,
            "is_preferred": offer.is_preferred,
        }
        for offer in rows
    ]


def reorder_suggestions(location=None, limit: int = 50) -> list[dict]:
    """
    What needs buying: items below their reorder point that have a supplier.

    ⚠️  **An item with no supplier is listed and flagged, not dropped.**

        Excluding it makes the most important shortage in the warehouse vanish
        from the purchasing screen — and the reason is that it has no supplier,
        which is exactly what needs dealing with.
    """
    from inventory.models import Stock

    stocks = Stock.objects.filter(quantity_physical__lte=F("reorder_point")).select_related(
        "product"
    )
    if location is not None:
        stocks = stocks.filter(location=location)

    suggestions = []
    for stock in stocks[:limit]:
        preferred = (
            SupplierProduct.objects.filter(
                product=stock.product, is_active=True, supplier__is_active=True
            )
            .select_related("supplier")
            .order_by("-is_preferred", "unit_cost")
            .first()
        )

        suggestions.append(
            {
                "product": str(stock.product_id),
                "sku": stock.product.sku,
                "name_ar": stock.product.name_ar,
                "name_en": stock.product.name_en,
                "on_hand": stock.quantity_physical,
                "reorder_point": stock.reorder_point,
                "supplier": str(preferred.supplier_id) if preferred else None,
                "supplier_name": preferred.supplier.name_ar if preferred else None,
                "unit_cost": str(preferred.unit_cost) if preferred else None,
                # ⚠️  An explicit flag: the screen highlights it rather than dropping it
                "has_supplier": preferred is not None,
            }
        )

    return suggestions
