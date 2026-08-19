"""
Purposes — the unit of assignment on the responsibilities screen.

⚠️  **Deliberately a leaf module** (it imports nothing from the domain).

    The purpose is needed by two parties: `models`, to be a field's choices, and
    `templates`, so every template can declare one. Putting it in either made
    the other import it — and then the first imported it back when the templates
    needed validation, closing a cycle breakable only by an import inside a
    function: hiding the cycle rather than resolving it.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class MailPurpose(models.TextChoices):
    ACCOUNT = "ACCOUNT", _("الحساب والأمان")
    ORDERS = "ORDERS", _("الطلبات")
    PAYMENTS = "PAYMENTS", _("الدفع")
    SHIPPING = "SHIPPING", _("الشحن")
    INVENTORY = "INVENTORY", _("المخزون")
    MARKETING = "MARKETING", _("التسويق")
    SUPPORT = "SUPPORT", _("خدمة العملاء — الوارد")
    REPORTS = "REPORTS", _("التقارير")
    SYSTEM = "SYSTEM", _("النظام")


#: ⚠️  The purposes that are never assigned to a marketing account (ADR-76).
#:
#:     "Your password was changed" and "activate your account" are not
#:     marketing: sending them from a blacklisted account locks the user out of their account.
SECURITY_PURPOSES = frozenset({MailPurpose.ACCOUNT, MailPurpose.SYSTEM})
