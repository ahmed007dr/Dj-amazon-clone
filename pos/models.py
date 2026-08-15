"""
نقطة البيع.

⚠️  **POS قناة بيع لا نظام موازٍ.**

    كل بيعة تُنتج `Order` بـ `channel=POS`. النموذج الموازي
    (`POSOrder`) يعني تقريرَي مبيعات ومخزونين ومصدرَي حقيقة —
    وأول سؤال محاسبي يكشف الفجوة بينهما بلا طريقة لحسمها.

    ولذلك **لا موديل طلب هنا**: الموديلات أدناه تصف الوردية
    والصندوق والجهاز فقط، وهي أشياء لا يعرفها نطاق الطلبات.

⚠️  والوردية المغلقة **لا تُعدَّل**.

    التصحيح بقيد جديد لا بتحرير القديم. الوردية سجل مالي يُبنى
    عليه الجرد النقدي، وتحريرها بعد الإغلاق يجعل كل تسوية سابقة
    غير جديرة بالثقة.
"""

from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.identifiers import business_number
from core.models.base import BaseModel, TimeStampedModel
from core.models.translatable import BilingualNameMixin
from core.money import MoneyField


def session_number() -> str:
    return business_number("SES", random_length=6)


def register_code() -> str:
    return business_number("REG", random_length=4)


# ═══════════════════════════════════════════════════════════
#  الجهاز
# ═══════════════════════════════════════════════════════════


class Register(BilingualNameMixin, BaseModel):
    """
    جهاز نقطة بيع مربوط بموقع مخزني.

    ⚠️  الربط بالموقع **إلزامي وغير قابل للتغيير عمليًا**.

        الجهاز يبيع من مخزون فرعه لا من مخزون عام. تغييره بعد
        بيعات مسجَّلة يجعل حركات المخزون تشير إلى موقع لم تقع فيه،
        فينكسر جرد الفرعين معًا.
    """

    code = models.SlugField(_("رمز الجهاز"), max_length=50, unique=True, default=register_code)

    location = models.ForeignKey(
        "inventory.StockLocation",
        on_delete=models.PROTECT,
        related_name="registers",
        verbose_name=_("الموقع المخزني"),
        help_text=_("الجهاز يبيع من مخزون هذا الموقع وحده"),
    )

    is_active = models.BooleanField(_("مفعّل"), default=True, db_index=True)

    class Meta:
        verbose_name = _("جهاز نقطة بيع")
        verbose_name_plural = _("أجهزة نقطة البيع")
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} · {self.name_ar}"

    @property
    def open_session(self) -> "POSSession | None":
        return self.sessions.filter(status=SessionStatus.OPEN).first()


# ═══════════════════════════════════════════════════════════
#  الوردية
# ═══════════════════════════════════════════════════════════


class SessionStatus(models.TextChoices):
    OPEN = "OPEN", _("مفتوحة")
    CLOSED = "CLOSED", _("مغلقة")


