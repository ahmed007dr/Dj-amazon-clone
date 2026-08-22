"""
The time seed — visitor traffic and the spread of orders across the hours of the week.

⚠️  **A seed where everything happens in the same second shows nothing.**

    The load screen answers "when?", and data all landing at the moment of
    creation produces one lit cell and 167 empty ones — so the screen looks
    broken rather than empty. That is why this seed distributes time before
    anything else.

⚠️  And the shape is **not uniform randomness**.

    A flat distribution makes the map grey with no peak, so the difference
    between "working" and "not working" cannot be seen. The shape here mimics a
    real store: an evening peak, quiet before dawn, and a higher weekend — which
    is what makes a time-zone calculation error **visible** rather than passing unnoticed.
"""

from __future__ import annotations

import random
from datetime import timedelta

from django.utils import timezone

from accounts.models import DeviceType
from analytics.models import TrafficBucket

#: The number of days seeded — matching the default window on the load screen.
DAYS = 30

#: The weight of each hour (0–23) — an evening peak and a quiet dawn.
HOUR_WEIGHTS = [
    2, 1, 1, 1, 1, 2, 4, 7, 11, 14, 16, 18,
    17, 15, 14, 16, 20, 26, 30, 28, 22, 15, 9, 4,
]

#: The weight of each day in ISO order — Monday 1 … Sunday 7.
#
# ⚠️  Friday is lowest: the weekend in the Egyptian market, with the peaks
#     before and after it. A figure contradicting local reality makes the screen read but not
#     believed.
WEEKDAY_WEIGHTS = {1: 1.0, 2: 1.05, 3: 1.0, 4: 1.1, 5: 0.55, 6: 0.9, 7: 0.95}

#: The device split — phone first, which is the reality of any retail store.
DEVICE_SHARE = {
    DeviceType.MOBILE: 0.62,
    DeviceType.DESKTOP: 0.28,
    DeviceType.TABLET: 0.08,
    DeviceType.UNKNOWN: 0.02,
}

#: ⚠️  A fixed seed — two consecutive runs produce the same screen.
#
#     Numbers that change on every run make "did anything change after my
#     edit?" a question with no answer.
SEED = 20260818


def _shape(moment) -> float:
    local = timezone.localtime(moment)
    return HOUR_WEIGHTS[local.hour] * WEEKDAY_WEIGHTS[local.isoweekday()]


def seed() -> dict:
    """
    ⚠️  Called **after** the orders seed, not before — it distributes what was created.
    """
    from orders.models import Order

    rng = random.Random(SEED)
    now = timezone.localtime(timezone.now())

    # ── Spreading the orders across time ───────────────────
    #
    # ⚠️  `update`, not `save`: `created_at` is an `auto_now_add` field,
    #     and `save()` rewrites it with the save moment, cancelling the whole distribution.
    spread = 0
    for order_id in Order.objects.values_list("pk", flat=True):
        Order.objects.filter(pk=order_id).update(created_at=_pick_moment(rng, now))
        spread += 1

    # ── Visitor traffic ────────────────────────────────────
    buckets = []
    for day_offset in range(DAYS):
        day = now - timedelta(days=day_offset)

        for hour in range(24):
            moment = day.replace(hour=hour, minute=0, second=0, microsecond=0)
            if moment > now:
                continue

            visitors = int(_shape(moment) * rng.uniform(0.6, 1.4))
            if visitors <= 0:
                continue

            for device, share in DEVICE_SHARE.items():
                count = int(visitors * share)
                if count <= 0:
                    continue

                # ⚠️  Registered visitors are a minority — most people browsing a store
                #     never log in, which is why the anonymous count exists.
                known = int(count * 0.22)

                buckets.append(
                    TrafficBucket(
                        bucket_start=moment,
                        device_type=device,
                        # More requests than visitors: every visitor browses several pages
                        requests=count * rng.randint(4, 11),
                        guest_visitors=count - known,
                        known_visitors=known,
                    )
                )

    TrafficBucket.objects.bulk_create(buckets, ignore_conflicts=True)

    return {
        "counts": {
            "traffic_buckets": len(buckets),
            "orders_spread": spread,
            "days": DAYS,
        }
    }


def _pick_moment(rng: random.Random, now):
    """
    A moment within the last `DAYS` days, **weighted by the store's shape**.

    ⚠️  Rejection sampling rather than a uniform draw: the latter makes the
        buying peak flat while the browsing peak is sharp — a contradiction on
        the same screen that looks like a calculation error rather than a seed one.
    """
    peak = max(HOUR_WEIGHTS) * max(WEEKDAY_WEIGHTS.values())

    for _ in range(64):
        moment = now - timedelta(
            days=rng.randint(0, DAYS - 1),
            hours=rng.randint(0, 23),
            minutes=rng.randint(0, 59),
        )
        if rng.uniform(0, peak) <= _shape(moment):
            return moment

    return now - timedelta(days=rng.randint(0, DAYS - 1))
