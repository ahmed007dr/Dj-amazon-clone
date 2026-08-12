"""
استعلامات القراءة لشاشات الأدمن.

⚠️  كل دالة هنا تُرجع خريطة مجمّعة لمجموعة مستخدمين — **لا استعلامًا
    لكل صف**. جدول بمئة مستخدم لا يجوز أن ينتج ٤٠٠ استعلام.
"""

from __future__ import annotations

from django.db.models import Count, Max, Sum
from django.utils import timezone

from accounts.models import UserSession
from accounts.services import PRESENCE_WINDOW
from core.models.audit import AuditLog


def online_user_ids(user_ids=None) -> set:
    """معرّفات المتصلين الآن."""
    cutoff = timezone.now() - PRESENCE_WINDOW
    queryset = UserSession.objects.filter(last_activity__gte=cutoff, logout_at__isnull=True)
    if user_ids is not None:
        queryset = queryset.filter(user_id__in=user_ids)

    return set(queryset.values_list("user_id", flat=True))


def last_seen_map(user_ids) -> dict:
    """آخر ظهور لكل مستخدم — استعلام واحد مجمّع."""
    rows = (
        UserSession.objects.filter(user_id__in=user_ids)
        .values("user_id")
        .annotate(last_seen=Max("last_activity"))
    )
    return {row["user_id"]: row["last_seen"] for row in rows}


def usage_map(user_ids) -> dict:
    """
    إجمالي مدة الاستخدام بالثواني.

    الجلسات المفتوحة لا تدخل — مدتها غير محسوبة حتى تُغلق.
    """
    rows = (
        UserSession.objects.filter(user_id__in=user_ids)
        .values("user_id")
        .annotate(total=Sum("duration_seconds"))
    )
    return {row["user_id"]: row["total"] or 0 for row in rows}


def session_count_map(user_ids) -> dict:
    rows = (
        UserSession.objects.filter(user_id__in=user_ids)
        .values("user_id")
        .annotate(total=Count("id"))
    )
    return {row["user_id"]: row["total"] for row in rows}


def last_action_map(user_ids) -> dict:
    """
    آخر عملية لكل مستخدم — من سجل التدقيق.

    ⚠️  «آخر ظهور» و«آخر عملية» سؤالان مختلفان:
        الأول من `UserSession`، والثاني من `AuditLog`.
        من يفتح التطبيق ولا يفعل شيئًا له ظهور بلا عملية.
    """
    result = {}
    for entry in (
        AuditLog.objects.filter(actor_id__in=user_ids)
        .order_by("actor_id", "-created_at")
        .distinct("actor_id")
        if _supports_distinct_on()
        else AuditLog.objects.filter(actor_id__in=user_ids).order_by("-created_at")
    ):
        result.setdefault(entry.actor_id, entry)
    return result


def _supports_distinct_on() -> bool:
    """`DISTINCT ON` متاح في PostgreSQL لا SQLite."""
    from django.db import connection

    return connection.vendor == "postgresql"


def enrich_context(user_ids) -> dict:
    """
    سياق الـ serializer كاملًا — بعدد ثابت من الاستعلامات
    مهما كبر عدد الصفوف.
    """
    user_ids = list(user_ids)
    return {
        "online_ids": online_user_ids(user_ids),
        "last_seen_map": last_seen_map(user_ids),
        "usage_map": usage_map(user_ids),
        "session_count_map": session_count_map(user_ids),
        "last_action_map": last_action_map(user_ids),
    }
