"""
المخزون — «كم المتاح؟ وماذا جرى له؟»

⚠️  حدود صارمة:

        catalog    →  ما هذا المنتج؟   ← **لا حقل كمية هناك**
        inventory  →  كم المتاح منه؟   ← هنا وحده

    وهذا النطاق **لا يستورد `orders`**. الطلبات تستدعي خدماته،
    والاتجاه يبقى نازلًا.
"""

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.identifiers import business_number
from core.models.base import BaseModel, TimeStampedModel
from core.models.translatable import BilingualNameMixin
from core.money import MoneyField


def batch_number() -> str:
    return business_number("BAT", random_length=6)


def movement_reference() -> str:
    return business_number("MOV", random_length=8)


def count_reference() -> str:
    # ⚠️  دالة مسماة لا lambda — Django لا يستطيع تسلسل الـ lambda
    #     في ملف الترحيل.
    return business_number("CNT", random_length=6)


# ═══════════════════════════════════════════════════════════
#  المواقع المخزنية
# ═══════════════════════════════════════════════════════════


class LocationKind(models.TextChoices):
    WAREHOUSE = "WAREHOUSE", _("مخزن")
    BRANCH = "BRANCH", _("فرع")
    QUARANTINE = "QUARANTINE", _("حجر — تالف أو منتهٍ")
    TRANSIT = "TRANSIT", _("قيد النقل")


class StockLocation(BilingualNameMixin, BaseModel):
    """
    موقع مخزني.

    ⚠️  **يُخلق في المرحلة ٤ حتى لو كان الموقع واحدًا.** (ADR-09)

        نقطة البيع تبيع من مخزون فرعها لا من مخزون عام، وتقارير
        الفروع مستحيلة رجعيًا. إضافته لاحقًا تعني إعادة بناء كل
        حركة مخزون سُجِّلت.
    """

    code = models.SlugField(_("الرمز"), max_length=50, unique=True)
    kind = models.CharField(
        _("النوع"),
        max_length=16,
        choices=LocationKind.choices,
        default=LocationKind.WAREHOUSE,
        db_index=True,
    )

    address = models.TextField(_("العنوان"), blank=True)
    governorate = models.CharField(_("المحافظة"), max_length=100, blank=True)
    phone = models.CharField(_("الهاتف"), max_length=20, blank=True)

    is_default = models.BooleanField(
        _("الموقع الافتراضي"),
        default=False,
        help_text=_("يُستخدم حين لا يُحدَّد موقع صراحةً"),
    )
    is_sellable = models.BooleanField(
        _("يُباع منه"),
        default=True,
        help_text=_("مخزون الحجر لا يُباع منه"),
    )
    is_active = models.BooleanField(_("مفعّل"), default=True, db_index=True)

    class Meta:
        verbose_name = _("موقع مخزني")
        verbose_name_plural = _("المواقع المخزنية")
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=models.Q(is_default=True, deleted_at__isnull=True),
                name="unique_default_stock_location",
            ),
        ]

    def __str__(self):
        return f"{self.code} · {self.name_ar}"

    @classmethod
    def get_default(cls) -> "StockLocation | None":
        return cls.objects.filter(is_default=True, is_active=True).first()


# ═══════════════════════════════════════════════════════════
#  الدفعات
# ═══════════════════════════════════════════════════════════


