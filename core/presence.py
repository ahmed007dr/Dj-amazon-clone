"""
The presence record — shared infrastructure  (ADR-17).

⚠️  **The cache is the source of "now", and the database the source of "was".**

    Writing a row on every request to learn who is online kills the database
    under any real load. And the record here does not know who uses it: the
    registered user in `accounts` and the anonymous visitor in `analytics` ask
    the same question and are answered by the same mechanism — and two copies of
    it would have drifted.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.core.cache import cache
from django.utils import timezone


class PresenceRegistry:
    """
    Who appeared during the most recent window.

    ⚠️  **One aggregated record, not a key per identity.**

        "How many are online now?" is a question about the set, and scattered
        keys can only be counted by scanning the keyspace — which is unavailable
        on LocMem in development and testing. A single record is read with one
        call on both.

    ⚠️  And read-then-write on a single record races between workers.

        The worst that happens: a heartbeat is overwritten, so one identity
        appears a cycle late and corrects itself on the next request seconds
        later. A distributed lock for that costs more than the error it prevents.
    """

    def __init__(self, key: str, *, window: timedelta, heartbeat: timedelta):
        self.key = key
        self.window = window
        self.heartbeat = heartbeat

    # ── Reading ────────────────────────────────────────────

    def _raw(self) -> dict:
        return cache.get(self.key) or {}

    def alive(self) -> dict:
        """
        The live identities and their timestamps.

        ⚠️  Pruning happens on read rather than through a sweeper task — the
            record grows only with the number of people actually present.
        """
        cutoff = timezone.now() - self.window

        alive = {}
        for identity, raw in self._raw().items():
            try:
                stamp = datetime.fromisoformat(raw)
            except (TypeError, ValueError):
                continue
            if stamp >= cutoff:
                alive[identity] = stamp
        return alive

    def identities(self) -> set:
        return set(self.alive())

    def count(self) -> int:
        return len(self.alive())

    # ── Writing ────────────────────────────────────────────

    def _save(self, alive: dict) -> None:
        cache.set(
            self.key,
            {identity: stamp.isoformat() for identity, stamp in alive.items()},
            int(self.window.total_seconds()) + 60,
        )

    def touch(self, identity) -> None:
        """A heartbeat — skipped if the previous one is newer than `heartbeat`."""
        identity = str(identity)
        now = timezone.now()
        registry = self._raw()

        # ⚠️  Writing on every request floods the cache without changing a single answer
        previous = registry.get(identity)
        if previous:
            try:
                if now - datetime.fromisoformat(previous) < self.heartbeat:
                    return
            except (TypeError, ValueError):
                pass

        alive = self.alive()
        alive[identity] = now
        self._save(alive)

    def drop(self, identity) -> None:
        identity = str(identity)
        if identity not in self._raw():
            return

        alive = self.alive()
        alive.pop(identity, None)
        self._save(alive)

    def clear(self) -> None:
        cache.delete(self.key)
