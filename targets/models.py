"""
أهداف المبيعات الشهرية.

⚠️  **هدف لكل شهر — لا هدف دائم واحد.**

    الهدف الدائم يجعل شهر رمضان وشهر أغسطس متساويين في التقييم،
    ويجعل رفع الهدف يُعيد كتابة تاريخ كل شهر مضى. كل شهر فترة
    أداء مستقلة تُقفَل ولا تُعاد كتابتها.

⚠️  و**نوع الهدف حقل لا فرع في الكود**.

    المطلوب دعم أنواع متعددة بلا إعادة بناء: مبيعات · صافي ·
    ربح · عدد طلبات · عدد عملاء. تثبيت «المبيعات» في البنية يجعل
    إضافة «الربح» لاحقًا تمسّ كل استعلام.
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
    ما الذي يُقاس.

    ⚠️  القيمة المخزَّنة واحدة (`target_value`) ومعناها يتبع النوع.

        جدول بعمود لكل نوع يترك معظم الأعمدة فارغة في كل صف،
        ويجبر كل استعلام على معرفة أيّها يقرأ.
    """

    SALES_AMOUNT = "SALES_AMOUNT", _("إجمالي المبيعات")
    NET_SALES = "NET_SALES", _("صافي المبيعات بعد المرتجعات")
    GROSS_PROFIT = "GROSS_PROFIT", _("مجمل الربح")
    ORDER_COUNT = "ORDER_COUNT", _("عدد الطلبات")
    CUSTOMER_COUNT = "CUSTOMER_COUNT", _("عدد العملاء النشطين")


#: الأنواع التي قيمتها **مبلغ** — الباقي عدد صحيح
MONETARY_TYPES = {
    TargetType.SALES_AMOUNT,
    TargetType.NET_SALES,
    TargetType.GROSS_PROFIT,
}


class TargetStatus(models.TextChoices):
    """
    ⚠️  الهدف يبدأ **مسوّدة**.

        هدف يُنشأ نشطًا فورًا يعني أن خطأ إدخال يصير التزامًا على
        المندوب قبل أن يراجعه أحد — ويُبنى عليه حساب عمولة.
    """

    DRAFT = "DRAFT", _("مسوّدة")
    ACTIVE = "ACTIVE", _("نشط")
    CLOSED = "CLOSED", _("مقفل")


class MonthlyTarget(BaseModel):
    """
    هدف موظف في شهر.

    ⚠️  **الإقفال يُجمّد لقطة ولا يُعاد حسابه.**

        الشهر المقفل مستند يُبنى عليه صرف عمولة. إعادة حسابه من
        بيانات اليوم تعني أن مرتجعًا وقع في مارس يغيّر عمولة يناير
        المصروفة — ولا أحد يعرف أي نسخة كانت صحيحة.
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

    #: ⚠️  دون هذه النسبة **لا عمولة إطلاقًا**.
    #:
    #:     بلا حدّ أدنى يستحق مندوب باع ٥٪ من هدفه عمولةً — وهي
    #:     مكافأة على الإخفاق. الصفر يعني «بلا حدّ» ويُختار صراحةً.
    minimum_achievement_percent = RateField(_("الحد الأدنى للتحقيق ٪"), default=ZERO)

    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=TargetStatus.choices,
        default=TargetStatus.DRAFT,
        db_index=True,
    )

    note = models.TextField(_("ملاحظة"), blank=True)

    # ── لقطة الإقفال ───────────────────────────────────────
    # ⚠️  تُكتب مرة عند الإقفال ولا تُمسّ بعدها.
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
            # ⚠️  هدف واحد لكل موظف في الشهر.
            #
            #     هدفان يعنيان نسبتَي تحقيق ونتيجتَي عمولة، ولا
            #     قاعدة تحسم أيّهما يُصرَف.
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
        ⚠️  الإقفال **مرة واحدة**.

            إعادته تكتب لقطة جديدة فوق مُعتمَدة، فتتغيّر عمولة
            صُرفت بأثر رجعي.
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