class Batch(BaseModel):
    """
    دفعة بتاريخ صلاحية وتكلفة.

    ⚠️  `unit_cost` **إلزامي رغم أن مستهلكه في المرحلة ٨.**

        حساب تكلفة البضاعة المباعة (COGS) **مستحيل رجعيًا** بلا
        تكلفة الدفعة — لا يمكن معرفة ربح بيعة تمت قبل شهور إن لم
        تُسجَّل تكلفتها وقتها. (ADR-09)
    """

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="batches",
        verbose_name=_("المنتج"),
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="batches",
        verbose_name=_("النسخة"),
    )
    location = models.ForeignKey(
        StockLocation,
        on_delete=models.PROTECT,
        related_name="batches",
        verbose_name=_("الموقع"),
    )

    number = models.CharField(_("رقم الدفعة"), max_length=64, default=batch_number, db_index=True)
    supplier_batch_number = models.CharField(_("رقم دفعة المورّد"), max_length=64, blank=True)

    quantity_received = models.PositiveIntegerField(_("الكمية المستلمة"))
    quantity_remaining = models.PositiveIntegerField(_("الكمية المتبقية"))

    unit_cost = MoneyField(
        _("تكلفة الوحدة"),
        validators=[MinValueValidator(0)],
        help_text=_("إلزامية — بدونها يستحيل حساب الربح لاحقًا"),
    )

    manufactured_at = models.DateField(_("تاريخ الإنتاج"), null=True, blank=True)
    expires_at = models.DateField(_("تاريخ الصلاحية"), null=True, blank=True, db_index=True)

    received_at = models.DateTimeField(_("تاريخ الاستلام"), default=timezone.now)
    is_quarantined = models.BooleanField(
        _("محجورة"), default=False, help_text=_("لا تدخل في البيع")
    )

    class Meta:
        verbose_name = _("دفعة")
        verbose_name_plural = _("الدفعات")
        # ⚠️  FEFO: الأقرب انتهاءً أولًا — لا الأقدم استلامًا.
        #     ترتيب FIFO يترك دفعة تنتهي غدًا في المخزن بينما
        #     تُباع دفعة صالحة لسنة.
        ordering = ["expires_at", "received_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity_remaining__lte=models.F("quantity_received")),
                name="batch_remaining_not_above_received",
            ),
        ]
        indexes = [
            models.Index(fields=["product", "location", "expires_at"]),
            models.Index(fields=["expires_at", "quantity_remaining"]),
        ]

    def __str__(self):
        return f"{self.number} · {self.product.sku}"

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and self.expires_at < timezone.localdate()

    @property
    def is_available(self) -> bool:
        return self.quantity_remaining > 0 and not self.is_quarantined and not self.is_expired

    def days_to_expiry(self) -> int | None:
        if self.expires_at is None:
            return None
        return (self.expires_at - timezone.localdate()).days


# ═══════════════════════════════════════════════════════════
#  رصيد المخزون
# ═══════════════════════════════════════════════════════════


class Stock(TimeStampedModel):
    """
    رصيد منتج في موقع.

    ⚠️  **قيد قاعدة البيانات هو خط الدفاع الأخير ضد البيع الزائد.**

        القفل (`select_for_update`) يحمي من التزامن — لكنه
        **لا يعمل على SQLite**. أما `CheckConstraint` فيعمل على
        الاثنين ولا يمكن تجاوزه من أي مسار كود مهما أخطأ.

        الدفاعان معًا:
          ١. قفل الصف        →  صحة تحت التزامن (PostgreSQL)
          ٢. قيد قاعدة البيانات →  استحالة رصيد سالب (الكل)

    مفتاح BigInt — جدول داخلي عالي الحجم لا يظهر في رابط.
    """

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="stock_records",
        verbose_name=_("المنتج"),
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="stock_records",
        verbose_name=_("النسخة"),
    )
    location = models.ForeignKey(
        StockLocation,
        on_delete=models.PROTECT,
        related_name="stock_records",
        verbose_name=_("الموقع"),
    )

    #: الموجود فعليًا على الرف
    quantity_physical = models.PositiveIntegerField(_("الكمية الفعلية"), default=0)
    #: محجوز لطلبات لم تُشحن بعد
    quantity_reserved = models.PositiveIntegerField(_("المحجوز"), default=0)
    #: تالف — موجود ولا يُباع
    quantity_damaged = models.PositiveIntegerField(_("التالف"), default=0)
    #: منتهي الصلاحية — موجود ولا يُباع
    quantity_expired = models.PositiveIntegerField(_("المنتهي"), default=0)

    # ── حدود التنبيه ───────────────────────────────────────
    reorder_point = models.PositiveIntegerField(
        _("حد إعادة الطلب"), default=0, help_text=_("تنبيه حين ينزل المتاح عنه")
    )
    critical_point = models.PositiveIntegerField(_("الحد الحرج"), default=0)

    last_counted_at = models.DateTimeField(_("آخر جرد"), null=True, blank=True)

    class Meta:
        verbose_name = _("رصيد مخزون")
        verbose_name_plural = _("أرصدة المخزون")
        constraints = [
            models.UniqueConstraint(
                fields=["product", "variant", "location"],
                name="unique_stock_per_product_variant_location",
            ),
            # ⚠️  استحالة رصيد سالب — الحارس النهائي
            models.CheckConstraint(
                condition=models.Q(quantity_reserved__lte=models.F("quantity_physical")),
                name="reserved_never_exceeds_physical",
            ),
        ]
        indexes = [
            models.Index(fields=["product", "location"]),
            models.Index(fields=["location", "quantity_physical"]),
        ]

    def __str__(self):
        return f"{self.product.sku} @ {self.location.code} = {self.available}"

    @property
    def available(self) -> int:
        """
        المتاح للبيع.

        الفعلي − المحجوز − التالف − المنتهي.
        هذا هو الرقم الوحيد الذي يهم عند البيع.
        """
        return max(
            0,
            self.quantity_physical
            - self.quantity_reserved
            - self.quantity_damaged
            - self.quantity_expired,
        )

    @property
    def needs_reorder(self) -> bool:
        return self.reorder_point > 0 and self.available <= self.reorder_point

    @property
    def is_critical(self) -> bool:
        return self.critical_point > 0 and self.available <= self.critical_point


