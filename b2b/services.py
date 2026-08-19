"""
B2B services.

⚠️  **The credit check is the critical function in this file.**

    Everything else is display and reporting. This check decides whether goods
    leave against a promise to pay — and being wrong in one direction means a
    direct cash loss.
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

#: Ageing buckets in days — matching what an accountant reads on any statement
AGING_BUCKETS = [(0, 30), (31, 60), (61, 90)]


def _signed_sum(queryset) -> Decimal:
    """
    The sum of the movements with their signs.

    ⚠️  The sign is computed in the database, not in Python.

        Dragging every movement of a customer with a thousand orders into memory
        to add them up makes opening the statement slower the more loyal they become.
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
    What the customer owes right now — **derived from the ledger**.

    ⚠️  There is no stored `balance` field.

        A field updated by addition and subtraction drifts at the first
        exception mid-transaction or the first manual correction. And drift in
        the credit balance means blocking a customer in good standing or
        extending credit to a defaulter — with nobody knowing which happened.
    """
    return _signed_sum(LedgerEntry.objects.filter(business=business))


def available_credit(business: BusinessProfile) -> Decimal:
    """
    ⚠️  Never less than zero.

        A customer who paid more than they owe would have a negative balance,
        making their credit limit look larger than what was granted. A credit
        balance is a benefit to the customer, not an extension of their ceiling.
    """
    remaining = business.credit_limit - outstanding_balance(business)

    # ⚠️  Clamped between zero and the granted limit — **at both ends**.
    #
    #     The floor prevents a negative number being read as available credit. The
    #     ceiling prevents something more dangerous: a customer who paid more than
    #     they owe has a negative balance, so the subtraction lifts their available
    #     credit above what was granted — and they buy against a limit nobody approved.
    return min(max(remaining, ZERO), business.credit_limit)


def overdue_invoices(business: BusinessProfile):
    """Invoices past their due date and unpaid."""
    return Invoice.objects.filter(
        business=business,
        # ⚠️  `OPEN_...`, not `ISSUED`: an invoice marked "overdue" is still
        #     due, and excluding it made marking it hide it from the credit
        #     gate — so the oldest debts dropped out of the account.
        status__in=OPEN_INVOICE_STATUSES,
        due_on__lt=timezone.localdate(),
    )


# ═══════════════════════════════════════════════════════════
#  The credit gate
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class CreditDecision:
    """
    ⚠️  The decision carries **its reason**, not just yes/no.

        A bare "refused" makes the sales rep call head office on every order.
        The reason is shown to the customer so they can act: pay, or renew their licence.
    """

    allowed: bool
    reason: str = ""
    available: Decimal = ZERO


def evaluate_credit(business: BusinessProfile, amount: Decimal) -> CreditDecision:
    """
    Is a credit order for this amount allowed?

    ⚠️  The order is deliberate: **structural reasons before arithmetic ones.**

        A customer whose licence has lapsed must read "your licence has expired",
        not "you have exceeded your limit" — the latter pushes them to pay for nothing.
    """
    if business.credit_status == CreditStatus.SUSPENDED:
        return CreditDecision(False, "الحساب الائتماني موقوف — راجع خدمة العملاء")

    if not business.allows_credit:
        return CreditDecision(False, "لا ائتمان على هذا الحساب — الدفع مقدَّم")

    # ⚠️  An expired licence blocks credit, not the sale.
    #
    #     A pharmacy with an expired licence is still trading and may well pay;
    #     but handing it goods on a promise while its legal standing is in
    #     suspense is a risk not measured in money alone.
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
    Charges an order to the account and issues its invoice.

    ⚠️  **`select_for_update` on the business profile — and it is not decoration.**

        Two concurrent orders each read a balance before the other writes, so
        both pass and their total exceeds the limit. The lock makes the second
        wait and read the first one's effect.

        And this scenario is **not rare** in B2B: a double-click on the checkout
        button is enough.
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
    A payment from the customer — settling the oldest invoices first.

    ⚠️  **Oldest first (FIFO), not newest.**

        Settling the newest leaves the old invoice open forever, so the customer
        shows as overdue while paying regularly — and is blocked from buying
        because of a debt they have actually paid.
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
    ⚠️  A partial payment **does not close an invoice**.

        Closing it for a smaller amount hides the remainder from the statement,
        so an outstanding debt disappears from every report — and the customer
        themselves does not know they owe it.
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
    A credit note — a return against a credit order.

    ⚠️  The original debt entry is not deleted: the invoice was issued and
        delivered, and cancelling it retroactively leaves the customer's
        accountant holding a document with no counterpart.
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
#  Statement and ageing
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class AgingBucket:
    label: str
    amount: Decimal


@dataclass(frozen=True)
class Statement:
    """
    An account statement — **a document sent to the customer**.

    ⚠️  Opening balance, movements and closing balance together.

        A statement of movements alone forces the customer to add them up to
        learn where they stand, and a statement of the balance alone cannot be
        reviewed. All three together are what makes a dispute settleable.
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
    Debt ageing — **from the open invoices**.

    ⚠️  Computed from the invoices, not from the ledger.

        The ledger carries payments with no link to a specific invoice, so
        computing ageing from it needs an allocation that reinvents what the
        invoices already do.
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

    # ⚠️  The last bucket is open-ended at the top: a debt a year old must
    #     show up, not drop off the statement for passing the last written boundary.
    oldest_edge = AGING_BUCKETS[-1][1]
    beyond = open_invoices.filter(due_on__lt=today - timedelta(days=oldest_edge)).aggregate(
        total=Coalesce(
            Sum("total"),
            Value(ZERO),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )["total"]
    buckets.append(AgingBucket(label=f"{oldest_edge}+", amount=quantize(beyond)))

    # ⚠️  Not-yet-due amounts are shown separately: mixing them with overdue ones
    #     makes a customer in good standing look like a defaulter over a sum that is not due yet.
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
#  Quick reordering
# ═══════════════════════════════════════════════════════════


def frequently_ordered(customer, limit: int = 20) -> list[dict]:
    """
    What this customer orders most.

    ⚠️  **Most frequent, not most recent.**

        A pharmacy reorders the same twenty items every fortnight. "Last order"
        gives a single order that may have been exceptional; frequency gives
        their genuinely habitual basket.
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
    ⚠️  Granting is **a documented act**, not a field edit.

        "Who raised this customer's limit to a hundred thousand, and when?" is
        asked after the first default — and it has to be answerable from the row itself.
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
    ⚠️  Suspension **does not touch the limit** — it only disables it.

        Zeroing the limit loses what was granted, so reactivation needs a fresh
        decision from scratch instead of simply lifting the suspension.
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
    Marks invoices overdue — **for display and reporting only**.

    ⚠️  Blocking decisions **do not depend on this field**.

        `evaluate_credit` queries `due_on` directly. Were it to rely on the
        stored state, a failure of the periodic task would become a silent hole:
        overdue invoices looking healthy, so credit keeps flowing.
    """
    updated = Invoice.objects.filter(
        status=InvoiceStatus.ISSUED, due_on__lt=timezone.localdate()
    ).update(status=InvoiceStatus.OVERDUE)

    if updated:
        logger.info("عُلّمت %s فاتورة كمتأخرة", updated)
    return updated
