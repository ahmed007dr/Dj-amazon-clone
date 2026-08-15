"""
العمولات.

⚠️  **كل نتيجة عمولة قابلة للتفسير — لا حساب صندوق أسود.**

    المندوب يقرأ مبلغًا سيُصرَف له ويسأل «كيف؟». والجواب يجب أن
    يكون صفًّا يحمل: الطلبات المشمولة · الإجمالي · المرتجعات ·
    الصافي · التكلفة · الربح · التحقيق · القاعدة المطبَّقة ·
    النسبة · المبلغ. إعادة الحساب عند العرض تعني أن الجواب يتغيّر
    كلما تغيّرت البيانات — والمبلغ صُرف.

⚠️  و**قواعد العمولة بيانات لا كود**.

    «٣٪ فوق ١٠٠٪ تحقيق» قرار إداري يتغيّر كل موسم. تثبيته في
    الكود يجعل تعديله نشرًا.
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
    ما الذي تُحسب النسبة عليه.

    ⚠️  الفارق جوهري لا شكلي: ٣٪ من المبيعات قد تفوق ١٠٪ من
        الربح أو تقلّ عنها بأضعاف — حسب هامش الصنف المباع.
    """

    NET_SALES = "NET_SALES", _("صافي المبيعات")
    GROSS_PROFIT = "GROSS_PROFIT", _("مجمل الربح")


class CommissionScheme(BaseModel):
    """
    خطة عمولة — حزمة شرائح.

    ⚠️  **الخطة تُسنَد للدور لا للفرد** ما لم يُخصَّص.

        منحها فردًا يجعل كل تعيين جديد يحتاج ضبطًا يدويًا، ويجعل
        سؤال «ما عمولة المندوبين؟» يحتاج مسح كل الحسابات.
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
    شريحة: «من نسبة تحقيق كذا إلى كذا ⟵ نسبة عمولة كذا».

    ⚠️  **الحدود شاملة من الأسفل حصرية من الأعلى** — `[from, to)`.

        تداخل الحدود يجعل تحقيق ٨٠٪ يطابق شريحتين، ويصير المبلغ
        تابعًا لترتيب الاستعلام. والاصطلاح مكتوب هنا لأن نصفه
        في الرأس ونصفه في الكود هو ما يُنتج فجوة عند ٨٠ بالضبط.

    ⚠️  والشريحة العليا **بلا سقف** (`to_percent = null`).

        سقف مكتوب يعني أن من حقّق ٥٠٠٪ لا يطابق أي شريحة —
        فيخرج بعمولة صفر مكافأةً على أفضل شهر في حياته.
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
    ⚠️  العمولة تبدأ **محسوبة** لا معتمدة.

        الاعتماد التلقائي يجعل خطأ في هدف أو مرتجعًا متأخرًا
        يتحوّل إلى مبلغ مصروف قبل أن يراجعه أحد.
    """

    CALCULATED = "CALCULATED", _("محسوبة")
    APPROVED = "APPROVED", _("معتمدة")
    PAID = "PAID", _("مصروفة")
    REJECTED = "REJECTED", _("مرفوضة")


class CommissionRecord(BaseModel):
    """
    نتيجة عمولة شهر — **بكل مدخلاتها مخزَّنة**.

    ⚠️  **لا حقل هنا يُعاد حسابه عند العرض.**

        المبلغ يُصرَف، ثم يقع مرتجع في الشهر التالي. إعادة الحساب
        عند فتح الشاشة تُظهر رقمًا يخالف ما صُرف — فيبدو النظام
        كاذبًا أو المحاسب مخطئًا، ولا سبيل لحسم أيّهما.

        التصحيح يكون بسجل جديد لا بتعديل هذا.
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

    # ── المدخلات — لقطة لا تُعاد حسابها ────────────────────
    orders_count = models.PositiveIntegerField(_("عدد الطلبات"), default=0)
    gross_sales = MoneyField(_("إجمالي المبيعات"), default=ZERO)
    returns_total = MoneyField(_("المرتجعات"), default=ZERO)
    net_sales = MoneyField(_("صافي المبيعات"), default=ZERO)
    cost_total = MoneyField(_("تكلفة البضاعة"), default=ZERO)
    gross_profit = MoneyField(_("مجمل الربح"), default=ZERO)

    target_value = models.DecimalField(_("قيمة الهدف"), max_digits=14, decimal_places=2)
    achieved_value = models.DecimalField(_("المُحقَّق"), max_digits=14, decimal_places=2)
    achievement_percent = RateField(_("نسبة التحقيق ٪"))

    # ── القاعدة المطبَّقة ──────────────────────────────────
    base = models.CharField(_("أساس الحساب"), max_length=16, choices=CommissionBase.choices)
    base_amount = MoneyField(_("المبلغ الأساس"), default=ZERO)
    #: ⚠️  وصف الشريحة نصًّا: حذفها من الخطة لاحقًا يجب ألا يمحو
    #:     تفسير عمولة صُرفت.
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
            # ⚠️  سجل واحد لكل موظف في الشهر.
            #
            #     إعادة الحساب تُحدّث القائم ولا تُنشئ ثانيًا؛ ولولا
            #     القيد لصُرفت عمولتان عن شهر واحد.
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
        ⚠️  المعتمدة والمصروفة **لا تُعاد حسابها**.

            إعادة حساب مبلغ خرج من الخزينة تجعل السجل يخالف
            القيد المحاسبي.
        """
        return self.status in (CommissionStatus.APPROVED, CommissionStatus.PAID)
