"""
Payments — a gateway registry **configurable from the admin panel**.

⚠️  The explicit requirement: add and enable one or more gateways with no code
    change and no redeployment. (ADR-15)

    The structure:

        orders / pos
             ↓  an abstract interface — neither knows any gateway
        payments.services.charge()
             ↓
        PaymentRouter  ← selects by channel, method, currency and order
             ↓
        Provider adapter
             ↓
        the actual gateway
"""

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.encryption import EncryptedTextField
from core.identifiers import business_number
from core.models.base import BaseModel
from core.models.translatable import BilingualNameMixin
from core.money import CurrencyField, MoneyField


def transaction_reference() -> str:
    return business_number("PAY", random_length=8)


def refund_reference() -> str:
    return business_number("RFD", random_length=8)


class PaymentMethodKind(models.TextChoices):
    CASH_ON_DELIVERY = "COD", _("دفع عند الاستلام")
    CASH = "CASH", _("نقدي")
    CARD = "CARD", _("بطاقة")
    WALLET = "WALLET", _("محفظة إلكترونية")
    BANK_TRANSFER = "BANK", _("تحويل بنكي")
    INSTALLMENT = "INSTALLMENT", _("تقسيط")


class PaymentProvider(BilingualNameMixin, BaseModel):
    """
    A registered payment gateway.

    ⚠️  `adapter_key` points at an adapter in the code; everything else is data
        the admin edits. Adding a gateway = a new adapter + a row here.
    """

    code = models.SlugField(_("الرمز"), max_length=50, unique=True)
    adapter_key = models.CharField(
        _("مفتاح المحوّل"),
        max_length=50,
        help_text=_("اسم المحوّل المسجّل في الكود"),
    )

    supported_methods = models.JSONField(
        _("طرق الدفع المدعومة"), default=list, help_text=_("قائمة من PaymentMethodKind")
    )
    supported_currencies = models.JSONField(
        _("العملات المدعومة"), default=list, help_text=_("فارغ = كل العملات")
    )
    supported_channels = models.JSONField(
        _("القنوات المسموحة"),
        default=list,
        help_text=_("ONLINE · POS · EMPLOYEE — فارغ = الكل"),
    )

    # ── Limits ─────────────────────────────────────────────
    min_amount = MoneyField(_("الحد الأدنى"), default=0)
    max_amount = MoneyField(_("الحد الأقصى"), null=True, blank=True)

    priority = models.IntegerField(_("الأولوية"), default=0, help_text=_("الأعلى يُجرَّب أولًا"))
    is_sandbox = models.BooleanField(_("وضع تجريبي"), default=True)
    is_active = models.BooleanField(_("مفعّلة"), default=False, db_index=True)

    class Meta:
        verbose_name = _("بوابة دفع")
        verbose_name_plural = _("بوابات الدفع")
        ordering = ["-priority", "code"]
        indexes = [models.Index(fields=["is_active", "-priority"])]

    def __str__(self):
        mode = " [تجريبي]" if self.is_sandbox else ""
        return f"{self.name_ar}{mode}"

    def missing_credentials(self) -> list[str]:
        """
        The keys this gateway's adapter needs and does not have, for the mode it is in.

        ⚠️  **Asked of the adapter, never inferred from the row.**

            "It has no credentials stored, so it is unconfigured" is true of
            Paymob and false of cash on delivery — there is no key to give a
            courier. The panel inferred it that way and locked the shop out of
            its own default payment method the first time anyone disabled it.
            See `PaymentAdapter.required_credentials`.

        ⚠️  And per mode: sandbox keys are not production keys.

            A gateway tested in sandbox and then switched to production has
            credentials — the wrong ones. Counting them means enabling a gateway
            that authenticates against an account holding no money.
        """
        from payments.adapters import required_credentials

        required = required_credentials(self.adapter_key)
        if not required:
            return []

        present = set(
            self.credentials.filter(is_sandbox=self.is_sandbox).values_list("key", flat=True)
        )
        return [key for key in required if key not in present]

    def supports(self, *, method: str, currency: str, channel: str, amount) -> bool:
        if self.supported_methods and method not in self.supported_methods:
            return False
        if self.supported_currencies and currency not in self.supported_currencies:
            return False
        if self.supported_channels and channel not in self.supported_channels:
            return False
        if amount < self.min_amount:
            return False
        return not (self.max_amount is not None and amount > self.max_amount)


