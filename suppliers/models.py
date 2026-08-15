"""
الموردون وأوامر الشراء.

⚠️  **المورّد ليس المصنّع** — والفصل مقصود.

    `catalog.Manufacturer` يجيب «من صنع هذا الدواء؟» وهو سؤال
    تنظيمي يظهر على العبوة. والمورّد يجيب «ممن نشتريه؟» — وقد
    نشتري منتج نفس المصنّع من ثلاثة موزّعين بأسعار مختلفة.

    دمجهما كان يجعل تغيير الموزّع يبدو تغييرًا في بيانات الدواء.

⚠️  و**أمر الشراء يدخل المخزون عبر `inventory` لا بنفسه.**

    الاستلام يُنشئ دفعة بتكلفتها وصلاحيتها عبر
    `inventory.services.receive`. كتابة الدفعة من هنا كانت تُنشئ
    مسارًا ثانيًا للمخزون لا يمرّ بفحوصه ولا يُسجَّل في حركاته.
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


def purchase_order_number() -> str:
    return business_number("PO", random_length=6)


class Supplier(BaseModel):
    """
    مورّد — من نشتري منه.

    ⚠️  الموقوف **لا يُحذف**: أوامر شرائه ودفعاته تبقى مرجعًا
        لتكلفة بضاعة ما زالت في المخزن.
    """

    code = models.SlugField(_("الرمز"), max_length=64, unique=True)
    name_ar = models.CharField(_("الاسم بالعربية"), max_length=200)
    name_en = models.CharField(_("الاسم بالإنجليزية"), max_length=200, blank=True)

    contact_person = models.CharField(_("مسؤول التواصل"), max_length=200, blank=True)
    phone = models.CharField(_("الهاتف"), max_length=32, blank=True)
    email = models.EmailField(_("البريد"), blank=True)
    address = models.TextField(_("العنوان"), blank=True)

    tax_number = models.CharField(_("الرقم الضريبي"), max_length=50, blank=True)
    commercial_register = models.CharField(_("السجل التجاري"), max_length=50, blank=True)

    #: ⚠️  مهلة السداد **لنا نحن**: كم يومًا نتأخر في الدفع له.
    #:     عكس `payment_terms_days` في B2B التي تخصّ عملاءنا.
    payment_terms_days = models.PositiveSmallIntegerField(_("مهلة السداد (يوم)"), default=0)
    #: مهلة التوريد — من الطلب إلى الاستلام، تُستخدم في تخطيط الشراء
    lead_time_days = models.PositiveSmallIntegerField(_("مهلة التوريد (يوم)"), default=0)

    is_active = models.BooleanField(_("مفعّل"), default=True, db_index=True)
    note = models.TextField(_("ملاحظة"), blank=True)

    class Meta:
        verbose_name = _("مورّد")
        verbose_name_plural = _("الموردون")
        ordering = ["name_ar"]

    def __str__(self):
        return self.name_ar


class SupplierProduct(BaseModel):
    """
    عرض مورّد لمنتج — **أساس الـ Marketplace**.

    ⚠️  **هذا الجدول هو ما يجعل «منتج من عدة موردين» ممكنًا.**

        بلا وسيط بين المورّد والمنتج يكون لكل منتج مورّد واحد
        مثبَّت، وتغييره يفقد تاريخ الشراء من السابق. والجدول هنا
        يحمل ما يختلف بين الموردين لنفس المنتج: السعر · الحد
        الأدنى للطلب · مهلة التوريد · رمزه لديهم.

    ⚠️  ومورّد **مفضَّل واحد** لكل منتج يفرضه قيد.

        اثنان مفضَّلان يعنيان أن أمر الشراء التلقائي لا يعرف من
        يختار — ويصير الاختيار تابعًا لترتيب الاستعلام.
    """

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.CASCADE,
        related_name="offers",
        verbose_name=_("المورّد"),
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.CASCADE,
        related_name="supplier_offers",
        verbose_name=_("المنتج"),
    )

    #: رمز المنتج لدى المورّد — يختلف عن رمزنا ويُكتب في أمر الشراء
    supplier_sku = models.CharField(_("رمز المورّد"), max_length=64, blank=True)

    unit_cost = MoneyField(_("سعر الشراء"), validators=[MinValueValidator(ZERO)])
    minimum_order_quantity = models.PositiveIntegerField(_("الحد الأدنى للطلب"), default=1)
    lead_time_days = models.PositiveSmallIntegerField(_("مهلة التوريد (يوم)"), default=0)

    is_preferred = models.BooleanField(_("المورّد المفضَّل"), default=False)
    is_active = models.BooleanField(_("متاح"), default=True, db_index=True)

    class Meta:
        verbose_name = _("عرض مورّد")
        verbose_name_plural = _("عروض الموردين")
        ordering = ["product", "unit_cost"]
        constraints = [
            models.UniqueConstraint(
                fields=["supplier", "product"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_offer_per_supplier_product",
            ),
            # ⚠️  مفضَّل واحد لكل منتج — وإلا لم يعرف أمر الشراء من يختار
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_preferred=True, deleted_at__isnull=True),
                name="one_preferred_supplier_per_product",
            ),
        ]

    def __str__(self):
        return f"{self.supplier.name_ar} · {self.product.sku}"


class PurchaseOrderStatus(models.TextChoices):
    """
    ⚠️  `PARTIAL` حالة أولى لا استثناء.

        المورّد يرسل ما توفّر لديه ويُكمل لاحقًا؛ وبلا حالة جزئية
        يُقفَل الأمر بكامله أو يبقى مفتوحًا كأن شيئًا لم يصل.
    """

    DRAFT = "DRAFT", _("مسوّدة")
    SENT = "SENT", _("مُرسَل")
    PARTIAL = "PARTIAL", _("استلام جزئي")
    RECEIVED = "RECEIVED", _("مستلَم بالكامل")
    CANCELLED = "CANCELLED", _("ملغى")


#: الحالات التي يجوز الاستلام عليها
RECEIVABLE_STATUSES = [PurchaseOrderStatus.SENT, PurchaseOrderStatus.PARTIAL]


class PurchaseOrder(BaseModel):
    """
    أمر شراء.

    ⚠️  **الإجماليات لقطة تُحسب عند الإرسال** لا عند العرض.

        سعر المورّد يتغيّر؛ وإعادة حساب أمر أُرسل من أسعار اليوم
        تُنتج مستندًا يخالف ما اتُّفق عليه — وهو ما يُقدَّم عند
        الخلاف على فاتورة.
    """

    number = models.CharField(
        _("رقم الأمر"),
        max_length=24,
        unique=True,
        default=purchase_order_number,
        editable=False,
    )

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
        verbose_name=_("المورّد"),
    )
    location = models.ForeignKey(
        "inventory.StockLocation",
        on_delete=models.PROTECT,
        related_name="purchase_orders",
        verbose_name=_("موقع الاستلام"),
    )

    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=PurchaseOrderStatus.choices,
        default=PurchaseOrderStatus.DRAFT,
        db_index=True,
    )

    expected_on = models.DateField(_("التاريخ المتوقَّع"), null=True, blank=True)
    sent_at = models.DateTimeField(_("وقت الإرسال"), null=True, blank=True)
    received_at = models.DateTimeField(_("وقت الاستلام الكامل"), null=True, blank=True)

    subtotal = MoneyField(_("الإجمالي"), default=ZERO)
    note = models.TextField(_("ملاحظة"), blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_purchase_orders",
        verbose_name=_("أنشأه"),
    )

    class Meta:
        verbose_name = _("أمر شراء")
        verbose_name_plural = _("أوامر الشراء")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["supplier", "status"]),
        ]

    def __str__(self):
        return self.number

    @property
    def is_receivable(self) -> bool:
        return self.status in RECEIVABLE_STATUSES

    @property
    def is_fully_received(self) -> bool:
        """
        ⚠️  يُقاس من الأسطر لا من الحالة.

            الحالة تُحدَّث بعد الاستلام؛ وقياسها بنفسها يجعل خطأً
            في التحديث يُخفي بضاعة لم تصل.
        """
        return all(line.is_complete for line in self.lines.all())


class PurchaseOrderLine(BaseModel):
    """
    سطر أمر شراء.

    ⚠️  **الكمية المستلمة منفصلة عن المطلوبة.**

        دمجهما يعني أن الاستلام الجزئي يُعدّل الطلب نفسه — فيختفي
        أن المورّد لم يورّد ما وعد به، وهو أهم ما يُقيَّم به.
    """

    order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name=_("الأمر"),
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="purchase_lines",
        verbose_name=_("المنتج"),
    )

    quantity_ordered = models.PositiveIntegerField(
        _("الكمية المطلوبة"), validators=[MinValueValidator(1)]
    )
    quantity_received = models.PositiveIntegerField(_("الكمية المستلمة"), default=0)

    #: ⚠️  لقطة سعر وقت الإرسال — لا تُقرأ من عرض المورّد اليوم
    unit_cost = MoneyField(_("سعر الوحدة"), validators=[MinValueValidator(ZERO)])

    class Meta:
        verbose_name = _("سطر أمر شراء")
        verbose_name_plural = _("أسطر أوامر الشراء")
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.product.sku} × {self.quantity_ordered}"

    @property
    def total(self):
        return self.unit_cost * self.quantity_ordered

    @property
    def outstanding(self) -> int:
        """المتبقي — لا يقلّ عن صفر ولو زاد المستلَم."""
        return max(self.quantity_ordered - self.quantity_received, 0)

    @property
    def is_complete(self) -> bool:
        return self.quantity_received >= self.quantity_ordered


class SupplierLedgerKind(models.TextChoices):
    INVOICE = "INVOICE", _("فاتورة مورّد")
    PAYMENT = "PAYMENT", _("سداد له")
    CREDIT_NOTE = "CREDIT_NOTE", _("إشعار دائن — مرتجع له")
    ADJUSTMENT = "ADJUSTMENT", _("تسوية")


#: الحركات التي **تزيد** ما علينا للمورّد
CREDIT_KINDS = {SupplierLedgerKind.INVOICE, SupplierLedgerKind.ADJUSTMENT}


class SupplierLedgerEntry(BaseModel):
    """
    حركة حساب مورّد — **إضافة فقط**.

    ⚠️  الاتجاه **معكوس** عن دفتر العميل: هنا نحن المدينون.

        الفاتورة تزيد ما علينا، والسداد ينقصه. خلط الاتجاهين بين
        الدفترين هو أسهل خطأ ممكن — ولذلك الثوابت مسمّاة صراحةً
        (`CREDIT_KINDS`) لا مستنتجة.
    """

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="ledger",
        verbose_name=_("المورّد"),
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="ledger_entries",
        verbose_name=_("أمر الشراء"),
    )

    kind = models.CharField(
        _("النوع"), max_length=16, choices=SupplierLedgerKind.choices, db_index=True
    )
    amount = MoneyField(_("المبلغ"), validators=[MinValueValidator(ZERO)])

    occurred_on = models.DateField(_("التاريخ"), default=timezone.localdate, db_index=True)
    due_on = models.DateField(_("الاستحقاق"), null=True, blank=True)

    reference = models.CharField(_("المرجع"), max_length=64, blank=True)
    note = models.TextField(_("ملاحظة"), blank=True)

    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_supplier_entries",
        verbose_name=_("سجّلها"),
    )

    class Meta:
        verbose_name = _("حركة حساب مورّد")
        verbose_name_plural = _("حركات حسابات الموردين")
        ordering = ["-occurred_on", "-created_at"]
        indexes = [
            models.Index(fields=["supplier", "-occurred_on"]),
        ]
        constraints = [
            # ⚠️  أمر شراء واحد لا يُفوتَر مرتين
            models.UniqueConstraint(
                fields=["purchase_order", "kind"],
                condition=models.Q(deleted_at__isnull=True, purchase_order__isnull=False),
                name="unique_supplier_entry_per_order_kind",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} · {self.amount}"

    @property
    def increases_debt(self) -> bool:
        return self.kind in CREDIT_KINDS

    @property
    def signed_amount(self):
        return self.amount if self.increases_debt else -self.amount

    def save(self, *args, **kwargs):
        """⚠️  إضافة فقط — التصحيح بتسوية معاكسة."""
        if not self._state.adding:
            raise ValueError("حركات حساب المورّد لا تُعدَّل — سجّل تسوية")
        super().save(*args, **kwargs)