# ═══════════════════════════════════════════════════════════
#  حركات المخزون
# ═══════════════════════════════════════════════════════════


class MovementType(models.TextChoices):
    """
    ⚠️  كل تغيير في المخزون يترك حركة. بلا استثناء.

        السجل هو ما يجيب على «أين ذهبت الخمسون علبة؟» — وبدونه
        لا جرد يُطابَق ولا فرق يُفسَّر.
    """

    RECEIPT = "RECEIPT", _("استلام")
    SALE = "SALE", _("بيع")
    RETURN_IN = "RETURN_IN", _("مرتجع من عميل")
    RETURN_OUT = "RETURN_OUT", _("مرتجع لمورّد")
    TRANSFER_OUT = "TRANSFER_OUT", _("تحويل صادر")
    TRANSFER_IN = "TRANSFER_IN", _("تحويل وارد")
    ADJUSTMENT_UP = "ADJUSTMENT_UP", _("تسوية بالزيادة")
    ADJUSTMENT_DOWN = "ADJUSTMENT_DOWN", _("تسوية بالنقص")
    DAMAGE = "DAMAGE", _("تلف")
    EXPIRY = "EXPIRY", _("انتهاء صلاحية")
    COUNT = "COUNT", _("تسوية جرد")
    RESERVE = "RESERVE", _("حجز")
    RELEASE = "RELEASE", _("إفراج عن حجز")


#: الحركات التي تزيد الكمية الفعلية
INBOUND = {
    MovementType.RECEIPT,
    MovementType.RETURN_IN,
    MovementType.TRANSFER_IN,
    MovementType.ADJUSTMENT_UP,
}

#: الحركات التي تنقص الكمية الفعلية
OUTBOUND = {
    MovementType.SALE,
    MovementType.RETURN_OUT,
    MovementType.TRANSFER_OUT,
    MovementType.ADJUSTMENT_DOWN,
}