class ProviderCredential(BaseModel):
    """
    A gateway's credentials.

    ⚠️  **Deliberately separated from `PaymentProvider`.**

        A separate table allows a different read permission: whoever manages the
        gateways is not necessarily whoever holds their secret keys.

    ⚠️  **The value is never returned in any API — not even to the admin.** (ADR-15)

        The field is write-only, and the display shows the last four characters masked.

    ⚠️  **And it is encrypted in the database** with `FIELD_ENCRYPTION_KEY`.

        Withholding the value from the API alone protected one path and left the
        other open: a backup or a SQL leak hands over the keys in full. See
        `core.encryption`.
    """

    provider = models.ForeignKey(
        PaymentProvider,
        on_delete=models.CASCADE,
        related_name="credentials",
        verbose_name=_("البوابة"),
    )
    key = models.CharField(_("المفتاح"), max_length=100)
    value = EncryptedTextField(_("القيمة"), help_text=_("مشفّرة — لا تُقرأ عبر الـ API"))
    is_sandbox = models.BooleanField(_("للوضع التجريبي"), default=True)

    class Meta:
        verbose_name = _("بيانات اعتماد بوابة")
        verbose_name_plural = _("بيانات اعتماد البوابات")
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "key", "is_sandbox"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_provider_credential",
            ),
        ]

    def __str__(self):
        return f"{self.provider.code}.{self.key}"

    @property
    def masked_value(self) -> str:
        """The only representation permitted to be displayed."""
        if len(self.value) <= 4:
            return "••••"
        return f"••••••••{self.value[-4:]}"


class TransactionStatus(models.TextChoices):
    PENDING = "PENDING", _("قيد المعالجة")
    AUTHORIZED = "AUTHORIZED", _("مُصرَّح")
    CAPTURED = "CAPTURED", _("مُحصَّل")
    FAILED = "FAILED", _("فشل")
    CANCELLED = "CANCELLED", _("ملغى")
    REFUNDED = "REFUNDED", _("مسترد")


