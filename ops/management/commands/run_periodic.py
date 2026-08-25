"""
Run the periodic tasks.

    python manage.py run_periodic
    python manage.py run_periodic --job inventory
    python manage.py run_periodic --dry-run

⚠️  **This is the task queue — not Celery.**

    There are four periodic jobs here, the heaviest of which walks the stock
    batches once a day. A Celery worker, a Redis broker and a monitoring layer
    for four functions that execute in seconds is not infrastructure but
    operational overhead: two more services to monitor, restart and upgrade.

    The scheduling lives outside the application — `cron` or Task Scheduler. The
    details are in `ops/README.md`.

    And when work appears that **deserves** a real queue (heavy reports ·
    thousands of messages · image processing), Celery gets added then and for
    that work alone. The structure does not prevent it: every job is an
    independent function callable from any runner.

⚠️  And one job failing **does not stop the rest**.

    A corrupt batch that blocks quarantining must not block the release of
    reservations — or one error disables all maintenance until somebody notices.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from django.core.management.base import BaseCommand

from accounts import services as account_services
from analytics import services as analytics_services
from cart import services as cart_services
from imports import services as import_services
from inventory import services as inventory_services
from loyalty import services as loyalty_services
from mailing import inbound as mail_inbound
from mailing import services as mail_services

logger = logging.getLogger(__name__)


def _expire_points() -> int:
    """⚠️  The jobs return a count; the loyalty service returns a breakdown."""
    return loyalty_services.expire_points()["batches"]


#: job → (group, description, function)
#
# ⚠️  The order is deliberate: releasing reservations **before** the alerts.
#
#     An expired reservation is deducted from available; so computing the alerts
#     before the release produces a "critical stock" alert for stock that comes
#     back a second later — and the alert is then resolved the next day, so the system looks
#     erratic.
JOBS: dict[str, tuple[str, str, Callable[[], int]]] = {
    "release_reservations": (
        "inventory",
        "إفراج الحجوزات المنتهية",
        inventory_services.release_expired_reservations,
    ),
    "quarantine_batches": (
        "inventory",
        "حجر الدفعات المنتهية",
        inventory_services.quarantine_expired_batches,
    ),
    "expiry_alerts": (
        "inventory",
        "تنبيهات قرب انتهاء الصلاحية",
        inventory_services.check_expiring_batches,
    ),
    # ⚠️  **A rescue, not the runner.**
    #
    #     A bulk import is driven chunk by chunk by the admin's own browser,
    #     which is what makes the progress bar real. But a closed laptop at row
    #     four thousand leaves a job stuck at `RUNNING` forever, with four
    #     thousand products imported and six thousand not — the worst of the two
    #     possible outcomes.
    #
    #     This advances such a job **one chunk per tick**, so a large import
    #     finishes unattended over a few minutes. Running it to completion here
    #     would make this command take minutes and hold up the mail queue behind
    #     it, which is scheduled every few minutes for a reason.
    "resume_imports": (
        "imports",
        "استئناف عمليات الاستيراد المتروكة",
        import_services.resume_abandoned,
    ),
    "abandon_carts": (
        "cart",
        "إهمال السلال الراكدة",
        cart_services.abandon_stale_carts,
    ),
    # ⚠️  Expiring due points is **a periodic job, not an on-the-fly calculation**.
    #
    #     Without it the liability stays inflated in the ledger with points that
    #     will never be spent, and the customer sees a balance refused at the first
    #     redemption attempt — which is worse than a smaller balance they see as correct.
    "expire_points": (
        "loyalty",
        "إسقاط نقاط الولاء المنتهية",
        _expire_points,
    ),
    # ⚠️  **A safety net, not the main path.**
    #
    #     Delivery starts on `on_commit` the moment the event occurs — within seconds.
    #     This job picks up what failed (a server down · a timeout) and what got
    #     stuck (a process that died between the claim and the send). And without it
    #     a temporary failure meant a message lost forever.
    #
    #     It is therefore scheduled **every few minutes** rather than daily like the rest:
    #     the first retry comes after a minute, and delaying it to daily makes the
    #     password reset email arrive after its owner has forgotten it.
    "send_outbound_mail": (
        "mail",
        "تسليم بريد الطابور",
        mail_services.deliver_pending,
    ),
    # ⚠️  The pull comes **after** delivery in the order.
    #
    #     The inbox fills with replies to what we sent; and pulling it before
    #     delivering what is waiting makes the customer's reply arrive ahead of the
    #     message it answers — so the employee reads an answer with no question.
    "fetch_inbound_mail": (
        "mail",
        "سحب البريد الوارد",
        mail_inbound.fetch_all,
    ),
    # ⚠️  **Scheduled by the minute, not by the day** (ADR-17).
    #
    #     Presence is written to the cache on every request, and the database keeps the history.
    #     Without the flush, "last seen" in the accounts table stays at the moment
    #     of login forever, and the whole session record is lost if the cache restarts.
    #
    #     And the command is deliberately light: one query per distinct minute, and
    #     no query at all when nobody is online.
    "flush_presence": (
        "presence",
        "تفريغ سجل التواجد إلى الجلسات",
        account_services.flush_presence,
    ),
    # ⚠️  By the minute as well — the counters live in the cache, and restarting it
    #     between two flushes loses what lies between them. And the previous hour is
    #     flushed with the current one, so the minutes crossing the hour are not lost.
    "flush_traffic": (
        "presence",
        "تفريغ عدّادات الحركة",
        analytics_services.flush_traffic,
    ),
    # ⚠️  Retention is 90 days — traffic nobody reads after that stays a
    #     liability with no benefit. Scheduled daily, not by the minute.
    "purge_traffic": (
        "traffic",
        "حذف الحركة الأقدم من ٩٠ يومًا",
        analytics_services.purge_traffic,
    ),
}


class Command(BaseCommand):
    help = "تشغيل المهام الدورية (الجدولة من cron أو Task Scheduler)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--job",
            help=(
                "اسم مهمة واحدة أو مجموعة "
                "(inventory · cart · loyalty · mail · presence · traffic)"
            ),
        )
        parser.add_argument("--dry-run", action="store_true", help="عرض ما سيُنفَّذ بلا تنفيذ")

    def handle(self, *args, **options):
        selected = self._select(options.get("job"))

        if not selected:
            self.stderr.write(self.style.ERROR(f"لا مهمة بهذا الاسم: {options.get('job')}"))
            self.stderr.write(
                f"المتاح: {' · '.join(JOBS)} — "
                "أو مجموعة: inventory · cart · loyalty · mail · presence · traffic"
            )
            raise SystemExit(2)

        if options["dry_run"]:
            self.stdout.write("سيُنفَّذ:")
            for name, (_group, label, _fn) in selected.items():
                self.stdout.write(f"  {name:24} {label}")
            return

        failed = 0

        for name, (_group, label, job) in selected.items():
            started = time.monotonic()

            try:
                count = job()
            except Exception:
                # ⚠️  The failure is logged and does not stop the rest
                failed += 1
                logger.exception("فشلت المهمة الدورية %s", name)
                self.stdout.write(self.style.ERROR(f"  ✕ {label} — فشلت (انظر السجل)"))
                continue

            elapsed = time.monotonic() - started
            self.stdout.write(self.style.SUCCESS(f"  ✓ {label}: {count} ({elapsed:.2f}s)"))

        if failed:
            # ⚠️  A non-zero exit code — the scheduler detects the failure without reading a log
            self.stderr.write(self.style.ERROR(f"\n{failed} مهمة فشلت"))
            raise SystemExit(1)

    def _select(self, job: str | None) -> dict:
        if not job:
            return JOBS
        if job in JOBS:
            return {job: JOBS[job]}
        return {name: entry for name, entry in JOBS.items() if entry[0] == job}
