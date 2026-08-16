"""
B2B — الصيدليات وتجار الجملة.

⚠️  **الآجل هو كل الفرق بين B2C وB2B.**

    عميل التجزئة يدفع ثم يستلم. والصيدلية تستلم ثم تدفع بعد
    ثلاثين يومًا — وهذا يقلب المخاطرة: البضاعة تخرج والمال لم
    يدخل. كل ما في هذا الملف يخدم سؤالًا واحدًا: **كم يدين لنا
    هذا العميل، وهل يُسمح له بالمزيد؟**

⚠️  والرصيد **يُشتق من دفتر الحركات لا يُخزَّن حقلًا**.

    حقل `balance` يُحدَّث بالجمع والطرح ينحرف عن الدفتر عند أول
    استثناء في منتصف معاملة، أو أول تصحيح يدوي في قاعدة
    البيانات. والانحراف في رصيد ائتماني يعني إما منع عميل ملتزم
    أو تمديد ائتمان لمتعثّر — ولا أحد يعرف أيهما وقع.
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
    ⚠️  الحساب يبدأ **بلا ائتمان** لا بحدٍّ افتراضي.

        حدّ ائتماني تلقائي يعني بضاعة تخرج لعميل لم يراجعه أحد.
        المنح قرار صريح بمبلغ محدَّد ومن شخص معلوم.
    """

    NONE = "NONE", _("بلا ائتمان — دفع مقدَّم")
    ACTIVE = "ACTIVE", _("ائتمان نشط")
    SUSPENDED = "SUSPENDED", _("موقوف")


class BusinessProfile(BaseModel):
    """
    الملف التجاري — فوق `CustomerProfile` لا بديلًا عنه.

    ⚠️  **لا تكرار لبيانات العميل.**

        الاسم والهاتف والعناوين والرقم الضريبي كلها في
        `CustomerProfile` أصلًا. نسخها هنا ينشئ مصدرَي حقيقة
        يتباعدان عند أول تعديل — والفاتورة تُطبَع من أيّهما صادف.
        هذا الملف يحمل **ما لا يخصّ إلا الآجل**.
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

    #: رقم ترخيص مزاولة المهنة — يُراجَع يدويًا مع الوثائق
    license_number = models.CharField(_("رقم الترخيص"), max_length=64, blank=True)
    license_expires_on = models.DateField(_("انتهاء الترخيص"), null=True, blank=True)

    # ── الائتمان ───────────────────────────────────────────
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
    #: ⚠️  صفر = دفع مقدَّم. لا قيمة افتراضية «معقولة» هنا:
    #:     ثلاثون يومًا تُمنَح بقرار لا تُورَث من إعداد.
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
        ⚠️  الترخيص بلا تاريخ انتهاء يُعتبر **ساريًا**.

            اعتبار الغياب انتهاءً كان يمنع كل عميل قديم لم يُسجَّل
            تاريخ ترخيصه — وهو نقص بيانات لا مخالفة.

        ⚠️  و`localdate()` لا `now().date()`.

            الثانية تُرجع تاريخ **UTC**، وهو متأخر بيوم عن القاهرة
            بين منتصف الليل والثالثة فجرًا. فترخيص انتهى أمس يُقرأ
            ساريًا في تلك الساعات — والآجل يُمنَح على أساسه.
        """
        if self.license_expires_on is None:
            return True
        return self.license_expires_on >= timezone.localdate()

    @property
    def allows_credit(self) -> bool:
        return self.credit_status == CreditStatus.ACTIVE and self.credit_limit > ZERO


# ═══════════════════════════════════════════════════════════
#  دفتر الحساب
# ═══════════════════════════════════════════════════════════


class LedgerKind(models.TextChoices):
    """
    ⚠️  الإشارة جزء من المعنى لا من الحقل.

        `CHARGE` تزيد المديونية و`PAYMENT` تنقصها. تخزين مبلغ
        سالب للسداد كان يجعل كل استعلام يحتاج معرفة الاصطلاح،
        وأول من ينساه يقلب كشف الحساب.
    """

    CHARGE = "CHARGE", _("مديونية — طلب آجل")
    PAYMENT = "PAYMENT", _("سداد")
    CREDIT_NOTE = "CREDIT_NOTE", _("إشعار دائن — مرتجع")
    ADJUSTMENT = "ADJUSTMENT", _("تسوية يدوية")


