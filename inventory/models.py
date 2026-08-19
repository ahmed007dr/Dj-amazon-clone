"""
Inventory — "how much is available? and what happened to it?"

⚠️  Strict boundaries:

        catalog    →  what is this product?      ← **no quantity field there**
        inventory  →  how much of it is there?   ← here alone

    And this domain **does not import `orders`**. Orders call its services, and
    the direction stays downward.
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
    # ⚠️  A named function, not a lambda — Django cannot serialise a lambda
    #     into the migration file.
    return business_number("CNT", random_length=6)


# ═══════════════════════════════════════════════════════════
#  Stock locations
# ═══════════════════════════════════════════════════════════


class LocationKind(models.TextChoices):
    WAREHOUSE = "WAREHOUSE", _("مخزن")
    BRANCH = "BRANCH", _("فرع")
    QUARANTINE = "QUARANTINE", _("حجر — تالف أو منتهٍ")
    TRANSIT = "TRANSIT", _("قيد النقل")


class StockLocation(BilingualNameMixin, BaseModel):
    """
    A stock location.

    ⚠️  **Created in phase 4 even if there is only one location.** (ADR-09)

        Point of sale sells from its branch's stock, not from a general stock,
        and branch reports are impossible retrospectively. Adding it later means
        rebuilding every stock movement ever recorded.
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
#  Batches
# ═══════════════════════════════════════════════════════════


class Batch(BaseModel):
    """
    A batch with an expiry date and a cost.

    ⚠️  `unit_cost` is **mandatory even though its consumer arrives in phase 8.**

        Calculating the cost of goods sold (COGS) is **retrospectively
        impossible** without the batch cost — the profit of a sale made months
        ago cannot be known unless its cost was recorded at the time. (ADR-09)
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
        # ⚠️  FEFO: nearest to expiry first — not oldest received first.
        #     FIFO ordering leaves a batch expiring tomorrow in the warehouse
        #     while a batch good for a year gets sold.
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
#  Stock balance
# ═══════════════════════════════════════════════════════════


class Stock(TimeStampedModel):
    """
    A product's balance at a location.

    ⚠️  **The database constraint is the last line of defence against overselling.**

        The lock (`select_for_update`) protects against concurrency — but it
        **does nothing on SQLite**. A `CheckConstraint`, by contrast, works on
        both engines and cannot be bypassed by any code path however wrong.

        The two defences together:
          1. the row lock          →  correctness under concurrency (PostgreSQL)
          2. the database constraint →  a negative balance is impossible (both)

    A BigInt key — a high-volume internal table that appears in no URL.
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

    #: What is physically on the shelf
    quantity_physical = models.PositiveIntegerField(_("الكمية الفعلية"), default=0)
    #: Reserved for orders not yet shipped
    quantity_reserved = models.PositiveIntegerField(_("المحجوز"), default=0)
    #: Damaged — present and not for sale
    quantity_damaged = models.PositiveIntegerField(_("التالف"), default=0)
    #: Expired — present and not for sale
    quantity_expired = models.PositiveIntegerField(_("المنتهي"), default=0)

    # ── Alert thresholds ───────────────────────────────────
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
            # ⚠️  A negative balance is impossible — the final guard
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
        Available for sale.

        Physical − reserved − damaged − expired.
        This is the only number that matters when selling.
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
#  Stock movements
# ═══════════════════════════════════════════════════════════


class MovementType(models.TextChoices):
    """
    ⚠️  Every change in stock leaves a movement. Without exception.

        The log is what answers "where did the fifty boxes go?" — and without
        it no stock count can be reconciled and no discrepancy explained.
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


#: The movements that increase the physical quantity
INBOUND = {
    MovementType.RECEIPT,
    MovementType.RETURN_IN,
    MovementType.TRANSFER_IN,
    MovementType.ADJUSTMENT_UP,
}

#: The movements that decrease the physical quantity
OUTBOUND = {
    MovementType.SALE,
    MovementType.RETURN_OUT,
    MovementType.TRANSFER_OUT,
    MovementType.ADJUSTMENT_DOWN,
}


class StockMovement(models.Model):
    """
    A movement entry. **Append-only** — no editing and no deleting.

    Corrections go through an offsetting movement rather than editing the old
    one, or the log the stock count and the financial reports are built on
    becomes corrupt.

    A BigInt key — the largest table in the system, and it appears in no URL.
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

    #: A snapshot of the balance after the movement — it allows reviewing the log without recomputing
    balance_after = models.IntegerField(_("الرصيد بعد الحركة"), default=0)

    unit_cost = MoneyField(
        _("تكلفة الوحدة"),
        null=True,
        blank=True,
        help_text=_("لقطة وقت الحركة — تُستخدم في حساب COGS"),
    )

    #: An external string reference — **no FK to `orders`**.
    #: `inventory` is in L3 and `orders` in L6; a foreign key here
    #: makes the direction upward and breaks the boundaries.
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
        # ⚠️  `-id` is a mandatory secondary sort key.
        #
        #     Two movements recorded in the same microsecond (a sale consuming
        #     two batches, say) leave `-created_at` alone with an unstable
        #     ordering — differing from one query to the next. And in a log that
        #     the stock count and cost calculation are built on, unstable ordering is a defect, not a nuisance.
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
#  Reservations
# ═══════════════════════════════════════════════════════════


class ReservationStatus(models.TextChoices):
    ACTIVE = "ACTIVE", _("نشط")
    COMMITTED = "COMMITTED", _("مُنفَّذ")
    RELEASED = "RELEASED", _("مُفرَج عنه")
    EXPIRED = "EXPIRED", _("منتهٍ")


class StockReservation(BaseModel):
    """
    A temporary reservation.

    ⚠️  A reservation **expires on a timeout**.

        An abandoned cart holding stock forever means a product that looks out
        of stock while it is available. The timeout releases it automatically.
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

    # A string reference — no upward FK to orders/cart
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
#  Stock counting
# ═══════════════════════════════════════════════════════════


class StockCountStatus(models.TextChoices):
    DRAFT = "DRAFT", _("مسودة")
    IN_PROGRESS = "IN_PROGRESS", _("جارٍ")
    COMPLETED = "COMPLETED", _("مكتمل")
    CANCELLED = "CANCELLED", _("ملغى")


class StockCount(BaseModel):
    """A stock count session."""

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
    A stock count line.

    The discrepancy is computed and never entered — entering it by hand allows a
    shortfall to be hidden.
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
        """Positive = surplus · negative = shortfall."""
        return self.counted_quantity - self.expected_quantity


# ═══════════════════════════════════════════════════════════
#  Alerts
# ═══════════════════════════════════════════════════════════


class AlertType(models.TextChoices):
    LOW_STOCK = "LOW_STOCK", _("مخزون منخفض")
    CRITICAL_STOCK = "CRITICAL_STOCK", _("مخزون حرج")
    OUT_OF_STOCK = "OUT_OF_STOCK", _("نفاد")
    EXPIRING_SOON = "EXPIRING_SOON", _("قرب انتهاء صلاحية")
    EXPIRED = "EXPIRED", _("انتهت الصلاحية")


class StockAlert(BaseModel):
    """
    A stock alert.

    ⚠️  **Deduplication is mandatory.**

        An out-of-stock product generates an alert on every attempted sale —
        dozens of alerts for the same situation within an hour. The unique
        constraint on (type · product · location) conditioned on
        `is_resolved=False` keeps it to one alert until it is settled.
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
