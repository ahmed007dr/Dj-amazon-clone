"""
Drive an import from the terminal.

    python manage.py run_import catalogue.xlsx --mode CREATE_ONLY
    python manage.py run_import catalogue.xlsx --validate-only
    python manage.py run_import --job 018f4e2a-... --resume
    python manage.py run_import --list

⚠️  **This exists for the first load, and the first load is different.**

    Ten thousand products with their opening stock is not a screen the admin
    keeps open for several minutes on the day the shop goes live; it is a
    migration, run once, from the machine that holds the file. The browser path
    is right for the weekly price list and wrong for this.

    And it is the same `services.advance` the browser calls — not a second
    implementation. A separate "fast path" that skips the dry run or writes
    stock directly is how the terminal and the panel end up disagreeing about
    what the catalogue contains.

⚠️  It **prints progress and does not spin silently.**

    A command that shows nothing for four minutes gets interrupted, and an
    interrupted import leaves a job at `RUNNING` that only the periodic runner
    will finish — hours later, unattended, when nobody is watching for the
    result.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from imports import report, services, spec
from imports.models import ImportJob, ImportStatus


class Command(BaseCommand):
    help = "تشغيل استيراد جماعي من ملف xlsx"

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", help="مسار ملف xlsx")
        parser.add_argument(
            "--mode",
            default=spec.ImportMode.CREATE_ONLY,
            choices=[
                spec.ImportMode.CREATE_ONLY,
                spec.ImportMode.UPDATE_ONLY,
                spec.ImportMode.UPSERT,
            ],
        )
        parser.add_argument(
            "--validate-only",
            action="store_true",
            help="الفحص الجاف وحده — لا يكتب شيئًا",
        )
        parser.add_argument("--job", help="معرّف وظيفة قائمة")
        parser.add_argument("--resume", action="store_true", help="استئناف وظيفة متوقفة")
        parser.add_argument("--list", action="store_true", help="عرض آخر الوظائف")
        parser.add_argument(
            "--publish",
            action="store_true",
            help="تفعيل المنتجات فور اكتمال الاستيراد",
        )
        parser.add_argument(
            "--errors-to",
            help="حفظ ملف الصفوف الفاشلة في هذا المسار",
        )

    # ── entry ──────────────────────────────────────────────

    def handle(self, *args, **options):
        if options["list"]:
            return self._list()

        if options["job"]:
            job = ImportJob.objects.filter(pk=options["job"]).first()
            if job is None:
                raise CommandError("لا توجد وظيفة بهذا المعرّف")
        else:
            job = self._upload(options)

        if options["resume"] and job.status in (ImportStatus.RUNNING, ImportStatus.VALIDATING):
            self.stdout.write(f"استئناف من {job.phase} عند الصف {job.cursor}")
            self._drive(job)
        else:
            self._validate(job)

            # ⚠️  `--validate-only` falls through to the same exit check below
            #     rather than returning here.
            #
            #     It used to return, which meant a rejected file exited 0 — and
            #     a deployment script gating on `run_import --validate-only`
            #     read that as "the sheet is fine" and carried straight on to the
            #     real run. A check that cannot fail is not a check.
            if not options["validate_only"] and job.status == ImportStatus.VALIDATED:
                services.start_execution(job)
                self._drive(job)

        self._report(job, options)

        if options["publish"] and job.status in (ImportStatus.DONE, ImportStatus.PARTIAL):
            count = services.publish(job)
            self.stdout.write(self.style.SUCCESS(f"تم تفعيل {count:,} منتجًا"))

        if job.status in (ImportStatus.FAILED, ImportStatus.REJECTED):
            sys.exit(1)

    # ── steps ──────────────────────────────────────────────

    def _upload(self, options) -> ImportJob:
        if not options["path"]:
            raise CommandError("حدّد مسار الملف أو --job")

        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"الملف غير موجود: {path}")

        self.stdout.write(f"رفع {path.name} ({path.stat().st_size:,} بايت)…")
        with path.open("rb") as handle:
            job = services.create_job(File(handle, name=path.name), mode=options["mode"])

        counts = "، ".join(f"{name}: {count:,}" for name, count in job.row_counts.items())
        self.stdout.write(f"الوظيفة {job.pk} — {counts}")

        if earlier := services.earlier_import_of(job):
            self.stdout.write(
                self.style.WARNING(
                    f"تنبيه: نفس الملف استُورد في {earlier.created_at:%Y-%m-%d %H:%M}"
                )
            )
        return job

    def _validate(self, job: ImportJob) -> None:
        self.stdout.write("الفحص الجاف — لا يُكتب شيء…")
        services.start_validation(job)
        self._drive(job)

        summary = (job.preview or {}).get("summary", {})
        style = self.style.SUCCESS if job.status == ImportStatus.VALIDATED else self.style.ERROR
        self.stdout.write(
            style(
                f"  إنشاء: {summary.get('will_create', 0):,} · "
                f"تحديث: {summary.get('will_update', 0):,} · "
                f"مرفوض: {summary.get('rejected', 0):,}"
            )
        )

    def _drive(self, job: ImportJob) -> None:
        """
        The loop. One chunk, print, repeat.

        ⚠️  `advance` never raises for a row-level problem — it records the row
            and carries on. What ends this loop is the status, which is why the
            condition is `is_running` and not a try/except.
        """
        started = time.time()
        last_line = 0

        while job.is_running:
            services.advance(job)

            processed = job.processed_rows
            if processed - last_line >= 500 or not job.is_running:
                elapsed = max(time.time() - started, 0.001)
                self.stdout.write(
                    f"\r  {job.phase} — {processed:,}/{job.total_rows:,} "
                    f"({job.progress_percent}%) · {processed / elapsed:,.0f} صف/ث",
                    ending="",
                )
                self.stdout.flush()
                last_line = processed

        self.stdout.write("")

    def _report(self, job: ImportJob, options) -> None:
        job.refresh_from_db()
        style = (
            self.style.SUCCESS
            if job.status in (ImportStatus.DONE, ImportStatus.VALIDATED)
            else self.style.WARNING
            if job.status == ImportStatus.PARTIAL
            else self.style.ERROR
        )
        self.stdout.write(style(f"الحالة: {job.get_status_display()}"))

        # ⚠️  "created 1,197" after a dry run is a lie the admin acts on.
        #     The counters are the same field either way; the verb is not.
        dry = job.status in (ImportStatus.VALIDATED, ImportStatus.REJECTED)
        self.stdout.write(
            f"  {'سيُنشأ' if dry else 'أُنشئ'} {job.created_count:,} · "
            f"{'سيُحدَّث' if dry else 'حُدّث'} {job.updated_count:,} · "
            f"{'مرفوض' if dry else 'فشل'} {job.failed_count:,}"
        )
        if job.error_message:
            self.stdout.write(self.style.ERROR(f"  {job.error_message}"))

        if not job.errors.exists():
            return

        # ⚠️  The most repeated message, not the first one. Three thousand
        #     failures are almost never three thousand problems.
        from django.db.models import Count

        top = (
            job.errors.values("sheet", "column", "message")
            .annotate(total=Count("id"))
            .order_by("-total")[:5]
        )
        self.stdout.write("  أكثر الأخطاء تكرارًا:")
        for row in top:
            self.stdout.write(
                f"    {row['total']:>6,} × [{row['sheet']}] {row['column']}: {row['message'][:70]}"
            )

        if destination := options.get("errors_to"):
            target = Path(destination)
            target.write_bytes(report.build(job))
            self.stdout.write(f"  ملف الصفوف الفاشلة: {target}")

    def _list(self) -> None:
        jobs = ImportJob.objects.order_by("-created_at")[:15]
        if not jobs:
            self.stdout.write("لا توجد وظائف")
            return
        for job in jobs:
            self.stdout.write(
                f"{job.created_at:%Y-%m-%d %H:%M}  {str(job.pk)[:8]}  "
                f"{job.status:<10}  {job.progress_percent:>3}%  "
                f"{job.created_count:>7,}+ {job.failed_count:>6,}✗  {job.original_filename}"
            )