#: الحركات التي **تزيد** ما على العميل
DEBIT_KINDS = {LedgerKind.CHARGE, LedgerKind.ADJUSTMENT}


class LedgerEntry(BaseModel):
    """
    حركة في حساب العميل — **إضافة فقط**.

    ⚠️  لا تعديل ولا حذف: كشف الحساب مستند يُرسَل للعميل ويُبنى
        عليه نزاع. التصحيح بحركة `ADJUSTMENT` معاكسة تحمل سببها.
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
    #: ⚠️  تاريخ الاستحقاق للمديونية وحدها — هو أساس التقادم
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
            # ⚠️  طلب واحد لا يُقيَّد مديونيةً مرتين.
            #
            #     إعادة محاولة الإتمام أو حدث مكرر كانا سيضاعفان
            #     ما على العميل — فيُمنَع من الشراء بحدٍّ استهلكه
            #     مرة واحدة فقط.
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
        """المبلغ بإشارته في الرصيد — موجب على العميل، سالب له."""
        return self.amount if self.is_debit else -self.amount

    def save(self, *args, **kwargs):
        """
        ⚠️  **إضافة فقط.**

            تعديل حركة يغيّر كشف حساب أُرسل للعميل بأثر رجعي،
            فيصير النزاع بلا مرجع يُحتكَم إليه.
        """
        # ⚠️  `_state.adding` لا `self.pk`.
        #
        #     المفتاح UUID يُولَّد في بايثون **قبل** الإدراج، فيكون
        #     `pk` موجودًا على صفٍّ لم يُكتب بعد. الفحص به كان
        #     يرفض كل إنشاء — أي أن الحارس يمنع ما جاء ليحرسه.
        if not self._state.adding:
            raise ValueError("حركات الحساب لا تُعدَّل — سجّل تسوية معاكسة")
        super().save(*args, **kwargs)


# ═══════════════════════════════════════════════════════════
#  الفواتير
# ═══════════════════════════════════════════════════════════


class InvoiceStatus(models.TextChoices):
    ISSUED = "ISSUED", _("صادرة")
    PAID = "PAID", _("مسدَّدة")
    OVERDUE = "OVERDUE", _("متأخرة")
    CANCELLED = "CANCELLED", _("ملغاة")


#: الفواتير **القائمة** — ما زال على العميل سدادها.
#
# ⚠️  `OVERDUE` حالة عرضية لا مصير.
#
#     الفاتورة المتأخرة ما زالت مستحقة؛ استبعادها من استعلامات
#     «المفتوح» يجعل تعليمها متأخرةً **يخفيها** من بوابة الائتمان
#     ومن التقادم ومن تسوية السداد — أي أن أقدم الديون تسقط من
#     الحساب بمجرد أن تصير أقدم. وهو انقلاب كامل في المعنى.
OPEN_INVOICE_STATUSES = [InvoiceStatus.ISSUED, InvoiceStatus.OVERDUE]


class Invoice(BaseModel):
    """
    فاتورة آجل.

    ⚠️  **كل مبلغ فيها لقطة** — تُنسَخ من الطلب وقت الإصدار.

        قراءتها من الطلب وقت العرض تجعل فاتورة مطبوعة تخالف نسختها
        على الشاشة بعد أي تصحيح. والفاتورة مستند يُقدَّم للمحاسب.
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
        ⚠️  التأخر يُحسب لحظيًا لا يُخزَّن.

            حقل `is_overdue` مخزَّن يحتاج مهمة دورية تحدّثه، وأي
            تعطّل فيها يجعل فاتورة متأخرة تبدو سليمة — وهو الحقل
            الذي تُبنى عليه قرارات المنع.
        """
        return self.status in OPEN_INVOICE_STATUSES and self.due_on < timezone.localdate()

    @property
    def days_overdue(self) -> int:
        if not self.is_overdue:
            return 0
        return (timezone.localdate() - self.due_on).days
