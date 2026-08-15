"""
الطلبات — «معاملة تجارية مؤكدة».

⚠️  كل رقم هنا **لقطة تاريخية**.

    السعر والنسبة الضريبية واسم المنتج — كلها منسوخة وقت الطلب.
    الفاتورة الصادرة لا تتغيّر بتغيّر الكتالوج أو الضريبة أو
    قوائم الأسعار. حسابها لاحقًا من القيم الحالية يزوّر السجل
    ويكسر أي مراجعة ضريبية أو محاسبية.
"""

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.identifiers import business_number
from core.models.base import BaseModel
from core.money import CurrencyField, MoneyField, RateField


def order_number() -> str:
    return business_number("ORD", random_length=6)


class OrderChannel(models.TextChoices):
    """
    قناة البيع.

    ⚠️  **يُخلق في المرحلة ٥ ولو كانت القيمة الوحيدة `ONLINE`.** (ADR-09)

        نقطة البيع في المرحلة ٧، لكن إضافة الحقل بعد تراكم الطلبات
        تعني أن كل طلب سابق بلا قناة — فلا تقرير مبيعات يفصل
        القنوات رجعيًا.
    """

    ONLINE = "ONLINE", _("متجر إلكتروني")
    POS = "POS", _("نقطة بيع")
    EMPLOYEE = "EMPLOYEE", _("موظف")
    PHONE = "PHONE", _("هاتف")


class OrderStatus(models.TextChoices):
    PENDING = "PENDING", _("قيد الانتظار")
    CONFIRMED = "CONFIRMED", _("مؤكد")
    PROCESSING = "PROCESSING", _("قيد التجهيز")
    SHIPPED = "SHIPPED", _("تم الشحن")
    DELIVERED = "DELIVERED", _("تم التسليم")
    COMPLETED = "COMPLETED", _("مكتمل")
    CANCELLED = "CANCELLED", _("ملغى")
    REFUNDED = "REFUNDED", _("مسترد")


class PaymentStatus(models.TextChoices):
    """
    ⚠️  حالة الدفع **منفصلة** عن حالة الطلب.

        طلب مؤكد قد يكون غير مدفوع (دفع عند الاستلام)، وطلب ملغى
        قد يكون مدفوعًا وينتظر الاسترداد. دمجهما في حقل واحد يجعل
        نصف الحالات الحقيقية غير قابلة للتمثيل.
    """

    UNPAID = "UNPAID", _("غير مدفوع")
    PENDING = "PENDING", _("قيد المعالجة")
    PAID = "PAID", _("مدفوع")
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED", _("مسترد جزئيًا")
    REFUNDED = "REFUNDED", _("مسترد بالكامل")
    FAILED = "FAILED", _("فشل")


