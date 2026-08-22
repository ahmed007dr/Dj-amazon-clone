"""
The notification engine.

⚠️  One entry point: `notify()`.

    It decides the channels from the category and the user's preference, sends,
    and records. Calling any channel directly bypasses both the preferences and
    the log.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from mailing import services as mail_services
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

#: ⚠️  Categories that **cannot be disabled**.
#:
#:     "Your password was changed" and "your account was suspended" are not
#:     marketing — disabling them means a compromise passing unnoticed by its owner.
MANDATORY_CATEGORIES = {
    NotificationCategory.ACCOUNT,
    NotificationCategory.SYSTEM,
}

#: The default channels per category
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
    Is this channel enabled for this category?

    ⚠️  Mandatory categories override the preference — there is no choice in them.
    """
    if category in MANDATORY_CATEGORIES:
        return True

    preference = NotificationPreference.objects.filter(
        user=user, category=category, channel=channel
    ).first()

    # Absence means acceptance — the default is enabled
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
    Send a notification through the appropriate channels.

    ⚠️  A failure in one channel **does not stop the rest**.

        A failing email must not prevent the in-app notification — and the
        customer sees the news one way or another.
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
                # With no template there is no email — the in-app notification is enough
                skipped.append(channel)
                continue

            # ⚠️  **`PENDING`, not `SENT`** — the mail is enqueued in the
            #     `mailing` queue and delivered after the transaction commits.
            #
            #     Recording it as "sent" at enqueue time made the log answer
            #     "yes, it arrived" about a message that had not left yet — and that
            #     is the first question in every complaint, where the worst answer is a confident
            #     wrong one.
            #     The delivery outcome is known from the outbox row.
            queued = mail_services.send_to_user(template_key, user, context)
            sent.append(channel) if queued else skipped.append(channel)
            _log(
                user,
                channel,
                category,
                template_key,
                DeliveryStatus.PENDING if queued else DeliveryStatus.FAILED,
                recipient=user.email,
            )

        else:
            # SMS · PUSH · WHATSAPP — the structure is ready, the channels come later
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
#  Reading
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
    Set a preference.

    ⚠️  An attempt to disable a mandatory category is refused explicitly rather
        than accepted and then ignored. Silent acceptance gives the user the
        false impression that they disabled it.
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
