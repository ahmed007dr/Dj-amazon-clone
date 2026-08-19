"""
Flush presence from the cache into the database.

⚠️  Why does this command exist at all?  (ADR-17)

    Writing `last_activity` to PostgreSQL on **every request** kills it:
    ten thousand requests a minute = ten thousand writes to the same table.

    The solution: write to Redis (cheap, in memory), then flush in bulk every
    60 seconds.

        Redis      →  live presence (hot)
        PostgreSQL →  session history (durable)

Usage:
    */1 * * * *  python manage.py flush_presence

Or as a continuous loop:
    python manage.py flush_presence --loop --interval 60
"""

import time
from datetime import datetime

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import UserSession

PRESENCE_PREFIX = "presence:"


class Command(BaseCommand):
    help = "تفريغ آخر نشاط من الكاش إلى قاعدة البيانات"

    def add_arguments(self, parser):
        parser.add_argument(
            "--loop",
            action="store_true",
            help="التشغيل المستمر بدل مرة واحدة",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="الثواني بين دورتين في وضع الحلقة",
        )

    def handle(self, *args, **options):
        if options["loop"]:
            self.stdout.write(f"وضع الحلقة — كل {options['interval']} ثانية. Ctrl+C للإيقاف.")
            try:
                while True:
                    self._flush_once()
                    time.sleep(options["interval"])
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("\nتوقف."))
        else:
            self._flush_once()

    def _flush_once(self) -> int:
        entries = self._collect()

        if not entries:
            self.stdout.write("لا تحديثات معلّقة.")
            return 0

        updated = self._persist(entries)
        self.stdout.write(self.style.SUCCESS(f"حُدّثت {updated} جلسة في {timezone.now():%H:%M:%S}"))
        return updated

    def _collect(self) -> dict[str, datetime]:
        """
        Collect the presence keys from the cache.

        ⚠️  `keys()` with a pattern is available on RedisCache, not on
            LocMemCache. In development without Redis the command is skipped
            quietly — presence is written at login time regardless.
        """
        try:
            keys = cache.keys(f"{PRESENCE_PREFIX}*")
        except (AttributeError, NotImplementedError):
            self.stdout.write(
                self.style.WARNING("الكاش الحالي لا يدعم البحث بالنمط — يلزم Redis. تخطٍّ.")
            )
            return {}

        entries: dict[str, datetime] = {}
        for key in keys:
            raw = cache.get(key)
            if raw is None:
                continue

            # presence:<user_id>:<session_key>
            parts = str(key).split(":", 2)
            if len(parts) != 3:
                continue

            try:
                entries[parts[2]] = datetime.fromisoformat(raw)
            except (TypeError, ValueError):
                continue

            cache.delete(key)

        return entries

    @transaction.atomic
    def _persist(self, entries: dict[str, datetime]) -> int:
        sessions = list(
            UserSession.objects.filter(session_key__in=entries.keys(), logout_at__isnull=True)
        )

        for session in sessions:
            session.last_activity = entries[session.session_key]

        if sessions:
            # One bulk write — not a write per session
            UserSession.objects.bulk_update(sessions, ["last_activity"])

        return len(sessions)
