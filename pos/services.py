"""
Point-of-sale services.

⚠️  **The governing principle: POS is a sales channel, not a parallel system.**

        pos.services.checkout()
                ↓
        orders.services.create_pos_order(channel=POS, location=…)
                ↓
            an ordinary Order

    One sales report · one stock · one set of finances.

⚠️  And no rule is bypassed: access policies, pricing and stock apply exactly as
    they are. "The cashier is in front of the customer and in a hurry" is not a
    reason to sell a forbidden or unavailable item — and it is exactly what
    makes the stock count fail to balance.
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

#: The setting keys configurable from the panel
VARIANCE_THRESHOLD = "pos.cash_variance_threshold"
MAX_DISCOUNT_PERCENT = "pos.max_discount_percent"


def variance_threshold() -> Decimal:
    """
    The threshold above which explaining the discrepancy becomes mandatory.

    ⚠️  Business rule 12 is not yet settled — the default value is a
        recommendation written in `docs/shared/04-DECISIONS.md`, and it is
        configurable from the panel with no deployment.
    """
    return Decimal(str(SystemSetting.get(VARIANCE_THRESHOLD, default="20.00")))


def max_discount_percent() -> Decimal:
    """
    The cap on a cashier's manual discount.

    ⚠️  Business rule 11 is not settled — the default is **zero**: no discount
        without approval. A permissive default opens a door that is hard to
        close once the cashier has grown used to it.
    """
    return Decimal(str(SystemSetting.get(MAX_DISCOUNT_PERCENT, default="0")))


# ═══════════════════════════════════════════════════════════
#  The shift
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def open_session(register: Register, cashier, *, opening_float: Decimal = ZERO) -> POSSession:
    """
    Open a shift.

    ⚠️  A disabled register does not open a shift, and an open shift is not
        opened again — the database constraint is the final guard, and this
        check gives a comprehensible message instead of an integrity error.
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
    The cash expected in the drawer.

    ⚠️  Computed from **the drawer movements**, not from the shift's sales.

        A card sale puts no cash in the drawer; counting it in the expected
        figure produces a phantom shortfall the size of all card sales — and the
        cashier is accused of something they did not do.
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
    Close a shift with a cash reconciliation.

    ⚠️  **A discrepancy above the threshold requires an explanation.**

        Business rule 12. A discrepancy with no explanation accumulates for
        months and is then discovered as a shortfall nobody can trace — and
        closing time is the only moment the cashier still remembers what happened.

    ⚠️  And a closed shift is not closed again: a repeated close would have
        rewritten `expected_cash` with a fresh snapshot, changing an approved
        reconciliation retroactively.
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

    # ⚠️  The event after the save, not before: the listener (finance, later) reads
    #     a genuinely closed shift rather than one whose save may fail.
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
    Record a cash movement.

    ⚠️  A closed shift accepts no movements — or a settled expected figure changes.
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
#  Selling
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SaleLine:
    """A line in a sale — the product and the quantity only, and `pricing` computes the price."""

    product: object
    quantity: int
    variant: object | None = None


