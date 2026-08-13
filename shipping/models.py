"""
الشحن — العناوين والمناطق والرسوم والشحنات.

⚠️  هذا النطاق يستقبل `Address` و`DeliveryFee` من النموذج القديم.

    `Address` كان في `accounts` و`orders` يستورده — وهو نصف
    التبعية الدائرية H1. نقله هنا يكسرها: `shipping` في L2 تحت
    `orders` في L6، فالاتجاه نازل.
"""

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.identifiers import business_number
from core.models.base import BaseModel
from core.models.translatable import BilingualNameMixin
from core.money import MoneyField


def shipment_number() -> str:
    return business_number("SHP", random_length=6)


# ═══════════════════════════════════════════════════════════
#  المناطق والطرق
# ═══════════════════════════════════════════════════════════


class ShippingZone(BilingualNameMixin, BaseModel):
    """
    منطقة شحن — مجموعة محافظات برسوم موحّدة.

    المحافظات في `JSONField` لا جدول منفصل: القائمة ثابتة ومحدودة
    (٢٧ محافظة)، وجدول لها يعني وصلة إضافية في كل حساب رسوم.
    """

    code = models.SlugField(_("الرمز"), max_length=50, unique=True)
    governorates = models.JSONField(
        _("المحافظات"), default=list, help_text=_("أسماء المحافظات المشمولة")
    )

    is_default = models.BooleanField(
        _("الافتراضية"),
        default=False,
        help_text=_("تُستخدم لأي محافظة غير مُسندة"),
    )
    is_active = models.BooleanField(_("مفعّلة"), default=True, db_index=True)

    class Meta:
        verbose_name = _("منطقة شحن")
        verbose_name_plural = _("مناطق الشحن")
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=models.Q(is_default=True, deleted_at__isnull=True),
                name="unique_default_shipping_zone",
            ),
        ]

    def __str__(self):
        return f"{self.code} · {self.name_ar}"

    @classmethod
    def for_governorate(cls, governorate: str) -> "ShippingZone | None":
        """المنطقة التي تشمل هذه المحافظة، أو الافتراضية."""
        for zone in cls.objects.filter(is_active=True):
            if governorate in (zone.governorates or []):
                return zone
        return cls.objects.filter(is_default=True, is_active=True).first()


class ShippingMethod(BilingualNameMixin, BaseModel):
    """طريقة شحن — عادي · سريع · استلام من الفرع."""

    code = models.SlugField(_("الرمز"), max_length=50, unique=True)
    description_ar = models.TextField(_("الوصف بالعربية"), blank=True)
    description_en = models.TextField(_("الوصف بالإنجليزية"), blank=True)

    estimated_days_min = models.PositiveSmallIntegerField(_("أقل مدة بالأيام"), default=1)
    estimated_days_max = models.PositiveSmallIntegerField(_("أكثر مدة بالأيام"), default=3)

    is_pickup = models.BooleanField(
        _("استلام من الفرع"),
        default=False,
        help_text=_("بلا رسوم شحن وبلا عنوان"),
    )
    display_order = models.PositiveIntegerField(_("الترتيب"), default=0)
    is_active = models.BooleanField(_("مفعّلة"), default=True, db_index=True)

    class Meta:
        verbose_name = _("طريقة شحن")
        verbose_name_plural = _("طرق الشحن")
        ordering = ["display_order", "code"]

    def __str__(self):
        return self.name_ar


