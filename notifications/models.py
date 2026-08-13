"""
الإشعارات.

⚠️  **لا نطاق يستورد هذا النطاق.** (عقد `notifications-isolated`)

    النطاقات تبعث إشارات؛ وهذا يستمع. الاستدعاء المباشر يعني أن
    `inventory` يعرف بوجود البريد، و`orders` يعرف قوالب الرسائل —
    وكل تغيير في الإشعارات يمس نطاقات لا علاقة لها به.

        inventory يكتشف LOW_STOCK
                ↓  إشارة
        notifications يستمع
                ↓
        إشعار داخل التطبيق + بريد
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
    ⚠️  التصنيف يحكم التفضيلات.

        العميل قد يوقف التسويق ويبقي إشعارات الطلبات — بلا تصنيف
        يصير الخيار «الكل أو لا شيء»، فيوقف الجميع كل شيء.
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
    إشعار داخل التطبيق.

    ⚠️  النص **منسوخ لا مرجعي**.

        الإشعار يقول «شُحن طلبك ORD-2026-7K3M9P» — وهذه لقطة وقت
        الحدث. توليدها لاحقًا من الطلب يعطي نصًا يتغيّر مع تغيّر
        حالته، فيقرأ العميل تاريخًا مزوّرًا.
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

    #: رابط داخل الواجهة — `/account/orders/<uuid>`
    action_url = models.CharField(_("رابط الإجراء"), max_length=500, blank=True)

    #: مرجع نصي — لا FK صاعد إلى أي نطاق
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
    تفضيلات المستخدم لكل تصنيف وقناة.

    ⚠️  **إشعارات الحساب والأمان لا تُوقَف.**

        «غُيّرت كلمة مرورك» و«أُوقف حسابك» ليست تسويقًا — إيقافها
        يعني اختراقًا يمر بلا علم صاحبه. القاعدة مفروضة في الخدمة
        لا في الواجهة.
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
    سجل محاولات الإرسال.

    ⚠️  يجيب على «هل وصل البريد؟» — وهو أول سؤال في أي شكوى.

    مفتاح BigInt — حجم كبير ولا يظهر في رابط.
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
