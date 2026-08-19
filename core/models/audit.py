"""
The audit log.

It answers the admin's question: **"what was this user's last action?"**

A BigInt key rather than a UUID — a large internal table that appears in no URL. (ADR-28)
"""

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _


class AuditAction(models.TextChoices):
    CREATE = "CREATE", _("إنشاء")
    UPDATE = "UPDATE", _("تعديل")
    DELETE = "DELETE", _("حذف")
    RESTORE = "RESTORE", _("استرجاع")
    LOGIN = "LOGIN", _("تسجيل دخول")
    LOGOUT = "LOGOUT", _("تسجيل خروج")
    LOGIN_FAILED = "LOGIN_FAILED", _("محاولة دخول فاشلة")
    SUSPEND = "SUSPEND", _("إيقاف حساب")
    ACTIVATE = "ACTIVATE", _("تفعيل حساب")
    APPROVE = "APPROVE", _("اعتماد")
    REJECT = "REJECT", _("رفض")
    PRICE_CHANGE = "PRICE_CHANGE", _("تغيير سعر")
    STOCK_CHANGE = "STOCK_CHANGE", _("تغيير مخزون")
    PERMISSION_CHANGE = "PERMISSION_CHANGE", _("تغيير صلاحيات")
    SETTING_CHANGE = "SETTING_CHANGE", _("تغيير إعداد")
    REFUND = "REFUND", _("استرداد")
    EXPORT = "EXPORT", _("تصدير بيانات")


class AuditLog(models.Model):
    """
    A single audit entry. **Append-only** — no editing and no deleting.
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name=_("المنفّذ"),
    )
    action = models.CharField(_("الإجراء"), max_length=32, choices=AuditAction.choices)

    content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    # Text, so it can hold both a UUID and a BigInt
    object_id = models.CharField(_("معرّف الكائن"), max_length=64, null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    # A textual snapshot — it stays readable after the object is deleted
    object_repr = models.CharField(_("وصف الكائن"), max_length=200, blank=True)

    changes = models.JSONField(
        _("التغييرات"),
        default=dict,
        blank=True,
        help_text=_('{"field": {"old": ..., "new": ...}}'),
    )

    ip_address = models.GenericIPAddressField(_("عنوان IP"), null=True, blank=True)
    user_agent = models.TextField(_("المتصفح"), blank=True)

    created_at = models.DateTimeField(_("الوقت"), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("قيد تدقيق")
        verbose_name_plural = _("سجل التدقيق")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["actor", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.actor or 'system'} · {self.action} · {self.object_repr}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValueError("سجل التدقيق للإضافة فقط — لا يُعدَّل.")
        super().save(*args, **kwargs)