class ShippingRate(BaseModel):
    """
    رسوم منطقة × طريقة.

    ⚠️  `free_above` **لكل صف** لا إعداد عام.

        «شحن مجاني فوق ٥٠٠» في القاهرة قد لا يصلح للصعيد حيث
        التكلفة الفعلية أعلى. الإعداد العام يفرض سقفًا واحدًا على
        اقتصاديات مختلفة.
    """

    zone = models.ForeignKey(ShippingZone, on_delete=models.CASCADE, related_name="rates")
    method = models.ForeignKey(ShippingMethod, on_delete=models.CASCADE, related_name="rates")

    base_fee = MoneyField(_("الرسوم الأساسية"), validators=[MinValueValidator(0)])
    free_above = MoneyField(
        _("مجاني فوق"),
        null=True,
        blank=True,
        help_text=_("فارغ = لا شحن مجاني لهذه المنطقة"),
    )
    per_kg_fee = MoneyField(_("رسوم الكيلوجرام"), default=0, help_text=_("صفر = لا رسوم وزن"))
    is_active = models.BooleanField(_("مفعّلة"), default=True, db_index=True)

    class Meta:
        verbose_name = _("تعريفة شحن")
        verbose_name_plural = _("تعريفات الشحن")
        constraints = [
            models.UniqueConstraint(
                fields=["zone", "method"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_rate_per_zone_method",
            ),
        ]

    def __str__(self):
        return f"{self.zone.code} × {self.method.code} = {self.base_fee}"


# ═══════════════════════════════════════════════════════════
#  الشحنات
# ═══════════════════════════════════════════════════════════


class ShipmentStatus(models.TextChoices):
    PENDING = "PENDING", _("قيد التجهيز")
    PICKED = "PICKED", _("تم التجميع")
    IN_TRANSIT = "IN_TRANSIT", _("في الطريق")
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY", _("خرجت للتسليم")
    DELIVERED = "DELIVERED", _("سُلّمت")
    FAILED = "FAILED", _("فشل التسليم")
    RETURNED = "RETURNED", _("مرتجعة")


class Shipment(BaseModel):
    """
    شحنة.

    ⚠️  المرجع إلى الطلب **نصي**. `shipping` في L2 و`orders` في L6؛
        المفتاح الأجنبي هنا يجعل الاتجاه صاعدًا ويكسر الحدود.
    """

    number = models.CharField(_("رقم الشحنة"), max_length=32, unique=True, default=shipment_number)

    reference_type = models.CharField(_("نوع المرجع"), max_length=32, blank=True)
    reference_id = models.CharField(_("معرّف المرجع"), max_length=64, blank=True, db_index=True)

    method = models.ForeignKey(ShippingMethod, on_delete=models.PROTECT, related_name="shipments")
    zone = models.ForeignKey(
        ShippingZone,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="shipments",
    )

    status = models.CharField(
        _("الحالة"),
        max_length=20,
        choices=ShipmentStatus.choices,
        default=ShipmentStatus.PENDING,
        db_index=True,
    )

    # ── لقطة العنوان ───────────────────────────────────────
    # ⚠️  منسوخة لا مرجعية: العميل قد يعدّل عنوانه بعد الشحن،
    #     ولقطة وقت الشحن هي ما يُدافَع عنه في أي نزاع.
    recipient_name = models.CharField(_("اسم المستلم"), max_length=200)
    recipient_phone = models.CharField(_("هاتف المستلم"), max_length=20)
    governorate = models.CharField(_("المحافظة"), max_length=100)
    city = models.CharField(_("المدينة"), max_length=100)
    street = models.TextField(_("العنوان"))
    building = models.CharField(_("رقم العقار"), max_length=50, blank=True)
    landmark = models.CharField(_("علامة مميزة"), max_length=200, blank=True)

    shipping_fee = MoneyField(_("رسوم الشحن"), default=0)
    weight_grams = models.PositiveIntegerField(_("الوزن"), default=0)

    carrier = models.CharField(_("شركة الشحن"), max_length=100, blank=True)
    tracking_number = models.CharField(_("رقم التتبع"), max_length=100, blank=True, db_index=True)

    shipped_at = models.DateTimeField(_("تاريخ الشحن"), null=True, blank=True)
    delivered_at = models.DateTimeField(_("تاريخ التسليم"), null=True, blank=True)
    failure_reason = models.TextField(_("سبب الفشل"), blank=True)

    class Meta:
        verbose_name = _("شحنة")
        verbose_name_plural = _("الشحنات")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["reference_type", "reference_id"]),
        ]

    def __str__(self):
        return f"{self.number} [{self.status}]"


class ShipmentEvent(models.Model):
    """
    حدث تتبع. **إضافة فقط.**

    مفتاح BigInt — سجل داخلي لا يظهر في رابط.
    """

    shipment = models.ForeignKey(Shipment, on_delete=models.CASCADE, related_name="events")
    status = models.CharField(_("الحالة"), max_length=20, choices=ShipmentStatus.choices)
    note = models.TextField(_("ملاحظة"), blank=True)
    location = models.CharField(_("الموقع"), max_length=200, blank=True)
    created_at = models.DateTimeField(_("الوقت"), auto_now_add=True)

    class Meta:
        verbose_name = _("حدث شحنة")
        verbose_name_plural = _("أحداث الشحنات")
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.shipment.number} → {self.status}"
