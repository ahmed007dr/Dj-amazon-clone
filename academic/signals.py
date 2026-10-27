"""
Keeping `StudentProfile.is_verified` in step with the account.

⚠️  The account is the source of truth; the profile flag is its mirror.

    `User.verification_status` (accounts) is what every other domain reads — pricing,
    access, the catalogue. `StudentProfile.is_verified` exists only so the admin's
    student list can filter on it without joining. Two flags that are each written by
    hand drift apart the first time someone forgets one of them, so there is exactly
    one writer: this receiver, listening to the account.

⚠️  Why a receiver, and not a call from `customers`.

    The ID card is approved in `customers`, and `customers` and `academic` are
    independent siblings — neither imports the other. Both import `accounts`,
    so the account is the only place they can meet without a cycle: `customers`
    changes `User.verification_status`, and this module reacts to that.
"""

from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from academic.models import StudentProfile
from accounts.models import User


@receiver(post_save, sender=User, dispatch_uid="academic.mirror_student_verification")
def mirror_student_verification(sender, instance, created, update_fields=None, **kwargs):
    """
    Mirror the account's verification onto its student profile.

    ⚠️  Skipped for saves that cannot have changed it — `last_login` is written on
        every sign-in, and a profile lookup on each of those is a query for nothing.
    """
    if created:
        return
    if update_fields is not None and "verification_status" not in update_fields:
        return

    # One statement, and a no-op (zero rows) when the flag already agrees
    StudentProfile.objects.filter(user=instance).exclude(is_verified=instance.is_verified).update(
        is_verified=instance.is_verified
    )
