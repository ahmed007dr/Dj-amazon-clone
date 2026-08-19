"""
Notifications.

⚠️  **No domain imports this domain.** (the `notifications-isolated` contract)

    Domains emit signals; this one listens. A direct call would mean `inventory`
    knowing email exists and `orders` knowing the message templates — and every
    change to notifications touching domains that have nothing to do with it.

        inventory detects LOW_STOCK
                ↓  signal
        notifications listens
                ↓
        an in-app notification + email
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models.base import BaseModel


class NotificationChannel(models.TextChoices):
    IN_APP = "IN_APP", _("داخل التطبيق")
    EMAIL = "EMAIL", _("بريد إلكتروني")
    SMS = "SMS", _("رسالة نصية")
    PUSH = "PUSH", _("إشعار فوري")
    WHATSAPP = "WHATSAPP", _("واتساب")


class NotificationCategory(models.TextChoices):
    """
    ⚠️  The category governs the preferences.

        A customer may disable marketing and keep order notifications — with no
        category the choice becomes "all or nothing", so everyone disables everything.
    """

    ACCOUNT = "ACCOUNT", _("الحساب")
    ORDER = "ORDER", _("الطلبات")
    PAYMENT = "PAYMENT", _("الدفع")
    SHIPPING = "SHIPPING", _("الشحن")
    INVENTORY = "INVENTORY", _("المخزون")
    PROMOTION = "PROMOTION", _("العروض")
    MARKETING = "MARKETING", _("التسويق")
    SYSTEM = "SYSTEM", _("النظام")


class NotificationPriority(models.TextChoices):
    LOW = "LOW", _("منخفضة")
    NORMAL = "NORMAL", _("عادية")
    HIGH = "HIGH", _("مرتفعة")
    URGENT = "URGENT", _("عاجلة")


class Notification(BaseModel):
    """
    An in-app notification.

    ⚠️  The text is **copied, not referential**.

        The notification says "your order ORD-2026-7K3M9P has shipped" — and
        that is a snapshot at the time of the event. Generating it later from
        the order gives text that changes as its status changes, so the customer
        reads a falsified history.
    """

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=_("المستخدم"),
    )

    category = models.CharField(
        _("التصنيف"),
        max_length=16,
        choices=NotificationCategory.choices,
        db_index=True,
    )
    priority = models.CharField(
        _("الأولوية"),
        max_length=8,
        choices=NotificationPriority.choices,
        default=NotificationPriority.NORMAL,
    )

    title = models.CharField(_("العنوان"), max_length=200)
    body = models.TextField(_("النص"))

    #: A link inside the frontend — `/account/orders/<uuid>`
    action_url = models.CharField(_("رابط الإجراء"), max_length=500, blank=True)

    #: A string reference — no upward FK to any domain
    reference_type = models.CharField(_("نوع المرجع"), max_length=32, blank=True)
    reference_id = models.CharField(_("معرّف المرجع"), max_length=64, blank=True)

    is_read = models.BooleanField(_("مقروء"), default=False, db_index=True)
    read_at = models.DateTimeField(_("وقت القراءة"), null=True, blank=True)

    class Meta:
        verbose_name = _("إشعار")
        verbose_name_plural = _("الإشعارات")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"]),
            models.Index(fields=["category", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.user} · {self.title}"


class NotificationPreference(BaseModel):
    """
    The user's preferences per category and channel.

    ⚠️  **Account and security notifications cannot be disabled.**

        "Your password was changed" and "your account was suspended" are not
        marketing — disabling them means a compromise passing unnoticed by its
        owner. The rule is enforced in the service, not in the frontend.
    """

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="notification_preferences",
        verbose_name=_("المستخدم"),
    )
    category = models.CharField(_("التصنيف"), max_length=16, choices=NotificationCategory.choices)
    channel = models.CharField(_("القناة"), max_length=16, choices=NotificationChannel.choices)
    is_enabled = models.BooleanField(_("مفعّل"), default=True)

    class Meta:
        verbose_name = _("تفضيل إشعار")
        verbose_name_plural = _("تفضيلات الإشعارات")
        constraints = [
            models.UniqueConstraint(
                fields=["user", "category", "channel"],
                condition=models.Q(deleted_at__isnull=True),
                name="unique_notification_preference",
            ),
        ]

    def __str__(self):
        state = "مفعّل" if self.is_enabled else "موقوف"
        return f"{self.user} · {self.category}/{self.channel} [{state}]"


class DeliveryStatus(models.TextChoices):
    PENDING = "PENDING", _("قيد الإرسال")
    SENT = "SENT", _("أُرسل")
    FAILED = "FAILED", _("فشل")
    SKIPPED = "SKIPPED", _("متخطّى — تفضيل المستخدم")


class NotificationLog(models.Model):
    """
    The delivery attempt log.

    ⚠️  It answers "did the email arrive?" — the first question in any complaint.

    A BigInt key — high volume, and it appears in no URL.
    """

    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="notification_logs"
    )
    channel = models.CharField(_("القناة"), max_length=16, choices=NotificationChannel.choices)
    category = models.CharField(_("التصنيف"), max_length=16, choices=NotificationCategory.choices)
    template_key = models.CharField(_("مفتاح القالب"), max_length=100, blank=True)
    recipient = models.CharField(_("المستلم"), max_length=255, blank=True)

    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=DeliveryStatus.choices,
        default=DeliveryStatus.PENDING,
        db_index=True,
    )
    error_message = models.TextField(_("رسالة الخطأ"), blank=True)
    attempts = models.PositiveSmallIntegerField(_("عدد المحاولات"), default=0)

    created_at = models.DateTimeField(_("الوقت"), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("سجل إشعار")
        verbose_name_plural = _("سجل الإشعارات")
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.user} · {self.channel} [{self.status}]"
