"""
Commissions.

⚠️  **Every commission result is explainable — no black-box calculation.**

    A rep reads an amount that will be paid to them and asks "how?". And the
    answer has to be a row carrying: the orders covered · the total · the
    returns · the net · the cost · the profit · the achievement · the rule
    applied · the rate · the amount. Recomputing on display means the answer
    changes whenever the data changes — and the money has already been paid.

⚠️  And **commission rules are data, not code**.

    "3% above 100% achievement" is a management decision that changes every
    season. Fixing it in code makes editing it a deployment.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models.base import BaseModel
from core.money import ZERO, MoneyField, RateField


class CommissionBase(models.TextChoices):
    """
    What the rate is calculated on.

    ⚠️  The difference is substantive, not cosmetic: 3% of sales may exceed 10%
        of profit or fall many times below it — depending on the margin of the item sold.
    """

    NET_SALES = "NET_SALES", _("صافي المبيعات")
    GROSS_PROFIT = "GROSS_PROFIT", _("مجمل الربح")


class CommissionScheme(BaseModel):
    """
    A commission scheme — a bundle of tiers.

    ⚠️  **The scheme is assigned to the role, not the individual**, unless
        specifically overridden.

        Granting it to an individual makes every new appointment need manual
        configuration, and makes "what commission do the reps get?" require
        scanning every account.
    """

    code = models.SlugField(_("الرمز"), max_length=64, unique=True)
    name_ar = models.CharField(_("الاسم بالعربية"), max_length=120)
    name_en = models.CharField(_("الاسم بالإنجليزية"), max_length=120)

    base = models.CharField(
        _("أساس الحساب"),
        max_length=16,
        choices=CommissionBase.choices,
        default=CommissionBase.NET_SALES,
    )

    role = models.ForeignKey(
        "employees.EmployeeRole",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="commission_schemes",
        verbose_name=_("الدور"),
        help_text=_("فارغ = خطة عامة تُسنَد يدويًا"),
    )

    is_active = models.BooleanField(_("مفعّلة"), default=True, db_index=True)
    note = models.TextField(_("ملاحظة"), blank=True)

    class Meta:
        verbose_name = _("خطة عمولة")
        verbose_name_plural = _("خطط العمولة")
        ordering = ["code"]

    def __str__(self):
        return self.name_ar


class CommissionTier(BaseModel):
    """
    A tier: "from achievement X to Y ⟵ commission rate Z".

    ⚠️  **The bounds are inclusive below and exclusive above** — `[from, to)`.

        Overlapping bounds make 80% achievement match two tiers, and the amount
        then depends on query ordering. The convention is written down here
        because keeping half of it in someone's head and half in the code is
        exactly what produces a gap at precisely 80.

    ⚠️  And the top tier has **no ceiling** (`to_percent = null`).

        A written ceiling means someone who achieved 500% matches no tier — so
        they come out with zero commission as a reward for the best month of their life.
    """

    scheme = models.ForeignKey(
        CommissionScheme,
        on_delete=models.CASCADE,
        related_name="tiers",
        verbose_name=_("الخطة"),
    )

    from_percent = RateField(_("من نسبة تحقيق ٪"), validators=[MinValueValidator(ZERO)])
    to_percent = RateField(
        _("إلى نسبة تحقيق ٪"),
        null=True,
        blank=True,
        help_text=_("فارغ = بلا سقف"),
    )

    rate = RateField(
        _("نسبة العمولة ٪"),
        validators=[MinValueValidator(ZERO), MaxValueValidator(100)],
    )

    class Meta:
        verbose_name = _("شريحة عمولة")
        verbose_name_plural = _("شرائح العمولة")
        ordering = ["scheme", "from_percent"]

    def __str__(self):
        ceiling = f"{self.to_percent}٪" if self.to_percent is not None else "∞"
        return f"{self.from_percent}٪–{ceiling} ⟵ {self.rate}٪"

    def matches(self, achievement) -> bool:
        if achievement < self.from_percent:
            return False
        if self.to_percent is None:
            return True
        return achievement < self.to_percent


class CommissionStatus(models.TextChoices):
    """
    ⚠️  A commission starts **calculated**, not approved.

        Automatic approval turns an error in a target, or a late return, into
        money paid out before anyone reviews it.
    """

    CALCULATED = "CALCULATED", _("محسوبة")
    APPROVED = "APPROVED", _("معتمدة")
    PAID = "PAID", _("مصروفة")
    REJECTED = "REJECTED", _("مرفوضة")


class CommissionRecord(BaseModel):
    """
    A month's commission result — **with all of its inputs stored**.

    ⚠️  **No field here is recomputed on display.**

        The amount is paid out, and then a return lands the following month.
        Recomputing when the screen opens shows a number disagreeing with what
        was paid — so either the system looks dishonest or the accountant looks
        wrong, with no way to settle which.

        Corrections are made with a new record, never by editing this one.
    """

    employee = models.ForeignKey(
        "employees.EmployeeProfile",
        on_delete=models.PROTECT,
        related_name="commissions",
        verbose_name=_("الموظف"),
    )
    target = models.ForeignKey(
        "targets.MonthlyTarget",
        on_delete=models.PROTECT,
        related_name="commissions",
        verbose_name=_("الهدف"),
    )
    scheme = models.ForeignKey(
        CommissionScheme,
        on_delete=models.PROTECT,
        related_name="records",
        verbose_name=_("الخطة"),
    )

    year = models.PositiveIntegerField(_("السنة"))
    month = models.PositiveSmallIntegerField(_("الشهر"))

    # ── Inputs — a snapshot, never recomputed ──────────────
    orders_count = models.PositiveIntegerField(_("عدد الطلبات"), default=0)
    gross_sales = MoneyField(_("إجمالي المبيعات"), default=ZERO)
    returns_total = MoneyField(_("المرتجعات"), default=ZERO)
    net_sales = MoneyField(_("صافي المبيعات"), default=ZERO)
    cost_total = MoneyField(_("تكلفة البضاعة"), default=ZERO)
    gross_profit = MoneyField(_("مجمل الربح"), default=ZERO)

    target_value = models.DecimalField(_("قيمة الهدف"), max_digits=14, decimal_places=2)
    achieved_value = models.DecimalField(_("المُحقَّق"), max_digits=14, decimal_places=2)
    achievement_percent = RateField(_("نسبة التحقيق ٪"))

    # ── The rule applied ───────────────────────────────────
    base = models.CharField(_("أساس الحساب"), max_length=16, choices=CommissionBase.choices)
    base_amount = MoneyField(_("المبلغ الأساس"), default=ZERO)
    #: ⚠️  The tier description as text: deleting it from the scheme later must not
    #:     erase the explanation of a commission already paid.
    tier_label = models.CharField(_("الشريحة المطبَّقة"), max_length=64, blank=True)
    rate = RateField(_("نسبة العمولة ٪"), default=ZERO)

    amount = MoneyField(_("مبلغ العمولة"), default=ZERO)

    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=CommissionStatus.choices,
        default=CommissionStatus.CALCULATED,
        db_index=True,
    )
    note = models.TextField(_("ملاحظة"), blank=True)

    calculated_at = models.DateTimeField(_("وقت الحساب"), default=timezone.now)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_commissions",
        verbose_name=_("المُعتمِد"),
    )
    approved_at = models.DateTimeField(_("وقت الاعتماد"), null=True, blank=True)

    class Meta:
        verbose_name = _("سجل عمولة")
        verbose_name_plural = _("سجلات العمولة")
        ordering = ["-year", "-month"]
        constraints = [
            # ⚠️  One record per employee per month.
            #
            #     Recalculation updates the existing one rather than creating a
            #     second; without the constraint, two commissions would be paid for one month.
            models.UniqueConstraint(
                fields=["employee", "year", "month"],
                condition=models.Q(deleted_at__isnull=True),
                name="one_commission_per_employee_month",
            ),
        ]
        indexes = [
            models.Index(fields=["year", "month", "status"]),
        ]

    def __str__(self):
        return f"{self.employee.employee_number} · {self.year}-{self.month:02d} · {self.amount}"

    @property
    def is_locked(self) -> bool:
        """
        ⚠️  Approved and paid records are **never recomputed**.

            Recomputing an amount that has left the treasury makes the record
            disagree with the accounting entry.
        """
        return self.status in (CommissionStatus.APPROVED, CommissionStatus.PAID)
