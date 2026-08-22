"""
Usage traffic services — the only public interface to this domain.

⚠️  **Counting in the cache, aggregation in the database.**

    Counters are incremented atomically (`incr`), never read-then-write: every
    visitor's request passes through here, and reading a whole block and
    rewriting it on every request would have lost counts and loaded the network
    at the same time.

⚠️  And no personal identity is stored — no network address, no browser string.

    A visitor is identified by a hash that lives in the cache for two hours and
    then vanishes, and the database keeps nothing but **counts**. A visit log
    naming every visitor is a permanent legal liability in exchange for a
    question whose answer is a number.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Sum
from django.db.models.functions import ExtractHour, ExtractIsoWeekDay
from django.utils import timezone

from accounts.models import DeviceType
from accounts.services import device_type_from_user_agent
from analytics.models import TrafficBucket
from core.presence import PresenceRegistry

#: The window in which a visitor counts as "browsing now" — the same window as for users.
VISITOR_WINDOW = timedelta(minutes=5)
VISITOR_HEARTBEAT = timedelta(seconds=30)

#: The anonymous visitor record — parallel to the user record in `accounts`.
visitors = PresenceRegistry(
    "presence:guests", window=VISITOR_WINDOW, heartbeat=VISITOR_HEARTBEAT
)

#: Counters outlive their hour so the flush survives a late schedule.
COUNTER_TTL = 60 * 60 * 3

#: A visitor's fingerprint is forgotten after two hours — enough to tell two adjacent hours apart.
FINGERPRINT_TTL = 60 * 60 * 2

#: ⚠️  Bot markers — crawling is not human load.
#
#     Without excluding them, "the busiest hours in the store" becomes a
#     reflection of a search engine's crawl schedule rather than customer
#     behaviour, so shifts get staffed for an hour with not one human in it.
BOT_MARKERS = (
    "bot",
    "crawler",
    "spider",
    "slurp",
    "bingpreview",
    "headless",
    "python-requests",
    "curl/",
    "wget",
    "postman",
    "lighthouse",
    "monitor",
)


# ═══════════════════════════════════════════════════════════
#  Identity
# ═══════════════════════════════════════════════════════════


def is_bot(user_agent: str) -> bool:
    ua = (user_agent or "").lower()
    return any(marker in ua for marker in BOT_MARKERS)


def fingerprint(ip: str | None, user_agent: str) -> str:
    """
    The visitor fingerprint — **hashed and irreversible**.

    ⚠️  The salt comes from `SECRET_KEY`: without it the value becomes linkable
        to a known network address by trying the possibilities, turning an
        "anonymous statistic" into a full tracking record.
    """
    material = f"{settings.SECRET_KEY}|{ip or ''}|{user_agent or ''}"
    return hashlib.sha256(material.encode()).hexdigest()[:32]


# ═══════════════════════════════════════════════════════════
#  Counting
# ═══════════════════════════════════════════════════════════


def bucket_of(moment: datetime) -> datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


def _key(kind: str, bucket: datetime, suffix: str) -> str:
    return f"traffic:{kind}:{bucket:%Y%m%d%H}:{suffix}"


def _bump(key: str) -> None:
    """
    ⚠️  `add` then `incr` — never `get` then `set`.

        The latter loses every increment falling between the read and the write,
        which happens constantly when two workers hit the same hour.
    """
    cache.add(key, 0, COUNTER_TTL)
    try:
        cache.incr(key)
    except ValueError:
        # The key expired between the two lines — rare, and not worth a lock
        cache.set(key, 1, COUNTER_TTL)


def record_visit(*, ip: str | None, user_agent: str, authenticated: bool) -> None:
    """
    Record a single visit — called from the middleware on every store request.

    ⚠️  Registered and anonymous are counted separately.

        Merging them makes "customers online" an unreadable number: ten
        anonymous browsers and ten registered buyers are entirely different
        operational situations, and their sum, "20", says neither.
    """
    if is_bot(user_agent):
        return

    now = timezone.now()
    bucket = bucket_of(now)
    device = device_type_from_user_agent(user_agent)
    identity = fingerprint(ip, user_agent)

    _bump(_key("req", bucket, device))

    # ⚠️  `add` returns True once per fingerprint per hour — which is exactly the
    #     definition of a "unique visitor", with no set read and written on every request.
    if cache.add(_key("seen", bucket, identity), 1, FINGERPRINT_TTL):
        _bump(_key("known" if authenticated else "guest", bucket, device))

    # ⚠️  Registered users are not added here: their heartbeat happens in the
    #     authentication layer where **who they are** is known, and counting them twice inflates
    #     "online now".
    if not authenticated:
        visitors.touch(identity)


def guests_online() -> int:
    """How many anonymous browsers there are right now."""
    return visitors.count()


# ═══════════════════════════════════════════════════════════
#  Flushing
# ═══════════════════════════════════════════════════════════


def flush_traffic() -> int:
    """
    Flush the hour's counters into `TrafficBucket`.

    ⚠️  The previous hour is flushed along with the current one.

        Flushing the current one alone loses the last minutes of every hour if
        the schedule slips across the hour boundary — sometimes the peak moment.

    ⚠️  And values are written **by maximum, not by replacement**.

        The counters live in the cache; restarting it zeroes them, so a direct
        write would have erased a recorded hour and put a zero in its place.
    """
    now = timezone.now()
    buckets = (bucket_of(now) - timedelta(hours=1), bucket_of(now))

    written = 0
    for bucket in buckets:
        for device in DeviceType.values:
            counts = {
                "requests": cache.get(_key("req", bucket, device)) or 0,
                "guest_visitors": cache.get(_key("guest", bucket, device)) or 0,
                "known_visitors": cache.get(_key("known", bucket, device)) or 0,
            }
            if not any(counts.values()):
                continue

            row, created = TrafficBucket.objects.get_or_create(
                bucket_start=bucket, device_type=device, defaults=counts
            )

            if not created:
                changed = [
                    field for field, value in counts.items() if value > getattr(row, field)
                ]
                if not changed:
                    continue
                for field in changed:
                    setattr(row, field, counts[field])
                row.save(update_fields=changed)

            written += 1

    return written


def purge_traffic(days: int = 90) -> int:
    """
    ⚠️  Retention is deliberately limited.

        Traffic nobody reads after three months stays a liability with no
        benefit — and the operational question ("when is it busy?") is seasonal,
        not historical.
    """
    cutoff = bucket_of(timezone.now()) - timedelta(days=days)
    deleted, _ = TrafficBucket.objects.filter(bucket_start__lt=cutoff).delete()
    return deleted


# ═══════════════════════════════════════════════════════════
#  Reading
# ═══════════════════════════════════════════════════════════


def _period_rows(start: date, end: date):
    return TrafficBucket.objects.filter(
        bucket_start__date__gte=start, bucket_start__date__lte=end
    )


def traffic_summary(start: date, end: date) -> dict:
    """Traffic for a period — aggregated and split by device."""
    rows = _period_rows(start, end)

    totals = rows.aggregate(
        requests=Sum("requests"),
        guests=Sum("guest_visitors"),
        known=Sum("known_visitors"),
    )

    by_device = [
        {
            "device_type": row["device_type"],
            "requests": row["requests"] or 0,
            "guest_visitors": row["guests"] or 0,
            "known_visitors": row["known"] or 0,
        }
        for row in rows.values("device_type")
        .annotate(
            requests=Sum("requests"),
            guests=Sum("guest_visitors"),
            known=Sum("known_visitors"),
        )
        .order_by("-requests")
    ]

    return {
        "start": str(start),
        "end": str(end),
        "requests": totals["requests"] or 0,
        "guest_visitors": totals["guests"] or 0,
        "known_visitors": totals["known"] or 0,
        "by_device": by_device,
    }


def traffic_peak_hours(start: date, end: date) -> dict:
    """
    The distribution of visitors across the hours of the week — the same grid as
    `reporting.peak_hours`.

    ⚠️  The two questions differ: this is the **browsing** peak, that is the **buying** peak.

        And the gap between them is the real insight: an hour when people browse
        and do not buy means a price or stock problem, not a shortage of visits.

    ⚠️  And the grid is always complete — a heatmap with missing cells renders distorted.
    """
    rows = (
        _period_rows(start, end)
        .annotate(
            weekday=ExtractIsoWeekDay("bucket_start"),
            hour=ExtractHour("bucket_start"),
        )
        .values("weekday", "hour")
        .annotate(
            requests=Sum("requests"),
            guests=Sum("guest_visitors"),
            known=Sum("known_visitors"),
        )
    )

    grid = {(row["weekday"], row["hour"]): row for row in rows}

    cells = []
    for weekday in range(1, 8):
        for hour in range(24):
            row = grid.get((weekday, hour))
            visitor_count = ((row["guests"] or 0) + (row["known"] or 0)) if row else 0
            cells.append(
                {
                    "weekday": weekday,
                    "hour": hour,
                    "requests": (row["requests"] or 0) if row else 0,
                    "visitors": visitor_count,
                }
            )

    busiest = max(cells, key=lambda cell: cell["visitors"])

    return {
        "start": str(start),
        "end": str(end),
        "timezone": str(timezone.get_current_timezone()),
        "cells": cells,
        # ⚠️  A period with no traffic returns `None`, not the first cell with zero visitors
        "peak_cell": busiest if busiest["visitors"] else None,
    }
