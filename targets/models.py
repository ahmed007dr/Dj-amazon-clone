"""
Monthly sales targets.

⚠️  **A target per month — not one permanent target.**

    A permanent target makes Ramadan and August equal in assessment, and makes
    raising the target rewrite the history of every month past. Each month is an
    independent performance period that is closed and never rewritten.

⚠️  And **the target type is a field, not a branch in the code**.

    The requirement is to support several types with no rebuild: sales · net ·
    profit · order count · customer count. Fixing "sales" into the structure
    makes adding "profit" later touch every query.
"""

from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models.base import BaseModel
from core.money import ZERO, RateField


class TargetType(models.TextChoices):
    """
    What is measured.

    ⚠️  The stored value is a single one (`target_value`) and its meaning follows the type.

        A table with a column per type leaves most columns empty on every row,
        and forces every query to know which one it is reading.
    """

    SALES_AMOUNT = "SALES_AMOUNT", _("إجمالي المبيعات")
    NET_SALES = "NET_SALES", _("صافي المبيعات بعد المرتجعات")
    GROSS_PROFIT = "GROSS_PROFIT", _("مجمل الربح")
    ORDER_COUNT = "ORDER_COUNT", _("عدد الطلبات")
    CUSTOMER_COUNT = "CUSTOMER_COUNT", _("عدد العملاء النشطين")


#: The types whose value is **an amount** — the rest are integers
MONETARY_TYPES = {
    TargetType.SALES_AMOUNT,
    TargetType.NET_SALES,
    TargetType.GROSS_PROFIT,
}


class TargetStatus(models.TextChoices):
    """
    ⚠️  A target starts as a **draft**.

        A target created active immediately means an entry error becomes an
        obligation on the rep before anyone has reviewed it — and a commission
        calculation gets built on it.
    """

    DRAFT = "DRAFT", _("مسوّدة")
    ACTIVE = "ACTIVE", _("نشط")
    CLOSED = "CLOSED", _("مقفل")


class MonthlyTarget(BaseModel):
    """
    An employee's target for a month.

    ⚠️  **Closing freezes a snapshot and never recomputes it.**

        A closed month is a document a commission payment is built on.
        Recomputing it from today's data means a return that occurred in March
        changes January's paid commission — and nobody knows which version was correct.
    """

    employee = models.ForeignKey(
        "employees.EmployeeProfile",
        on_delete=models.PROTECT,
        related_name="targets",
        verbose_name=_("الموظف"),
    )

    year = models.PositiveIntegerField(_("السنة"))
    month = models.PositiveSmallIntegerField(_("الشهر"))

    target_type = models.CharField(
        _("نوع الهدف"),
        max_length=24,
        choices=TargetType.choices,
        default=TargetType.NET_SALES,
        db_index=True,
    )
    target_value = models.DecimalField(
        _("قيمة الهدف"),
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(ZERO)],
        help_text=_("مبلغ للأنواع المالية · عدد صحيح لما عداها"),
    )

    #: ⚠️  Below this percentage there is **no commission at all**.
    #:
    #:     With no minimum, a rep who sold 5% of their target earns a commission —
    #:     a reward for failure. Zero means "no minimum" and is chosen explicitly.
    minimum_achievement_percent = RateField(_("الحد الأدنى للتحقيق ٪"), default=ZERO)

    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=TargetStatus.choices,
        default=TargetStatus.DRAFT,
        db_index=True,
    )

    note = models.TextField(_("ملاحظة"), blank=True)

    # ── The closing snapshot ───────────────────────────────
    # ⚠️  Written once at closing and never touched afterwards.
    achieved_value = models.DecimalField(
        _("المُحقَّق"), max_digits=14, decimal_places=2, null=True, blank=True
    )
    achievement_percent = RateField(_("نسبة التحقيق ٪"), null=True, blank=True)

    closed_at = models.DateTimeField(_("وقت الإقفال"), null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="closed_targets",
        verbose_name=_("أقفله"),
    )

    class Meta:
        verbose_name = _("هدف شهري")
        verbose_name_plural = _("الأهداف الشهرية")
        ordering = ["-year", "-month"]
        constraints = [
            # ⚠️  One target per employee per month.
            #
            #     Two targets mean two achievement percentages and two commission
            #     results, with no rule to settle which is paid.
            models.UniqueConstraint(
                fields=["employee", "year", "month"],
                condition=models.Q(deleted_at__isnull=True),
                name="one_target_per_employee_month",
            ),
        ]
        indexes = [
            models.Index(fields=["year", "month", "status"]),
        ]

    def __str__(self):
        return f"{self.employee.employee_number} · {self.year}-{self.month:02d}"

    @property
    def is_monetary(self) -> bool:
        return self.target_type in MONETARY_TYPES

    @property
    def is_closed(self) -> bool:
        return self.status == TargetStatus.CLOSED

    def close(self, *, achieved, percent, by=None) -> None:
        """
        ⚠️  Closing happens **once**.

            Repeating it writes a new snapshot over an approved one, changing a
            paid commission retroactively.
        """
        self.achieved_value = achieved
        self.achievement_percent = percent
        self.status = TargetStatus.CLOSED
        self.closed_at = timezone.now()
        self.closed_by = by
        self.save(
            update_fields=[
                "achieved_value",
                "achievement_percent",
                "status",
                "closed_at",
                "closed_by",
                "updated_at",
            ]
        )
