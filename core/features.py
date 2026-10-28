"""
Feature switches the owner can flip without a deploy.

They are rows in `SystemSetting` (group *general*), read through its cache, so a
switch costs no query once warm and a missing row means "off".

⚠️  **Missing means off.** Every switch here defaults to the conservative
    behaviour, so a fresh database, a restored backup or a deleted row can never
    switch an enforcement on by surprise.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from core.models.settings import SystemSetting

#: Student verification as a *requirement*.
#:
#: Off  → nothing is asked of the student: no "pending verification" notices, and
#:        student prices follow the account type alone.
#: On   → the notices return, and student prices require an approved ID.
STUDENT_VERIFICATION_ENFORCED = "student_verification_enforced"


def is_enabled(key: str) -> bool:
    return bool(SystemSetting.get(key, False))


def student_verification_enforced() -> bool:
    return is_enabled(STUDENT_VERIFICATION_ENFORCED)


# ═══════════════════════════════════════════════════════════
#  Free shipping above an amount
# ═══════════════════════════════════════════════════════════
#
# Two `SystemSetting` rows (group *orders*), created by `core/0003`: a switch and
# a threshold in the shop currency. They are rows rather than a shipping-owned
# table so they show up in the Django panel beside the other switches, reuse the
# audit trail, and need no migration in a domain that owns no other settings.

#: Free shipping as a *rule* — off by default, so a fresh database never gives anything away.
FREE_SHIPPING_ENABLED = "free_shipping_enabled"

#: The products total (after discounts, before tax and shipping) from which delivery is free.
FREE_SHIPPING_THRESHOLD = "free_shipping_threshold"


@dataclass(frozen=True)
class FreeShippingRule:
    """
    What the owner configured.

    `enabled` / `threshold` are the stored values (the admin screen shows them as
    they are); `active` is what the checkout acts on.
    """

    enabled: bool = False
    threshold: Decimal = Decimal("0.00")

    @property
    def active(self) -> bool:
        """
        ⚠️  On **and** a positive amount — otherwise the rule does not apply.

            A switch left on with an empty or zero threshold (a row edited by hand
            in the Django panel) would otherwise read as "free above 0", which is
            free shipping on every order. A broken rule must fail towards charging.
        """
        return self.enabled and self.threshold > 0


def free_shipping_rule() -> FreeShippingRule:
    """
    The current free-shipping rule, read straight from the database.

    ⚠️  **Not through the `SystemSetting.get` cache.**

        That cache is per process (local memory unless Redis is configured), so
        after the owner turns the rule off, another worker would keep waiving
        shipping until its copy expired — a price the shop is no longer willing to
        give, honoured for up to an hour. This is one indexed query on a
        two-row lookup per cart pricing, and it makes "off" mean off everywhere.
    """
    rows = dict(
        SystemSetting.objects.filter(
            pk__in=(FREE_SHIPPING_ENABLED, FREE_SHIPPING_THRESHOLD)
        ).values_list("key", "value")
    )

    enabled = rows.get(FREE_SHIPPING_ENABLED, False) is True

    try:
        threshold = Decimal(str(rows.get(FREE_SHIPPING_THRESHOLD, "0")))
    except (InvalidOperation, ValueError):
        threshold = Decimal("0")
    if not threshold.is_finite() or threshold < 0:
        threshold = Decimal("0")

    return FreeShippingRule(enabled=enabled, threshold=threshold.quantize(Decimal("0.01")))
