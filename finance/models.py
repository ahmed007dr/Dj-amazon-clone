"""
المالية — الإيرادات والمصروفات وتكلفة البضاعة المباعة.

⚠️  **كل رقم قابل للتتبع إلى مصدره. لا حساب صندوق أسود.**

    قيد الإيراد يحمل مفتاحًا أجنبيًا للطلب، وقيد التكلفة يحمل
    مرجع الدفعة التي خرجت منها البضاعة فعلًا. سؤال «من أين جاء
    هذا الرقم؟» يجب أن يُجاب بصفٍّ لا بحساب.

⚠️  و`Decimal` حصرًا — لا `float` في أي حساب مالي.

    مع مرتجعات وخصومات وضرائب تتراكم فروق الفاصلة العائمة حتى
    تكسر أي مطابقة محاسبية.
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
    ⚠️  مسار **خاص** باسم عشوائي.

        فاتورة إيجار تحمل اسم المؤجّر ومبلغه. تركها تحت اسمها
        الأصلي في مسار عام يجعلها تُقرأ بمن يعرف الرابط، ومسارًا
        تسلسليًا يُخمَّن بحلقة.
    """
    return f"private/expense-attachments/{random_filename(filename)}"


# ═══════════════════════════════════════════════════════════
#  المصروفات
# ═══════════════════════════════════════════════════════════


class ExpenseCategory(BaseModel):
    """
    بند مصروف — شجري.

    ⚠️  الشجرة لأن «مرافق» تنقسم إلى كهرباء وماء وإنترنت.

        قائمة مسطّحة تجبر صاحب النشاط على الاختيار بين بندٍ عام
        لا يفيد التحليل وعشرين بندًا لا يُقرأ أيّها.
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
    ⚠️  المصروف يبدأ **مسوَّدة** لا معتمدًا.

        الاعتماد التلقائي يجعل كل خطأ إدخال يدخل قائمة الأرباح
        فورًا — ورقم خاطئ في تقرير مالي أسوأ من رقم ناقص، لأنه
        يُتخذ عليه قرار.
    """

    DRAFT = "DRAFT", _("مسوّدة")
    APPROVED = "APPROVED", _("معتمد")
    REJECTED = "REJECTED", _("مرفوض")


class PaymentMean(models.TextChoices):
    """كيف خرج المال — للتدفق النقدي."""

    CASH = "CASH", _("نقدًا")
    BANK = "BANK", _("تحويل بنكي")
    CARD = "CARD", _("بطاقة")
    OTHER = "OTHER", _("أخرى")