class POSSession(BaseModel):
    """
    وردية كاشير.

    ⚠️  **وردية مفتوحة واحدة لكل جهاز.**

        جهاز بورديتين مفتوحتين يعني بيعات تُنسب لأيّهما شاء
        الاستعلام، وتسوية نقدية لا تُوازن أبدًا. يفرضه قيد فريد.

    ⚠️  و`expected_cash` **محسوب لا مُدخَل**.

        الرصيد الافتتاحي + المقبوض نقدًا − المصروف نقدًا. تركه
        للكاشير يجعل الفرق صفرًا دائمًا — أي يلغي الغرض من التسوية.
    """

    number = models.CharField(
        _("رقم الوردية"), max_length=32, unique=True, default=session_number, db_index=True
    )

    register = models.ForeignKey(
        Register, on_delete=models.PROTECT, related_name="sessions", verbose_name=_("الجهاز")
    )
    cashier = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="pos_sessions",
        verbose_name=_("الكاشير"),
    )

    status = models.CharField(
        _("الحالة"),
        max_length=8,
        choices=SessionStatus.choices,
        default=SessionStatus.OPEN,
        db_index=True,
    )

    opened_at = models.DateTimeField(_("فُتحت في"), default=timezone.now)
    closed_at = models.DateTimeField(_("أُغلقت في"), null=True, blank=True)

    closed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("أغلقها"),
        help_text=_("قد يكون مديرًا لا الكاشير نفسه"),
    )

    # ── النقد ──────────────────────────────────────────────
    opening_float = MoneyField(
        _("الرصيد الافتتاحي"),
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("النقد في الدرج عند فتح الوردية"),
    )

    counted_cash = MoneyField(
        _("النقد المعدود"),
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("ما عدّه الكاشير فعليًا عند الإغلاق"),
    )

    #: ⚠️  لقطة محسوبة وقت الإغلاق — لا تُعاد من الحركات لاحقًا،
    #:     لأن حركة تُضاف بأثر رجعي كانت ستغيّر فرقًا مُسوّى.
    expected_cash = MoneyField(_("النقد المتوقَّع"), null=True, blank=True)

    variance_note = models.TextField(
        _("تفسير الفرق"),
        blank=True,
        help_text=_("إلزامي حين يتجاوز الفرق الحد المضبوط"),
    )

    note = models.TextField(_("ملاحظة"), blank=True)

    class Meta:
        verbose_name = _("وردية")
        verbose_name_plural = _("الورديات")
        ordering = ["-opened_at"]
        constraints = [
            # ⚠️  وردية مفتوحة واحدة لكل جهاز — الحارس الحقيقي
            models.UniqueConstraint(
                fields=["register"],
                condition=models.Q(status="OPEN", deleted_at__isnull=True),
                name="one_open_session_per_register",
            ),
        ]
        indexes = [
            models.Index(fields=["cashier", "-opened_at"]),
            models.Index(fields=["status", "-opened_at"]),
        ]

    def __str__(self):
        return f"{self.number} · {self.register.code}"

    @property
    def is_open(self) -> bool:
        return self.status == SessionStatus.OPEN

    @property
    def variance(self) -> Decimal | None:
        """
        موجب = زيادة · سالب = عجز.

        ⚠️  `None` قبل الإغلاق — لا صفر.

            الصفر يُقرأ «وازنت»، والوردية المفتوحة لم تُعدّ بعد.
        """
        if self.counted_cash is None or self.expected_cash is None:
            return None
        return self.counted_cash - self.expected_cash


# ═══════════════════════════════════════════════════════════
#  حركة الصندوق
# ═══════════════════════════════════════════════════════════


class CashMovementKind(models.TextChoices):
    """
    ⚠️  كل نقد يدخل الدرج أو يخرج منه يترك حركة. بلا استثناء.

        السجل هو ما يجيب على «من أين جاء الفرق؟» — وبدونه تصير
        التسوية تخمينًا.
    """

    SALE = "SALE", _("بيع نقدي")
    REFUND = "REFUND", _("مرتجع نقدي")
    PAY_IN = "PAY_IN", _("إيداع في الدرج")
    PAY_OUT = "PAY_OUT", _("سحب من الدرج")


#: الحركات التي تزيد النقد
CASH_IN = {CashMovementKind.SALE, CashMovementKind.PAY_IN}


class CashMovement(TimeStampedModel):
    """
    حركة نقدية في درج الوردية. **إضافة فقط.**

    مفتاح BigInt — سجل داخلي عالي الحجم لا يظهر في رابط.
    """

    session = models.ForeignKey(POSSession, on_delete=models.CASCADE, related_name="cash_movements")

    kind = models.CharField(_("النوع"), max_length=8, choices=CashMovementKind.choices)
    amount = MoneyField(_("المبلغ"), validators=[MinValueValidator(Decimal("0"))])

    #: مرجع نصي — **لا FK إلى `orders`**.
    #: `pos` فوق `orders` في المخطط، والمفتاح الأجنبي هنا يقلب الاتجاه.
    reference_type = models.CharField(_("نوع المرجع"), max_length=32, blank=True)
    reference_id = models.CharField(_("معرّف المرجع"), max_length=64, blank=True)

    reason = models.CharField(_("السبب"), max_length=300, blank=True)

    performed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = _("حركة صندوق")
        verbose_name_plural = _("حركات الصندوق")
        # ⚠️  `-id` ثانويًا: حركتان في نفس الميكروثانية تعطيان
        #     ترتيبًا غير مستقر في سجل تُبنى عليه تسوية مالية.
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["session", "-created_at"])]

    def __str__(self):
        return f"{self.kind} · {self.amount}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("حركة الصندوق للإضافة فقط — التصحيح بحركة معاكسة.")
        super().save(*args, **kwargs)

    @property
    def signed_amount(self) -> Decimal:
        return self.amount if self.kind in CASH_IN else -self.amount