class Order(BaseModel):
    number = models.CharField(
        _("رقم الطلب"),
        max_length=32,
        unique=True,
        default=order_number,
        db_index=True,
        help_text=_("للعرض والدعم — ليس معرّف الرابط"),
    )

    customer = models.ForeignKey(
        "customers.CustomerProfile",
        on_delete=models.PROTECT,
        related_name="orders",
        # ⚠️  **اختياري — لبيع الكاونتر وحده.** (المرحلة ٧)
        #
        #     المشتري في متجر فعلي لا يملك حسابًا غالبًا، وإلزام
        #     العميل هنا يعني أحد أمرين: إمّا كاشير يرفض البيع لمن
        #     لا يسجّل، وإمّا كاشير يخترع حسابًا وهميًا لكل عابر —
        #     فيمتلئ سجل العملاء بأشخاص لا وجود لهم وتصير كل إحصاءة
        #     عنهم كذبًا.
        #
        #     `null` هنا يعني «بيعة كاونتر» صراحةً، وهو ما تقرؤه
        #     التقارير بلا لبس.
        #
        #     ⚠️  وكل قارئ لهذا الحقل يجب أن يحتمل الغياب —
        #         `notifications/listeners.py` يفعل.
        null=True,
        blank=True,
        verbose_name=_("العميل"),
        help_text=_("فارغ = بيعة كاونتر لعميل بلا حساب"),
    )

    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=OrderStatus.choices,
        default=OrderStatus.PENDING,
        db_index=True,
    )
    payment_status = models.CharField(
        _("حالة الدفع"),
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID,
        db_index=True,
    )

    # ── القناة والموقع — حقول مبكرة (ADR-09) ───────────────
    channel = models.CharField(
        _("القناة"),
        max_length=16,
        choices=OrderChannel.choices,
        default=OrderChannel.ONLINE,
        db_index=True,
    )
    location = models.ForeignKey(
        "inventory.StockLocation",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders",
        verbose_name=_("الموقع"),
        help_text=_("فرع نقطة البيع أو المخزن المُصرِّف"),
    )

    # ── الإسناد — تُخلق الآن وتبقى فارغة حتى المرحلة ١٠ ────
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders_created",
        verbose_name=_("أنشأه"),
        help_text=_("الموظف أو الكاشير — فارغ للطلبات الإلكترونية"),
    )
    owner_employee = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders_owned",
        verbose_name=_("الموظف المسؤول"),
        help_text=_("للمرحلة ١٠ — يُملأ لاحقًا"),
    )
    commission_employee = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders_commissioned",
        verbose_name=_("موظف العمولة"),
        help_text=_("للمرحلة ١١ — قد يختلف عن المسؤول"),
    )

    # ── المبالغ — لقطات ────────────────────────────────────
    currency = CurrencyField()
    subtotal = MoneyField(_("الإجمالي قبل الخصم"), default=0)
    discount_total = MoneyField(_("إجمالي الخصم"), default=0)
    coupon_discount = MoneyField(_("خصم الكوبون"), default=0)
    tax_total = MoneyField(_("إجمالي الضريبة"), default=0)
    shipping_total = MoneyField(_("إجمالي الشحن"), default=0)
    grand_total = MoneyField(_("الإجمالي النهائي"), default=0)

    coupon_code = models.CharField(_("كود الكوبون"), max_length=32, blank=True)

    # ── لقطة العنوان ───────────────────────────────────────
    shipping_method_code = models.CharField(_("طريقة الشحن"), max_length=50, blank=True)
    recipient_name = models.CharField(_("اسم المستلم"), max_length=200, blank=True)
    recipient_phone = models.CharField(_("هاتف المستلم"), max_length=20, blank=True)
    governorate = models.CharField(_("المحافظة"), max_length=100, blank=True)
    city = models.CharField(_("المدينة"), max_length=100, blank=True)
    street = models.TextField(_("العنوان"), blank=True)
    building = models.CharField(_("رقم العقار"), max_length=50, blank=True)
    landmark = models.CharField(_("علامة مميزة"), max_length=200, blank=True)

    customer_note = models.TextField(_("ملاحظة العميل"), blank=True)
    internal_note = models.TextField(_("ملاحظة داخلية"), blank=True)

    confirmed_at = models.DateTimeField(_("تاريخ التأكيد"), null=True, blank=True)
    completed_at = models.DateTimeField(_("تاريخ الإكمال"), null=True, blank=True)
    cancelled_at = models.DateTimeField(_("تاريخ الإلغاء"), null=True, blank=True)
    cancellation_reason = models.TextField(_("سبب الإلغاء"), blank=True)

    class Meta:
        verbose_name = _("طلب")
        verbose_name_plural = _("الطلبات")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["payment_status", "-created_at"]),
            models.Index(fields=["channel", "-created_at"]),
            models.Index(fields=["location", "-created_at"]),
            models.Index(fields=["owner_employee", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.number} [{self.status}]"

    @property
    def is_paid(self) -> bool:
        return self.payment_status == PaymentStatus.PAID

    @property
    def is_final(self) -> bool:
        return self.status in (
            OrderStatus.COMPLETED,
            OrderStatus.CANCELLED,
            OrderStatus.REFUNDED,
        )

    @property
    def item_count(self) -> int:
        return sum(line.quantity for line in self.lines.all())


class OrderLine(BaseModel):
    """
    سطر طلب — **كل حقل لقطة**.

    ⚠️  `tax_rate` و`tax_amount` يُخزَّنان ولا يُحسبان لاحقًا.

        لو تغيّرت الضريبة من ١٤٪ إلى ١٥٪ العام القادم، تبقى
        الفواتير القديمة بـ ١٤٪. حسابها من النسبة الحالية يزوّر
        السجل المحاسبي ويكسر أي مراجعة ضريبية. (ADR-30)

    ⚠️  واسم المنتج منسوخ أيضًا — المنتج قد يُعاد تسميته أو يُحذف
        ناعمًا، والفاتورة يجب أن تبقى مقروءة.
    """

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="lines", verbose_name=_("الطلب")
    )
    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="order_lines",
        verbose_name=_("المنتج"),
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="order_lines",
    )

    # ── لقطة المنتج ────────────────────────────────────────
    product_sku = models.CharField(_("رمز المنتج"), max_length=64)
    product_name_ar = models.CharField(_("اسم المنتج بالعربية"), max_length=200)
    product_name_en = models.CharField(_("اسم المنتج بالإنجليزية"), max_length=200)

    quantity = models.PositiveIntegerField(_("الكمية"), validators=[MinValueValidator(1)])

    # ── لقطة السعر ─────────────────────────────────────────
    unit_price = MoneyField(_("سعر الوحدة"))
    list_price = MoneyField(_("السعر المرجعي"), default=0)
    discount_amount = MoneyField(_("الخصم"), default=0)

    # ── لقطة الضريبة —  ADR-30 ─────────────────────────────
    tax_rate = RateField(_("نسبة الضريبة"), default=0)
    tax_amount = MoneyField(_("قيمة الضريبة"), default=0)
    tax_class_code = models.CharField(_("رمز الفئة الضريبية"), max_length=50, blank=True)

    price_list_code = models.CharField(_("قائمة الأسعار"), max_length=50, blank=True)

    #: لقطة التكلفة — لحساب الربح في المرحلة ٨ بلا رجوع للمخزون
    unit_cost = MoneyField(_("تكلفة الوحدة"), null=True, blank=True)

    class Meta:
        verbose_name = _("سطر طلب")
        verbose_name_plural = _("أسطر الطلبات")
        ordering = ["created_at"]
        indexes = [models.Index(fields=["order", "created_at"])]

    def __str__(self):
        return f"{self.product_sku} × {self.quantity}"

    @property
    def net(self) -> "models.DecimalField":
        """الوعاء الضريبي — بعد الخصم قبل الضريبة."""
        return self.unit_price * self.quantity - self.discount_amount

    @property
    def total(self) -> "models.DecimalField":
        return self.net + self.tax_amount


class OrderStatusHistory(models.Model):
    """
    سجل تغيّر الحالة. **إضافة فقط.**

    ⚠️  يجيب على «متى تغيّرت الحالة ومن غيّرها ولماذا» — وهو ما
        يُحسم به أي نزاع مع عميل.

    مفتاح BigInt — سجل داخلي لا يظهر في رابط.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(_("من حالة"), max_length=16, blank=True)
    to_status = models.CharField(_("إلى حالة"), max_length=16)
    note = models.TextField(_("ملاحظة"), blank=True)
    changed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(_("الوقت"), auto_now_add=True)

    class Meta:
        verbose_name = _("تغيير حالة طلب")
        verbose_name_plural = _("سجل حالات الطلبات")
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.order.number}: {self.from_status} → {self.to_status}"