@dataclass(frozen=True)
class SplitPayment:
    """
    Part of a split payment.

    ⚠️  Split payment is a daily occurrence at the counter: half cash and half
        by card. Confining it to one method forces the cashier to record two
        sales for one operation — breaking the receipt and the return together.
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
    Price a sale before completing it.

    ⚠️  **The same calculation that will be charged — not a copy of it.**

        The cashier's screen shows a total, and the server charges a total.
        Computing them in two places means they diverge at the first change in
        pricing, so the terminal says one figure and the receipt prints another
        — and the customer is the one who discovers it.
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
    Prices the basket with no effect at all: no stock deducted and no order created.

    ⚠️  The discount cap is checked here too.

        Leaving it to checkout alone makes the cashier build a whole sale in
        front of the customer and then be refused on the last press — when the
        discount should be blocked the moment it is entered.
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
    ⚠️  The sum of the payments **equals** the total exactly.

        Less means an unsettled sale recorded as complete; more means a surplus
        the system does not know where to put. The customer's change is worked
        out by the cashier outside the system, as at every till.
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
    Complete a sale at the counter.

    ⚠️  The order is deliberate and not interchangeable:

          1. price from `pricing`      ← no price comes in from the frontend
          2. deduct stock immediately  ← no reservation, the sale is instantaneous
          3. create the order          ← `channel=POS`
          4. record the payments
          5. a drawer movement for the cash portion alone

        Stock is deducted **before** the order is created: if an item runs out
        the whole transaction is rolled back with no orphan order. The reverse
        leaves a recorded order for goods that were never handed over.
    """
    if not session.is_open:
        raise BusinessError(
            ErrorCode.CONFLICT, detail="الوردية مغلقة — افتح وردية أولًا", status_code=409
        )

    if not lines:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="لا أصناف في البيعة")

    location = session.register.location

    # ── 1. Pricing ─────────────────────────────────────────
    # ⚠️  **The same function that feeds the cashier's screen.**
    #
    #     Duplicating the calculation here would have meant two totals diverging at
    #     the first change in pricing — one on the screen and the other on the receipt.
    priced = quote(session, lines, customer=customer, discount_percent=discount_percent)
    priced_lines = priced.lines
    subtotal = priced.subtotal
    tax_total = priced.tax_total
    total = priced.total

    _assert_payments_cover(total, payments)

    # ── 2. Deduct stock immediately ────────────────────────
    #
    # ⚠️  The reference here is **the shift**, because the order does not exist yet.
    #
    #     The order is deliberate: if an item runs out the transaction is rolled back with no orphan
    #     order.
    #     But it leaves the movements tied to the shift rather than to the sale — and they are
    #     redirected to the order immediately after it is created (step 3b).
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

    # ── 3. The order ───────────────────────────────────────
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

    # ── 3b. Redirecting the stock movements to the order ───
    #
    # ⚠️  **Without it, the cost of every counter sale is absent from the profit statement.**
    #
    #     Finance computes the cost of goods sold from the stock movements
    #     linked to the order (`reference_type="order"`). Point-of-sale movements
    #     were tied to the shift, so branch sales were posted as
    #     revenue **at zero cost** — that is, at a profit equal to the full selling price.
    #     An error in the worst direction: it makes the report look excellent.
    #
    # ⚠️  And the shift is preserved in `note` rather than lost.
    #
    #     There is no foreign key from `Order` to `POSSession`: `orders` sits
    #     **below** `pos` in the layer order, and the key would have inverted
    #     the direction and broken the contract. The text suffices for manual
    #     tracing, and the analytical link runs through `CashMovement`, which carries the order id.
    if movements:
        touched = StockMovement.objects.filter(pk__in=[m.pk for m in movements])
        touched.update(reference_type="order", reference_id=str(order.pk))

        # ⚠️  Only an empty note is written over.
        #
        #     A movement with no batch carries "no linked batch" — the trace of
        #     goods of unknown cost. Overwriting it erases the only explanation
        #     for a line that will appear in the report with a missing cost.
        touched.filter(note="").update(note=f"وردية {session.number}")

    # ── 4. The payments ────────────────────────────────────
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
                # ⚠️  A unique key per part: a double-click on "charge"
                #     would have produced two payments for the same sale.
                idempotency_key=f"pos-{order.pk}-{entry.method}-{entry.amount}",
            )
        )

    # ── 5. The cash in the drawer ──────────────────────────
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
#  Returns
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
    A return inside the point of sale.

    ⚠️  A return produces **a reversing stock movement**, not a deletion of the order.

        Deleting the order erases a sale that actually happened, breaking the
        day's report and losing the tax collected on it. The order remains and
        is marked `REFUNDED`.

    ⚠️  And the cash returned leaves the drawer as a recorded movement — or the
        discrepancy looks like a shortfall at closing.
    """
    if not session.is_open:
        raise BusinessError(ErrorCode.CONFLICT, detail="لا مرتجع على وردية مغلقة", status_code=409)

    from orders import services as order_services

    order = order_services.refund_pos_order(order, reason=reason, actor=performed_by)

    # Returning the items to the location's stock
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
