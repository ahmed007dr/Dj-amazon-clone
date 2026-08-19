"""
Customer domain services — the only public interface.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from core.models.audit import AuditAction, AuditLog
from customers.models import (
    CustomerAddress,
    CustomerDocument,
    CustomerProfile,
    DocumentStatus,
)


def get_or_create_profile(user) -> CustomerProfile:
    """
    ⚠️  Called on demand rather than by a `post_save` signal on `User`.

    The signal created a profile for every user without exception — including
    administrators and employees. The result was orphan rows and wasted customer
    numbers.
    """
    profile, _created = CustomerProfile.objects.get_or_create(user=user)
    return profile


@transaction.atomic
def set_default_address(address: CustomerAddress) -> CustomerAddress:
    """
    Set a default address.

    The database constraint forbids two — so unsetting the current one first is
    mandatory, not an optimisation.
    """
    CustomerAddress.objects.filter(customer=address.customer, is_default=True).exclude(
        pk=address.pk
    ).update(is_default=False)

    if not address.is_default:
        address.is_default = True
        address.save(update_fields=["is_default"])

    return address


@transaction.atomic
def review_document(
    document: CustomerDocument,
    *,
    approved: bool,
    reviewer,
    reason: str = "",
) -> CustomerDocument:
    """
    Approve or reject a verification document.

    It does not change the user's `verification_status` automatically — the
    verification decision depends on the set of documents required for the
    account type, and that is a business rule settled in phase 2.
    """
    previous = document.status
    document.status = DocumentStatus.APPROVED if approved else DocumentStatus.REJECTED
    document.reviewed_by = reviewer
    document.reviewed_at = timezone.now()
    document.rejection_reason = "" if approved else reason
    document.save(update_fields=["status", "reviewed_by", "reviewed_at", "rejection_reason"])

    AuditLog.objects.create(
        actor=reviewer,
        action=AuditAction.APPROVE if approved else AuditAction.REJECT,
        object_repr=str(document),
        changes={"status": {"old": previous, "new": document.status}, "reason": reason},
    )
    return document


def record_order(profile: CustomerProfile, amount, when=None) -> CustomerProfile:
    """
    Update the pre-stored statistics.

    Called from the `order_completed` listener — not from `orders` directly, so
    the direction stays downward.
    """
    when = when or timezone.now()

    profile.total_orders += 1
    profile.total_spent += amount
    profile.last_order_at = when
    if profile.first_order_at is None:
        profile.first_order_at = when

    profile.save(update_fields=["total_orders", "total_spent", "last_order_at", "first_order_at"])
    return profile
