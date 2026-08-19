"""
Read queries for the admin screens.

⚠️  Every function here returns an aggregated map for a set of users — **not one
    query per row**. A table of a hundred users must not produce 400 queries.
"""

from __future__ import annotations

from django.db.models import Count, Max, Sum

from accounts import services as account_services
from accounts.models import UserSession
from core.models.audit import AuditLog


def online_user_ids(user_ids=None) -> set:
    """
    The ids of those online now.

    ⚠️  A single source — `accounts.services`.

        A second copy of the presence window here would have read the database
        alone, so the accounts table would show people missing from "online now",
        or the reverse.
    """
    ids = set(account_services.online_user_ids())
    if user_ids is not None:
        ids &= set(user_ids)
    return ids


def last_seen_map(user_ids) -> dict:
    """Last seen per user — a single aggregated query."""
    rows = (
        UserSession.objects.filter(user_id__in=user_ids)
        .values("user_id")
        .annotate(last_seen=Max("last_activity"))
    )
    return {row["user_id"]: row["last_seen"] for row in rows}


def usage_map(user_ids) -> dict:
    """
    Total time used, in seconds.

    Open sessions are excluded — their duration is not counted until they close.
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
    The last action per user — from the audit log.

    ⚠️  "Last seen" and "last action" are two different questions:
        the first comes from `UserSession`, the second from `AuditLog`.
        Someone who opens the app and does nothing has a sighting but no action.
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
    """`DISTINCT ON` is available in PostgreSQL, not SQLite."""
    from django.db import connection

    return connection.vendor == "postgresql"


def enrich_context(user_ids) -> dict:
    """
    The complete serializer context — in a fixed number of queries however many
    rows there are.
    """
    user_ids = list(user_ids)
    return {
        "online_ids": online_user_ids(user_ids),
        "last_seen_map": last_seen_map(user_ids),
        "usage_map": usage_map(user_ids),
        "session_count_map": session_count_map(user_ids),
        "last_action_map": last_action_map(user_ids),
    }