class StockMovement(models.Model):
    """
    قيد حركة. **إضافة فقط** — لا تعديل ولا حذف.

    التصحيح يكون بحركة معاكسة لا بتحرير القديمة، وإلا فسد السجل
    الذي يُبنى عليه الجرد والتقارير المالية.

    مفتاح BigInt — أضخم جدول في النظام ولا يظهر في رابط.
    """

    reference = models.CharField(
        _("المرجع"), max_length=32, default=movement_reference, db_index=True
    )

    product = models.ForeignKey(
        "catalog.Product",
        on_delete=models.PROTECT,
        related_name="stock_movements",
        verbose_name=_("المنتج"),
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    location = models.ForeignKey(
        StockLocation,
        on_delete=models.PROTECT,
        related_name="stock_movements",
        verbose_name=_("الموقع"),
    )
    batch = models.ForeignKey(
        Batch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="movements",
        verbose_name=_("الدفعة"),
    )

    movement_type = models.CharField(
        _("نوع الحركة"), max_length=20, choices=MovementType.choices, db_index=True
    )
    quantity = models.PositiveIntegerField(_("الكمية"))

    #: لقطة الرصيد بعد الحركة — تسمح بمراجعة السجل بلا إعادة حساب
    balance_after = models.IntegerField(_("الرصيد بعد الحركة"), default=0)

    unit_cost = MoneyField(
        _("تكلفة الوحدة"),
        null=True,
        blank=True,
        help_text=_("لقطة وقت الحركة — تُستخدم في حساب COGS"),
    )

    #: مرجع خارجي نصي — **لا FK إلى `orders`**.
    #: `inventory` في L3 و`orders` في L6؛ المفتاح الأجنبي هنا
    #: يجعل الاتجاه صاعدًا ويكسر الحدود.
    reference_type = models.CharField(_("نوع المرجع"), max_length=32, blank=True)
    reference_id = models.CharField(_("معرّف المرجع"), max_length=64, blank=True)

    note = models.TextField(_("ملاحظة"), blank=True)
    performed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("نفّذها"),
    )
    created_at = models.DateTimeField(_("الوقت"), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("حركة مخزون")
        verbose_name_plural = _("حركات المخزون")
        # ⚠️  `-id` مفتاح ترتيب ثانوي إلزامي.
        #
        #     حركتان تُسجَّلان في نفس الميكروثانية (بيع يستهلك
        #     دفعتين مثلًا) يعطي `-created_at` وحده ترتيبًا غير
        #     مستقر — يختلف بين استعلام وآخر. وفي سجل يُبنى عليه
        #     الجرد وحساب التكلفة، الترتيب غير المستقر خطأ لا إزعاج.
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["product", "location", "-created_at"]),
            models.Index(fields=["movement_type", "-created_at"]),
            models.Index(fields=["reference_type", "reference_id"]),
            models.Index(fields=["batch", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.reference} · {self.movement_type} · {self.quantity}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("حركة المخزون للإضافة فقط — التصحيح بحركة معاكسة لا بتعديل.")
        super().save(*args, **kwargs)


# ═══════════════════════════════════════════════════════════
#  الحجز
# ═══════════════════════════════════════════════════════════


class ReservationStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("نشط")
    COMMITTED = "COMMITTED", _("مُنفَّذ")
    RELEASED = "RELEASED", _("مُفرَج عنه")
    EXPIRED = "EXPIRED", _("منتهٍ")


class StockReservation(BaseModel):
    """
    حجز مؤقت.

    ⚠️  الحجز **ينتهي بمهلة**.

        سلة مهجورة تحجز مخزونًا إلى الأبد تعني منتجًا يبدو نافدًا
        وهو متوفر. المهلة تُفرج تلقائيًا.
    """

    product = models.ForeignKey(
        "catalog.Product", on_delete=models.PROTECT, related_name="reservations"
    )
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reservations",
    )
    location = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, related_name="reservations"
    )

    quantity = models.PositiveIntegerField(_("الكمية"))
    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=ReservationStatus.choices,
        default=ReservationStatus.ACTIVE,
        db_index=True,
    )

    # مرجع نصي — لا FK صاعد إلى orders/cart
    reference_type = models.CharField(_("نوع المرجع"), max_length=32, blank=True)
    reference_id = models.CharField(_("معرّف المرجع"), max_length=64, blank=True)

    expires_at = models.DateTimeField(_("ينتهي في"), db_index=True)
    resolved_at = models.DateTimeField(_("تاريخ الحسم"), null=True, blank=True)

    class Meta:
        verbose_name = _("حجز مخزون")
        verbose_name_plural = _("حجوزات المخزون")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "expires_at"]),
            models.Index(fields=["reference_type", "reference_id"]),
        ]

    def __str__(self):
        return f"{self.product.sku} × {self.quantity} [{self.status}]"

    @property
    def is_expired(self) -> bool:
        return self.status == ReservationStatus.ACTIVE and timezone.now() > self.expires_at


# ═══════════════════════════════════════════════════════════
#  الجرد
# ═══════════════════════════════════════════════════════════


class StockCountStatus(models.TextChoices):
    DRAFT = "DRAFT", _("مسودة")
    IN_PROGRESS = "IN_PROGRESS", _("جارٍ")
    COMPLETED = "COMPLETED", _("مكتمل")
    CANCELLED = "CANCELLED", _("ملغى")


