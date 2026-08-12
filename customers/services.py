"""
خدمات نطاق العملاء — الواجهة العامة الوحيدة.
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
    ⚠️  يُستدعى عند الحاجة لا بإشارة `post_save` على `User`.

    الإشارة كانت تنشئ ملفًا لكل مستخدم بلا استثناء — بما فيهم
    المديرون والموظفون. النتيجة صفوف يتيمة وأرقام عملاء مهدورة.
    """
    profile, _created = CustomerProfile.objects.get_or_create(user=user)
    return profile


@transaction.atomic
def set_default_address(address: CustomerAddress) -> CustomerAddress:
    """
    تعيين عنوان افتراضي.

    القيد في قاعدة البيانات يمنع اثنين — فالسحب من الحالي أولًا
    إلزامي لا تحسين.
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
    اعتماد أو رفض وثيقة تحقق.

    لا يغيّر `verification_status` للمستخدم تلقائيًا — قرار التوثيق
    يعتمد على مجموعة الوثائق المطلوبة لنوع الحساب، وتلك قاعدة عمل
    تُحسم في المرحلة ٢.
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
    تحديث الإحصاءات المُخزَّنة مسبقًا.

    يُستدعى من مستمع `order_completed` — لا من `orders` مباشرةً،
    فالاتجاه يبقى نازلًا.
    """
    when = when or timezone.now()

    profile.total_orders += 1
    profile.total_spent += amount
    profile.last_order_at = when
    if profile.first_order_at is None:
        profile.first_order_at = when

    profile.save(update_fields=["total_orders", "total_spent", "last_order_at", "first_order_at"])
    return profile
