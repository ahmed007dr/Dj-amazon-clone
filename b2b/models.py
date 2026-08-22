"""
B2B — pharmacies and wholesalers.

⚠️  **Credit terms are the whole difference between B2C and B2B.**

    A retail customer pays and then receives. A pharmacy receives and then pays
    thirty days later — and that inverts the risk: the goods leave and the money
    has not arrived. Everything in this file serves one question: **how much
    does this customer owe us, and are they allowed more?**

⚠️  And the balance is **derived from the ledger, never stored as a field**.

    A `balance` field updated by addition and subtraction drifts from the ledger
    at the first exception mid-transaction, or the first manual correction in the
    database. And drift in a credit balance means either blocking a customer in
    good standing or extending credit to a defaulter — with nobody knowing which happened.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.identifiers import business_number
from core.models.base import BaseModel
from core.money import ZERO, MoneyField


def invoice_number() -> str:
    return business_number("INV", random_length=6)


class BusinessKind(models.TextChoices):
    PHARMACY = "PHARMACY", _("صيدلية")
    WAREHOUSE = "WAREHOUSE", _("مخزن أدوية")
    CLINIC = "CLINIC", _("عيادة")
    HOSPITAL = "HOSPITAL", _("مستشفى")
    TRADER = "TRADER", _("تاجر")


class CreditStatus(models.TextChoices):
    """
    ⚠️  An account starts with **no credit**, not with a default limit.

        An automatic credit limit means goods leaving for a customer nobody
        reviewed. Granting is an explicit decision, for a specific amount, by a
        known person.
    """

    NONE = "NONE", _("بلا ائتمان — دفع مقدَّم")
    ACTIVE = "ACTIVE", _("ائتمان نشط")
    SUSPENDED = "SUSPENDED", _("موقوف")


class BusinessProfile(BaseModel):
    """
    The business profile — on top of `CustomerProfile`, not a replacement for it.

    ⚠️  **No duplication of customer data.**

        Name, phone, addresses and tax number all live in `CustomerProfile`
        already. Copying them here creates two sources of truth that diverge at
        the first edit — and the invoice gets printed from whichever came to
        hand. This file carries **only what belongs to credit terms**.
    """

    customer = models.OneToOneField(
        "customers.CustomerProfile",
        on_delete=models.CASCADE,
        related_name="business_profile",
        verbose_name=_("العميل"),
    )

    kind = models.CharField(
        _("نوع المنشأة"), max_length=16, choices=BusinessKind.choices, db_index=True
    )
    legal_name = models.CharField(_("الاسم القانوني"), max_length=250)

    #: Professional practice licence number — reviewed by hand along with the documents
    license_number = models.CharField(_("رقم الترخيص"), max_length=64, blank=True)
    license_expires_on = models.DateField(_("انتهاء الترخيص"), null=True, blank=True)

    # ── Credit ─────────────────────────────────────────────
    credit_status = models.CharField(
        _("حالة الائتمان"),
        max_length=16,
        choices=CreditStatus.choices,
        default=CreditStatus.NONE,
        db_index=True,
    )
    credit_limit = MoneyField(
        _("الحد الائتماني"), default=ZERO, validators=[MinValueValidator(ZERO)]
    )
    #: ⚠️  Zero = payment in advance. There is no "reasonable" default here:
    #:     thirty days is granted by decision, never inherited from a setting.
    payment_terms_days = models.PositiveSmallIntegerField(_("مهلة السداد (يوم)"), default=0)

    credit_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_credit_accounts",
        verbose_name=_("مانح الائتمان"),
    )
    credit_approved_at = models.DateTimeField(_("وقت المنح"), null=True, blank=True)
    credit_note = models.TextField(_("ملاحظة الائتمان"), blank=True)

    class Meta:
        verbose_name = _("ملف تجاري")
        verbose_name_plural = _("الملفات التجارية")
        ordering = ["-created_at"]

    def __str__(self):
        return self.legal_name

    @property
    def license_is_valid(self) -> bool:
        """
        ⚠️  A licence with no expiry date is treated as **valid**.

            Treating absence as expiry blocked every long-standing customer
            whose licence date was never recorded — which is missing data, not
            a violation.

        ⚠️  And `localdate()`, not `now().date()`.

            The latter returns the **UTC** date, which is a day behind Cairo
            between midnight and 3am. So a licence that expired yesterday reads
            as valid during those hours — and credit is granted on that basis.
        """
        if self.license_expires_on is None:
            return True
        return self.license_expires_on >= timezone.localdate()

    @property
    def allows_credit(self) -> bool:
        return self.credit_status == CreditStatus.ACTIVE and self.credit_limit > ZERO


# ═══════════════════════════════════════════════════════════
#  The account ledger
# ═══════════════════════════════════════════════════════════


class LedgerKind(models.TextChoices):
    """
    ⚠️  The sign is part of the meaning, not of the field.

        `CHARGE` increases the debt and `PAYMENT` reduces it. Storing a negative
        amount for a payment would have made every query need to know the
        convention, and the first person to forget it inverts the statement.
    """

    CHARGE = "CHARGE", _("مديونية — طلب آجل")
    PAYMENT = "PAYMENT", _("سداد")
    CREDIT_NOTE = "CREDIT_NOTE", _("إشعار دائن — مرتجع")
    ADJUSTMENT = "ADJUSTMENT", _("تسوية يدوية")


#: The movements that **increase** what the customer owes
DEBIT_KINDS = {LedgerKind.CHARGE, LedgerKind.ADJUSTMENT}


class LedgerEntry(BaseModel):
    """
    A movement on the customer's account — **append-only**.

    ⚠️  No editing and no deleting: the statement is a document sent to the
        customer and disputes are built on it. Corrections are made with an
        opposing `ADJUSTMENT` movement carrying its reason.
    """

    business = models.ForeignKey(
        BusinessProfile,
        on_delete=models.PROTECT,
        related_name="ledger",
        verbose_name=_("العميل"),
    )

    kind = models.CharField(_("النوع"), max_length=16, choices=LedgerKind.choices, db_index=True)
    amount = MoneyField(_("المبلغ"), validators=[MinValueValidator(ZERO)])

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ledger_entries",
        verbose_name=_("الطلب"),
    )

    occurred_on = models.DateField(_("التاريخ"), default=timezone.localdate, db_index=True)
    #: ⚠️  The due date applies to debt alone — it is the basis of the ageing report
    due_on = models.DateField(_("تاريخ الاستحقاق"), null=True, blank=True, db_index=True)

    reference = models.CharField(_("المرجع"), max_length=64, blank=True)
    note = models.TextField(_("ملاحظة"), blank=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_ledger_entries",
        verbose_name=_("سجّلها"),
    )

    class Meta:
        verbose_name = _("حركة حساب")
        verbose_name_plural = _("حركات الحساب")
        ordering = ["-occurred_on", "-created_at"]
        indexes = [
            models.Index(fields=["business", "-occurred_on"]),
        ]
        constraints = [
            # ⚠️  One order is never charged as debt twice.
            #
            #     A retried checkout or a duplicated event would have doubled what
            #     the customer owes — blocking them from buying against a limit
            #     they consumed only once.
            models.UniqueConstraint(
                fields=["order", "kind"],
                condition=models.Q(deleted_at__isnull=True, order__isnull=False),
                name="unique_ledger_entry_per_order_kind",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.amount}"

    @property
    def is_debit(self) -> bool:
        return self.kind in DEBIT_KINDS

    @property
    def signed_amount(self):
        """The amount with its sign in the balance — positive against the customer, negative for
        them."""
        return self.amount if self.is_debit else -self.amount

    def save(self, *args, **kwargs):
        """
        ⚠️  **Append-only.**

            Editing a movement changes a statement already sent to the customer
            retroactively, leaving the dispute with no reference to settle it.
        """
        # ⚠️  `_state.adding`, not `self.pk`.
        #
        #     The UUID key is generated in Python **before** the insert, so `pk`
        #     exists on a row that has not been written yet. Checking against it
        #     rejected every creation — the guard blocking the very thing it came to guard.
        if not self._state.adding:
            raise ValueError("حركات الحساب لا تُعدَّل — سجّل تسوية معاكسة")
        super().save(*args, **kwargs)


# ═══════════════════════════════════════════════════════════
#  Invoices
# ═══════════════════════════════════════════════════════════


class InvoiceStatus(models.TextChoices):
    ISSUED = "ISSUED", _("صادرة")
    PAID = "PAID", _("مسدَّدة")
    OVERDUE = "OVERDUE", _("متأخرة")
    CANCELLED = "CANCELLED", _("ملغاة")


#: **Outstanding** invoices — the customer still has to pay them.
#
# ⚠️  `OVERDUE` is an incidental state, not a destination.
#
#     An overdue invoice is still due; excluding it from "open" queries makes
#     marking it overdue **hide** it from the credit gate, from the ageing
#     report and from payment settlement — meaning the oldest debts drop out of
#     the account the moment they become the oldest. A complete inversion of meaning.
OPEN_INVOICE_STATUSES = [InvoiceStatus.ISSUED, InvoiceStatus.OVERDUE]


class Invoice(BaseModel):
    """
    A credit invoice.

    ⚠️  **Every amount on it is a snapshot** — copied from the order at issue time.

        Reading them from the order at display time makes a printed invoice
        disagree with its on-screen copy after any correction. And an invoice is
        a document handed to an accountant.
    """

    number = models.CharField(
        _("رقم الفاتورة"), max_length=24, unique=True, default=invoice_number, editable=False
    )

    business = models.ForeignKey(
        BusinessProfile,
        on_delete=models.PROTECT,
        related_name="invoices",
        verbose_name=_("العميل"),
    )
    order = models.OneToOneField(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="invoice",
        verbose_name=_("الطلب"),
    )

    issued_on = models.DateField(_("تاريخ الإصدار"), default=timezone.localdate)
    due_on = models.DateField(_("تاريخ الاستحقاق"), db_index=True)

    subtotal = MoneyField(_("الإجمالي قبل الخصم"))
    discount_total = MoneyField(_("الخصم"), default=ZERO)
    tax_total = MoneyField(_("الضريبة"), default=ZERO)
    total = MoneyField(_("الإجمالي"))

    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.ISSUED,
        db_index=True,
    )

    class Meta:
        verbose_name = _("فاتورة")
        verbose_name_plural = _("الفواتير")
        ordering = ["-issued_on", "-created_at"]
        indexes = [
            models.Index(fields=["business", "status"]),
        ]

    def __str__(self):
        return self.number

    @property
    def is_overdue(self) -> bool:
        """
        ⚠️  Lateness is computed on the fly, never stored.

            A stored `is_overdue` field needs a periodic task to update it, and
            any failure there makes an overdue invoice look healthy — and it is
            the field on which blocking decisions are built.
        """
        return self.status in OPEN_INVOICE_STATUSES and self.due_on < timezone.localdate()

    @property
    def days_overdue(self) -> int:
        if not self.is_overdue:
            return 0
        return (timezone.localdate() - self.due_on).days