class StockCount(BaseModel):
    """جلسة جرد."""

    reference = models.CharField(
        _("المرجع"),
        max_length=32,
        unique=True,
        default=count_reference,
    )
    location = models.ForeignKey(
        StockLocation, on_delete=models.PROTECT, related_name="stock_counts"
    )
    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=StockCountStatus.choices,
        default=StockCountStatus.DRAFT,
        db_index=True,
    )

    started_at = models.DateTimeField(_("بدأ في"), null=True, blank=True)
    completed_at = models.DateTimeField(_("اكتمل في"), null=True, blank=True)
    note = models.TextField(_("ملاحظة"), blank=True)

    class Meta:
        verbose_name = _("جرد")
        verbose_name_plural = _("عمليات الجرد")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} @ {self.location.code}"


class StockCountLine(TimeStampedModel):
    """
    سطر جرد.

    الفرق يُحسب ولا يُدخَل — إدخاله يدويًا يسمح بإخفاء العجز.
    """

    count = models.ForeignKey(StockCount, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    variant = models.ForeignKey(
        "catalog.ProductVariant",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    expected_quantity = models.IntegerField(_("الكمية المتوقعة"))
    counted_quantity = models.PositiveIntegerField(_("الكمية المعدودة"))
    note = models.TextField(_("ملاحظة"), blank=True)

    class Meta:
        verbose_name = _("سطر جرد")
        verbose_name_plural = _("أسطر الجرد")
        constraints = [
            models.UniqueConstraint(
                fields=["count", "product", "variant"], name="unique_count_line"
            ),
        ]

    def __str__(self):
        return f"{self.product.sku}: {self.counted_quantity} / {self.expected_quantity}"

    @property
    def variance(self) -> int:
        """موجب = زيادة · سالب = عجز."""
        return self.counted_quantity - self.expected_quantity


# ═══════════════════════════════════════════════════════════
#  التنبيهات
# ═══════════════════════════════════════════════════════════


class AlertType(models.TextChoices):
    LOW_STOCK = "LOW_STOCK", _("مخزون منخفض")
    CRITICAL_STOCK = "CRITICAL_STOCK", _("مخزون حرج")
    OUT_OF_STOCK = "OUT_OF_STOCK", _("نفاد")
    EXPIRING_SOON = "EXPIRING_SOON", _("قرب انتهاء صلاحية")
    EXPIRED = "EXPIRED", _("انتهت الصلاحية")


class StockAlert(BaseModel):
    """
    تنبيه مخزون.

    ⚠️  **منع التكرار إلزامي.**

        منتج نافد يولّد تنبيهًا مع كل محاولة بيع — عشرات التنبيهات
        لنفس الحالة في ساعة. القيد الفريد على (نوع · منتج · موقع)
        بشرط `is_resolved=False` يجعل التنبيه واحدًا حتى يُحسم.
    """

    alert_type = models.CharField(
        _("النوع"), max_length=20, choices=AlertType.choices, db_index=True
    )
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.CASCADE, related_name="stock_alerts"
    )
    location = models.ForeignKey(
        StockLocation, on_delete=models.CASCADE, related_name="stock_alerts"
    )
    batch = models.ForeignKey(
        Batch, on_delete=models.CASCADE, null=True, blank=True, related_name="alerts"
    )

    current_value = models.IntegerField(_("القيمة الحالية"), default=0)
    threshold_value = models.IntegerField(_("قيمة الحد"), default=0)

    is_resolved = models.BooleanField(_("محسوم"), default=False, db_index=True)
    resolved_at = models.DateTimeField(_("تاريخ الحسم"), null=True, blank=True)

    class Meta:
        verbose_name = _("تنبيه مخزون")
        verbose_name_plural = _("تنبيهات المخزون")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["alert_type", "product", "location"],
                condition=models.Q(is_resolved=False, deleted_at__isnull=True),
                name="unique_unresolved_alert",
            ),
        ]
        indexes = [models.Index(fields=["is_resolved", "-created_at"])]

    def __str__(self):
        return f"{self.alert_type} · {self.product.sku} @ {self.location.code}"