class PaymentTransaction(BaseModel):
    """
    A payment transaction.

    ⚠️  The reference to the order is **a string** — `payments` is in L7 and
        `orders` in L6, but a direct dependency would make the order know a
        specific gateway. A string reference keeps `payments` independent and
        extractable later.
    """

    reference = models.CharField(
        _("المرجع"),
        max_length=32,
        unique=True,
        default=transaction_reference,
        db_index=True,
    )

    provider = models.ForeignKey(
        PaymentProvider,
        on_delete=models.PROTECT,
        related_name="transactions",
        verbose_name=_("البوابة"),
    )
    method = models.CharField(_("طريقة الدفع"), max_length=16, choices=PaymentMethodKind.choices)

    reference_type = models.CharField(_("نوع المرجع"), max_length=32, blank=True)
    reference_id = models.CharField(_("معرّف المرجع"), max_length=64, blank=True, db_index=True)

    customer = models.ForeignKey(
        "customers.CustomerProfile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payment_transactions",
    )

    amount = MoneyField(_("المبلغ"), validators=[MinValueValidator(0)])
    currency = CurrencyField()

    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=TransactionStatus.choices,
        default=TransactionStatus.PENDING,
        db_index=True,
    )

    provider_reference = models.CharField(
        _("مرجع البوابة"), max_length=200, blank=True, db_index=True
    )
    #: ⚠️  It may contain sensitive data — never returned in any API
    provider_response = models.JSONField(_("استجابة البوابة"), default=dict, blank=True)

    failure_code = models.CharField(_("كود الفشل"), max_length=100, blank=True)
    failure_message = models.TextField(_("رسالة الفشل"), blank=True)

    #: Prevents the operation repeating on a double-click or a retry
    idempotency_key = models.CharField(
        _("مفتاح المنع التكراري"),
        max_length=64,
        blank=True,
        db_index=True,
    )

    authorized_at = models.DateTimeField(_("وقت التصريح"), null=True, blank=True)
    captured_at = models.DateTimeField(_("وقت التحصيل"), null=True, blank=True)

    class Meta:
        verbose_name = _("معاملة دفع")
        verbose_name_plural = _("معاملات الدفع")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=models.Q(idempotency_key__gt="", deleted_at__isnull=True),
                name="unique_idempotency_key",
            ),
        ]
        indexes = [
            models.Index(fields=["reference_type", "reference_id"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["provider", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.reference} · {self.amount} [{self.status}]"

    @property
    def is_successful(self) -> bool:
        return self.status in (
            TransactionStatus.AUTHORIZED,
            TransactionStatus.CAPTURED,
        )

    @property
    def refunded_amount(self):
        from django.db.models import Sum

        total = self.refunds.filter(status=RefundStatus.COMPLETED).aggregate(total=Sum("amount"))[
            "total"
        ]
        return total or 0

    @property
    def refundable_amount(self):
        return self.amount - self.refunded_amount


class RefundStatus(models.TextChoices):
    PENDING = "PENDING", _("قيد المعالجة")
    COMPLETED = "COMPLETED", _("مكتمل")
    FAILED = "FAILED", _("فشل")


class Refund(BaseModel):
    """
    A refund — full or partial.

    ⚠️  Tied to the original transaction, not to the order.

        An order may be paid by two transactions (a split payment); the refund
        goes back to the source the money came from, not to the order in the abstract.
    """

    reference = models.CharField(_("المرجع"), max_length=32, unique=True, default=refund_reference)
    transaction = models.ForeignKey(
        PaymentTransaction,
        on_delete=models.PROTECT,
        related_name="refunds",
        verbose_name=_("المعاملة الأصلية"),
    )

    amount = MoneyField(_("المبلغ"), validators=[MinValueValidator(0)])
    reason = models.TextField(_("السبب"))

    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=RefundStatus.choices,
        default=RefundStatus.PENDING,
        db_index=True,
    )

    provider_reference = models.CharField(_("مرجع البوابة"), max_length=200, blank=True)
    requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    completed_at = models.DateTimeField(_("وقت الإكمال"), null=True, blank=True)

    class Meta:
        verbose_name = _("استرداد")
        verbose_name_plural = _("الاستردادات")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} · {self.amount}"


class WebhookEvent(models.Model):
    """
    An inbound event from a gateway.

    ⚠️  **Recorded before it is processed.**

        The gateway resends the event when no response arrives. Without a
        record, the order is marked paid twice — and with a refund the amount is
        doubled.

    A BigInt key — high volume, and it appears in no URL.
    """

    provider = models.ForeignKey(
        PaymentProvider, on_delete=models.CASCADE, related_name="webhook_events"
    )
    event_id = models.CharField(
        _("معرّف الحدث"),
        max_length=200,
        db_index=True,
        help_text=_("من البوابة — يمنع المعالجة المكررة"),
    )
    event_type = models.CharField(_("نوع الحدث"), max_length=100)
    payload = models.JSONField(_("الحمولة"), default=dict)

    signature_valid = models.BooleanField(_("التوقيع صالح"), default=False)
    is_processed = models.BooleanField(_("عولج"), default=False, db_index=True)
    processed_at = models.DateTimeField(_("وقت المعالجة"), null=True, blank=True)
    processing_error = models.TextField(_("خطأ المعالجة"), blank=True)

    created_at = models.DateTimeField(_("وقت الاستقبال"), auto_now_add=True)

    class Meta:
        verbose_name = _("حدث بوابة")
        verbose_name_plural = _("أحداث البوابات")
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["provider", "event_id"], name="unique_webhook_event"),
        ]

    def __str__(self):
        return f"{self.provider.code} · {self.event_type}"
