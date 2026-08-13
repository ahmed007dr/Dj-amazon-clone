"""
محرك الإشعارات.

⚠️  نقطة دخول واحدة: `notify()`.

    تقرر القنوات حسب التصنيف وتفضيل المستخدم، وترسل، وتسجّل.
    الاستدعاء المباشر لأي قناة يتجاوز التفضيلات والسجل معًا.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from core import mail
from notifications.models import (
    DeliveryStatus,
    Notification,
    NotificationCategory,
    NotificationChannel,
    NotificationLog,
    NotificationPreference,
    NotificationPriority,
)

logger = logging.getLogger(__name__)

#: ⚠️  تصنيفات **لا تُوقَف**.
#:
#:     «غُيّرت كلمة مرورك» و«أُوقف حسابك» ليست تسويقًا — إيقافها
#:     يعني اختراقًا يمر بلا علم صاحبه.
MANDATORY_CATEGORIES = {
    NotificationCategory.ACCOUNT,
    NotificationCategory.SYSTEM,
}

#: القنوات الافتراضية لكل تصنيف
DEFAULT_CHANNELS = {
    NotificationCategory.ACCOUNT: (NotificationChannel.IN_APP, NotificationChannel.EMAIL),
    NotificationCategory.ORDER: (NotificationChannel.IN_APP, NotificationChannel.EMAIL),
    NotificationCategory.PAYMENT: (NotificationChannel.IN_APP, NotificationChannel.EMAIL),
    NotificationCategory.SHIPPING: (NotificationChannel.IN_APP, NotificationChannel.EMAIL),
    NotificationCategory.INVENTORY: (NotificationChannel.IN_APP,),
    NotificationCategory.PROMOTION: (NotificationChannel.IN_APP,),
    NotificationCategory.MARKETING: (NotificationChannel.EMAIL,),
    NotificationCategory.SYSTEM: (NotificationChannel.IN_APP,),
}


@dataclass(frozen=True)
class NotificationResult:
    notification: Notification | None
    channels_sent: tuple
    channels_skipped: tuple


def is_enabled(user, category: str, channel: str) -> bool:
    """
    هل هذه القناة مفعّلة لهذا التصنيف؟

    ⚠️  التصنيفات الإلزامية تتجاوز التفضيل — لا خيار فيها.
    """
    if category in MANDATORY_CATEGORIES:
        return True

    preference = NotificationPreference.objects.filter(
        user=user, category=category, channel=channel
    ).first()

    # الغياب يعني القبول — الافتراضي مفعّل
    return preference.is_enabled if preference is not None else True


@transaction.atomic
def notify(
    user,
    *,
    category: str,
    title: str,
    body: str,
    template_key: str = "",
    template_context: dict | None = None,
    action_url: str = "",
    reference_type: str = "",
    reference_id: str = "",
    priority: str = NotificationPriority.NORMAL,
    channels: tuple | None = None,
) -> NotificationResult:
    """
    إرسال إشعار عبر القنوات المناسبة.

    ⚠️  فشل قناة **لا يوقف الباقي**.

        بريد يفشل يجب ألا يمنع الإشعار داخل التطبيق — والعميل
        يرى الخبر بطريقة ما.
    """
    channels = channels or DEFAULT_CHANNELS.get(category, (NotificationChannel.IN_APP,))
    context = template_context or {}

    sent, skipped = [], []
    notification = None

    for channel in channels:
        if not is_enabled(user, category, channel):
            skipped.append(channel)
            _log(user, channel, category, template_key, DeliveryStatus.SKIPPED)
            continue

        if channel == NotificationChannel.IN_APP:
            notification = Notification.objects.create(
                user=user,
                category=category,
                priority=priority,
                title=title,
                body=body,
                action_url=action_url,
                reference_type=reference_type,
                reference_id=str(reference_id) if reference_id else "",
            )
            sent.append(channel)
            _log(user, channel, category, template_key, DeliveryStatus.SENT)

        elif channel == NotificationChannel.EMAIL:
            if not template_key:
                # بلا قالب لا بريد — الإشعار داخل التطبيق يكفي
                skipped.append(channel)
                continue

            delivered = mail.send_to_user(template_key, user, context)
            sent.append(channel) if delivered else skipped.append(channel)
            _log(
                user,
                channel,
                category,
                template_key,
                DeliveryStatus.SENT if delivered else DeliveryStatus.FAILED,
                recipient=user.email,
            )

        else:
            # SMS · PUSH · WHATSAPP — البنية جاهزة، القنوات لاحقًا
            skipped.append(channel)
            _log(user, channel, category, template_key, DeliveryStatus.SKIPPED)

    return NotificationResult(
        notification=notification,
        channels_sent=tuple(sent),
        channels_skipped=tuple(skipped),
    )


def _log(user, channel, category, template_key, status, *, recipient="", error=""):
    NotificationLog.objects.create(
        user=user,
        channel=channel,
        category=category,
        template_key=template_key,
        recipient=recipient,
        status=status,
        error_message=error,
        attempts=1,
    )


# ═══════════════════════════════════════════════════════════
#  القراءة
# ═══════════════════════════════════════════════════════════


def unread_count(user) -> int:
    return Notification.objects.filter(user=user, is_read=False).count()


def mark_read(notification: Notification) -> Notification:
    if notification.is_read:
        return notification

    notification.is_read = True
    notification.read_at = timezone.now()
    notification.save(update_fields=["is_read", "read_at"])
    return notification


def mark_all_read(user) -> int:
    return Notification.objects.filter(user=user, is_read=False).update(
        is_read=True, read_at=timezone.now()
    )


@transaction.atomic
def set_preference(user, category: str, channel: str, *, enabled: bool) -> NotificationPreference:
    """
    ضبط تفضيل.

    ⚠️  محاولة إيقاف تصنيف إلزامي تُرفض صراحةً لا تُقبل ثم تُتجاهَل.
        القبول الصامت يعطي المستخدم انطباعًا خاطئًا بأنه أوقفها.
    """
    from core.errors import BusinessError, ErrorCode

    if category in MANDATORY_CATEGORIES and not enabled:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            detail="إشعارات الحساب والأمان لا يمكن إيقافها",
        )

    preference, _created = NotificationPreference.objects.update_or_create(
        user=user, category=category, channel=channel, defaults={"is_enabled": enabled}
    )
    return preference
