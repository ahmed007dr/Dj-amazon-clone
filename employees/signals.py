"""
Synchronising an employee's permissions with their status.

⚠️  **A signal, not a manual call.**

    Deactivating an employee happens from more than one place: the admin screen ·
    a management command · a direct correction. Tying the withdrawal of
    permissions to a call at one point means every other path leaves a departed
    employee with their group intact — and `has_perm` in the rest of the system
    says "yes".
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from employees.models import EmployeeProfile

logger = logging.getLogger(__name__)


@receiver(post_save, sender=EmployeeProfile, weak=False)
def sync_permissions_with_status(sender, instance, created, **kwargs):
    """
    ⚠️  **`apply_role_permissions`, not `set_role`.**

        The latter saves the profile, re-firing this signal endlessly. That
        genuinely happened, and the `except` below swallowed the
        `RecursionError` — so the save looked successful while every operation
        burned a thousand stack frames and logged an exception nobody read.

    ⚠️  And a failure is logged without failing the save.

        A broken synchronisation must not prevent deactivating an employee — and
        deactivation is the urgent action. But it **is logged at error level**: a
        deactivated employee with permissions still attached is a state to be
        reviewed, not swallowed.
    """
    from employees import services

    try:
        if instance.is_active:
            services.apply_role_permissions(instance)
        else:
            services.revoke_permissions(instance)
    except RecursionError:
        # ⚠️  Never swallowed: this is a symptom of a structural defect rather than a
        #     passing failure, and swallowing it is what hid it the first time.
        raise
    except Exception:
        logger.exception("فشلت مزامنة صلاحيات الموظف %s", instance.employee_number)
