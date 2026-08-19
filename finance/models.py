"""
Finance — revenue, expenses and the cost of goods sold.

⚠️  **Every number is traceable to its source. No black-box calculation.**

    The revenue entry carries a foreign key to the order, and the cost entry
    carries a reference to the batch the goods actually left from. The question
    "where did this number come from?" must be answered with a row, not a calculation.

⚠️  And `Decimal` exclusively — no `float` in any financial calculation.

    With returns, discounts and taxes, floating-point discrepancies accumulate
    until they break any accounting reconciliation.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.identifiers import random_filename
from core.models.base import BaseModel, TimeStampedModel
from core.money import ZERO, MoneyField


def expense_attachment_path(instance, filename):
    """
    ⚠️  A **private** path under a random name.

        A rent invoice carries the landlord's name and their amount. Leaving it
        under its original name on a public path makes it readable by anyone who
        knows the URL, and a sequential path is guessed with a loop.
    """
    return f"private/expense-attachments/{random_filename(filename)}"


# ═══════════════════════════════════════════════════════════
#  Expenses
# ═══════════════════════════════════════════════════════════


class ExpenseCategory(BaseModel):
    """
    An expense category — a tree.

    ⚠️  A tree because "utilities" splits into electricity, water and internet.

        A flat list forces the business owner to choose between one general
        category that helps no analysis and twenty categories where none is legible.
    """

    code = models.SlugField(_("الرمز"), max_length=64, unique=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
        verbose_name=_("البند الأب"),
    )

    name_ar = models.CharField(_("الاسم بالعربية"), max_length=120)
    name_en = models.CharField(_("الاسم بالإنجليزية"), max_length=120)

    is_active = models.BooleanField(_("مفعّل"), default=True)
    display_order = models.PositiveIntegerField(_("الترتيب"), default=0)

    class Meta:
        verbose_name = _("بند مصروف")
        verbose_name_plural = _("بنود المصروفات")
        ordering = ["display_order", "name_ar"]

    def __str__(self):
        return self.name_ar


class ExpenseStatus(models.TextChoices):
    """
    ⚠️  An expense starts as a **draft**, not approved.

        Automatic approval makes every entry error enter the profit statement
        immediately — and a wrong number in a financial report is worse than a
        missing one, because a decision gets taken on it.
    """

    DRAFT = "DRAFT", _("مسوّدة")
    APPROVED = "APPROVED", _("معتمد")
    REJECTED = "REJECTED", _("مرفوض")


class PaymentMean(models.TextChoices):
    """How the money went out — for the cash flow."""

    CASH = "CASH", _("نقدًا")
    BANK = "BANK", _("تحويل بنكي")
    CARD = "CARD", _("بطاقة")
    OTHER = "OTHER", _("أخرى")


class Expense(BaseModel):
    """
    An operating expense — **entered by hand**.

    ⚠️  `incurred_on` is the date it **was incurred, not the date it was entered**.

        March's rent is entered in April and must appear in March's profit.
        Conflating them moves the expense into the following month, showing one
        profitable month and one loss-making one for no real reason.
    """

    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        related_name="expenses",
        verbose_name=_("البند"),
    )

    amount = MoneyField(_("المبلغ"), validators=[MinValueValidator(ZERO)])
    incurred_on = models.DateField(_("تاريخ الاستحقاق"), db_index=True)

    vendor_name = models.CharField(_("المورّد/الجهة"), max_length=200, blank=True)
    reference = models.CharField(_("رقم الفاتورة"), max_length=64, blank=True)

    attachment = models.FileField(
        _("مرفق الفاتورة"),
        upload_to=expense_attachment_path,
        null=True,
        blank=True,
    )

    payment_mean = models.CharField(
        _("طريقة الدفع"),
        max_length=16,
        choices=PaymentMean.choices,
        default=PaymentMean.CASH,
    )

    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=ExpenseStatus.choices,
        default=ExpenseStatus.DRAFT,
        db_index=True,
    )

    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="entered_expenses",
        verbose_name=_("المُدخِل"),
    )
    # ⚠️  `SET_NULL`, not `PROTECT`: deleting an old approver's account must not
    #     protect an expense from deletion, nor fail with an obscure integrity error.
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_expenses",
        verbose_name=_("المُعتمِد"),
    )
    approved_at = models.DateTimeField(_("وقت الاعتماد"), null=True, blank=True)
    rejection_reason = models.TextField(_("سبب الرفض"), blank=True)

    note = models.TextField(_("ملاحظة"), blank=True)

    class Meta:
        verbose_name = _("مصروف")
        verbose_name_plural = _("المصروفات")
        ordering = ["-incurred_on", "-created_at"]
        indexes = [
            # The dominant query: a period's expenses in a given state
            models.Index(fields=["status", "incurred_on"]),
        ]

    def __str__(self):
        return f"{self.category.name_ar} · {self.amount}"

    @property
    def counts_toward_profit(self) -> bool:
        """
        ⚠️  Only approved expenses enter the profit statement.

            Including drafts makes the profit figure move every time an employee
            writes down an expense that has not been reviewed.
        """
        return self.status == ExpenseStatus.APPROVED


# ═══════════════════════════════════════════════════════════
#  Revenue and cost
# ═══════════════════════════════════════════════════════════


class RevenueSource(models.TextChoices):
    ORDER = "ORDER", _("طلب")
    REFUND = "REFUND", _("مرتجع")


class RevenueEntry(BaseModel):
    """
    A revenue entry — **captured automatically from the events**.

    ⚠️  **One entry per source — enforced by a unique database constraint.**

        `order_completed` may be emitted twice: a retry · a manual correction ·
        a listener registered twice after a reload. And without the unique
        constraint the order's revenue is counted twice, so the report says
        double what was sold — an error that is **never discovered** except by a
        manual reconciliation.

    ⚠️  And a return is **a negative entry, not a deletion of the original**.

        Deleting the revenue entry erases that the sale ever happened. An
        accounting record is corrected with an offsetting entry, not an eraser.
    """

    source = models.CharField(
        _("المصدر"), max_length=16, choices=RevenueSource.choices, db_index=True
    )

    # ⚠️  A real foreign key, not a string reference — "where did this number come
    #     from?" must be answered with a row that can be opened, not a string to search by hand.
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="revenue_entries",
        verbose_name=_("الطلب"),
    )

    gross = MoneyField(_("الإجمالي قبل الخصم"))
    discounts = MoneyField(_("الخصومات"), default=ZERO)
    tax = MoneyField(_("الضريبة"), default=ZERO)
    #: ⚠️  Net sales **excluding tax**: tax is collected for the state and is not
    #:     owned, so counting it as revenue inflates the profit by its full rate.
    net = MoneyField(_("صافي المبيعات"))

    channel = models.CharField(_("القناة"), max_length=16, blank=True, db_index=True)
    occurred_on = models.DateField(_("تاريخ الاستحقاق"), db_index=True)

    class Meta:
        verbose_name = _("قيد إيراد")
        verbose_name_plural = _("قيود الإيراد")
        ordering = ["-occurred_on", "-created_at"]
        constraints = [
            # ⚠️  This constraint is the only guard against duplicated revenue.
            #     A check in code alone loses the race between two concurrent orders.
            models.UniqueConstraint(
                fields=["source", "order"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_revenue_entry_per_source_order",
            ),
        ]

    def __str__(self):
        return f"{self.get_source_display()} · {self.net}"


class COGSEntry(BaseModel):
    """
    The cost of goods sold.

    ⚠️  **From `Batch.unit_cost` at the time of sale, not from today's average.**

        The system consumes batches by FEFO, and every sale movement carries its
        batch's cost. Computing the cost from a current average gives a profit
        matching no sale that actually happened — and it changes retroactively
        every time a new batch arrives.

    ⚠️  And `unknown_quantity` is not a detail.

        Stock entered with no batch is sold at an unknown cost. Treating it as
        zero makes the profit appear higher than reality by the full price of
        the goods — the worst possible direction for an error. It is counted and
        displayed rather than swallowed.
    """

    revenue_entry = models.OneToOneField(
        RevenueEntry,
        on_delete=models.CASCADE,
        related_name="cogs",
        verbose_name=_("قيد الإيراد"),
    )

    amount = MoneyField(_("التكلفة"), default=ZERO)

    quantity = models.PositiveIntegerField(_("الكمية"), default=0)
    unknown_quantity = models.PositiveIntegerField(
        _("كمية بتكلفة مجهولة"),
        default=0,
        help_text=_("بضاعة بلا دفعة مرتبطة — تكلفتها غير معروفة"),
    )

    class Meta:
        verbose_name = _("قيد تكلفة")
        verbose_name_plural = _("قيود التكلفة")

    def __str__(self):
        return f"COGS {self.amount}"

    @property
    def is_complete(self) -> bool:
        """The cost is fully known — no unknown quantity."""
        return self.unknown_quantity == 0


# ═══════════════════════════════════════════════════════════
#  Closing periods
# ═══════════════════════════════════════════════════════════


class FiscalPeriod(TimeStampedModel):
    """
    A fiscal month — closed, and then never edited.

    ⚠️  **A closed period accepts no new expense and no edit.**

        A profit report that was issued, acted upon, and then changed
        retroactively is the worst thing that can happen in a financial system:
        nobody knows which version was correct. Corrections are posted in the
        open period.

    ⚠️  And its key is `(year, month)`, not a UUID.

        The key **is** the meaning: "2026-03" is read and queried directly,
        and it appears in no public URL.
    """

    year = models.PositiveIntegerField(_("السنة"))
    month = models.PositiveSmallIntegerField(_("الشهر"))

    is_closed = models.BooleanField(_("مقفلة"), default=False, db_index=True)
    closed_at = models.DateTimeField(_("وقت الإقفال"), null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_periods",
        verbose_name=_("أقفلها"),
    )
    note = models.TextField(_("ملاحظة"), blank=True)

    class Meta:
        verbose_name = _("فترة مالية")
        verbose_name_plural = _("الفترات المالية")
        ordering = ["-year", "-month"]
        constraints = [
            models.UniqueConstraint(fields=["year", "month"], name="unique_fiscal_period"),
        ]

    def __str__(self):
        return f"{self.year}-{self.month:02d}"

    @classmethod
    def is_locked(cls, on_date) -> bool:
        """
        ⚠️  A period that **does not exist is open**.

            Treating absence as closed blocked the very first expense entered
            into the system — with nothing to explain why to the user.
        """
        return cls.objects.filter(year=on_date.year, month=on_date.month, is_closed=True).exists()

    def close(self, by=None, note: str = "") -> None:
        self.is_closed = True
        self.closed_at = timezone.now()
        self.closed_by = by
        self.note = note
        self.save(update_fields=["is_closed", "closed_at", "closed_by", "note", "updated_at"])