class Expense(BaseModel):
    """
    مصروف تشغيلي — **يُدخَل يدويًا**.

    ⚠️  `incurred_on` تاريخ **الاستحقاق لا الإدخال**.

        إيجار مارس يُدخَل في أبريل ويجب أن يظهر في أرباح مارس.
        الخلط بينهما ينقل المصروف إلى الشهر التالي فيُظهر شهرًا
        رابحًا وآخر خاسرًا بلا سبب حقيقي.
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
    # ⚠️  `SET_NULL` لا `PROTECT`: حذف حساب معتمِد قديم يجب ألا
    #     يحمي مصروفًا من الحذف ولا يفشل بخطأ تكامل غامض.
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
            # الاستعلام السائد: مصروفات فترة بحالة معيّنة
            models.Index(fields=["status", "incurred_on"]),
        ]

    def __str__(self):
        return f"{self.category.name_ar} · {self.amount}"

    @property
    def counts_toward_profit(self) -> bool:
        """
        ⚠️  المعتمد وحده يدخل الأرباح.

            إدخال المسوّدات يجعل رقم الربح يتحرّك كلما كتب موظف
            مصروفًا لم يُراجَع بعد.
        """
        return self.status == ExpenseStatus.APPROVED


# ═══════════════════════════════════════════════════════════
#  الإيرادات والتكلفة
# ═══════════════════════════════════════════════════════════


class RevenueSource(models.TextChoices):
    ORDER = "ORDER", _("طلب")
    REFUND = "REFUND", _("مرتجع")


class RevenueEntry(BaseModel):
    """
    قيد إيراد — **يُلتقط تلقائيًا من الأحداث**.

    ⚠️  **قيد واحد لكل مصدر — يفرضه قيد فريد في قاعدة البيانات.**

        `order_completed` قد تُبعَث مرتين: إعادة محاولة · تصحيح
        يدوي · مستمع سُجّل مرتين بعد إعادة تحميل. وبلا القيد
        الفريد يُحتسب إيراد الطلب مرتين، فيقول التقرير ضعف ما
        بيع — وهو خطأ **لا يُكتشف** إلا بمطابقة يدوية.

    ⚠️  والمرتجع **قيد سالب لا حذف للأصلي**.

        حذف قيد الإيراد يمحو أن البيعة وقعت أصلًا. السجل
        المحاسبي يُصحَّح بقيد معاكس لا بممحاة.
    """

    source = models.CharField(
        _("المصدر"), max_length=16, choices=RevenueSource.choices, db_index=True
    )

    # ⚠️  مفتاح أجنبي حقيقي لا مرجع نصي — «من أين جاء هذا الرقم؟»
    #     يجب أن يُجاب بصفٍّ يمكن فتحه، لا بسلسلة تُبحَث يدويًا.
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.PROTECT,
        related_name="revenue_entries",
        verbose_name=_("الطلب"),
    )

    gross = MoneyField(_("الإجمالي قبل الخصم"))
    discounts = MoneyField(_("الخصومات"), default=ZERO)
    tax = MoneyField(_("الضريبة"), default=ZERO)
    #: ⚠️  صافي المبيعات **بلا ضريبة**: الضريبة تُحصَّل للدولة ولا
    #:     تُملَك، فاحتسابها إيرادًا يضخّم الربح بنسبتها كاملة.
    net = MoneyField(_("صافي المبيعات"))

    channel = models.CharField(_("القناة"), max_length=16, blank=True, db_index=True)
    occurred_on = models.DateField(_("تاريخ الاستحقاق"), db_index=True)

    class Meta:
        verbose_name = _("قيد إيراد")
        verbose_name_plural = _("قيود الإيراد")
        ordering = ["-occurred_on", "-created_at"]
        constraints = [
            # ⚠️  هذا القيد هو الحارس الوحيد ضد ازدواج الإيراد.
            #     الفحص في الكود وحده يخسر السباق بين طلبين متزامنين.
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
    تكلفة البضاعة المباعة.

    ⚠️  **من `Batch.unit_cost` وقت البيع لا من متوسط اليوم.**

        النظام يستهلك الدفعات بـ FEFO، وكل حركة بيع تحمل تكلفة
        دفعتها. حساب التكلفة بمتوسط حالي يعطي ربحًا لا يطابق أي
        بيعة وقعت فعلًا — ويتغيّر بأثر رجعي كلما وصلت دفعة جديدة.

    ⚠️  و`unknown_quantity` ليس تفصيلًا.

        مخزون أُدخل بلا دفعة يُباع بتكلفة مجهولة. معاملتها كصفر
        يجعل الربح يظهر أعلى من حقيقته بثمن البضاعة كاملًا —
        وهو أسوأ اتجاه ممكن للخطأ. تُعَدّ وتُعرَض بدل أن تُبتلع.
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
        """التكلفة معروفة بالكامل — لا كمية مجهولة."""
        return self.unknown_quantity == 0


# ═══════════════════════════════════════════════════════════
#  إقفال الفترات
# ═══════════════════════════════════════════════════════════


class FiscalPeriod(TimeStampedModel):
    """
    شهر مالي — يُقفَل فلا يُعدَّل.

    ⚠️  **الفترة المقفلة لا تقبل مصروفًا جديدًا ولا تعديلًا.**

        تقرير أرباح صدر واتُّخذ عليه قرار ثم تغيّر بأثر رجعي هو
        أسوأ ما يقع في نظام مالي: لا أحد يعرف أي نسخة كانت
        صحيحة. التصحيح يُقيَّد في الفترة المفتوحة.

    ⚠️  ومفتاحه `(year, month)` لا UUID.

        المفتاح **هو** المعنى: «٢٠٢٦-٠٣» يُقرأ ويُستعلَم به،
        ولا يظهر في رابط عام.
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
        ⚠️  الفترة **غير الموجودة مفتوحة**.

            اعتبار الغياب إقفالًا كان يمنع أول مصروف يُدخَل في
            النظام — ولا شيء يشرح للمستخدم السبب.
        """
        return cls.objects.filter(year=on_date.year, month=on_date.month, is_closed=True).exists()

    def close(self, by=None, note: str = "") -> None:
        self.is_closed = True
        self.closed_at = timezone.now()
        self.closed_by = by
        self.note = note
        self.save(update_fields=["is_closed", "closed_at", "closed_by", "note", "updated_at"])
