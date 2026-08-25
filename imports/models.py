"""
Bulk import — the job and its errors.

⚠️  **The job is a row in the database, not a variable in a process.**

    There is no task queue here (ADR-42) and the host is Passenger: a request
    that takes minutes is killed, and a Python object holding progress dies with
    the worker that owned it. So progress is written down after every chunk, and
    any of three callers can pick the job up where the last one stopped — the
    admin's browser, the periodic runner, or the management command.

⚠️  And **no row of a successful import is stored.**

    Ten thousand rows that worked are ten thousand rows of noise; what the admin
    needs afterwards is the count and the failures. The successes are already
    recorded where they belong — as products, batches and stock movements.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.identifiers import random_filename
from core.models.base import BaseModel, TimeStampedModel


def import_file_path(instance, filename: str) -> str:
    """
    ⚠️  A random name on a sharded path — the same rule as every other upload.

        An import file is a supplier price list: costs, margins and the shape of
        the catalogue. `MEDIA_ROOT` is served to anyone who knows the path, and
        `imports/2026-08/pricelist.xlsx` is guessed on the first try.
    """
    return f"imports/{random_filename(filename)}"


class ImportStatus(models.TextChoices):
    """
    ⚠️  `VALIDATED` is a state, not a flag.

        Uploading and executing are separated by a dry run that must have
        actually happened: a file goes in as `UPLOADED`, and only a completed
        validation pass moves it to `VALIDATED`. Nothing executes from any other
        state — which is what stops "upload and hope" on ten thousand rows.

    ⚠️  And `PARTIAL` is a first-class outcome, not a failure.

        Each chunk commits on its own, so a file with forty bad rows out of ten
        thousand imports 9,960 products and reports forty. Rolling the whole
        thing back for those forty would mean the admin fixes them and re-uploads
        everything — and the second run hits the same wall on a different forty.
    """

    UPLOADED = "UPLOADED", _("مرفوع")
    VALIDATING = "VALIDATING", _("قيد الفحص")
    VALIDATED = "VALIDATED", _("جاهز للتنفيذ")
    REJECTED = "REJECTED", _("مرفوض — أخطاء تمنع التنفيذ")
    RUNNING = "RUNNING", _("قيد التنفيذ")
    DONE = "DONE", _("اكتمل")
    PARTIAL = "PARTIAL", _("اكتمل بأخطاء جزئية")
    FAILED = "FAILED", _("فشل")
    CANCELLED = "CANCELLED", _("ملغى")


#: States in which a chunk is still owed. **Not** `VALIDATED`.
#
# ⚠️  `VALIDATED` is a job **waiting for a human**, not a job in flight.
#
#     Listing it here made `advance` run once more on a job whose phases were
#     already finished, and the second `_finish` no longer saw `VALIDATING` — so
#     a dry run that had just completed re-labelled itself `DONE`, and the admin
#     was told ten thousand products were imported when nothing had been written
#     at all. The two states that owe work are the two that are running.
ADVANCEABLE = frozenset({ImportStatus.VALIDATING, ImportStatus.RUNNING})

#: States nothing may change any more.
TERMINAL = frozenset(
    {
        ImportStatus.DONE,
        ImportStatus.PARTIAL,
        ImportStatus.FAILED,
        ImportStatus.CANCELLED,
        ImportStatus.REJECTED,
    }
)


class ImportPhase(models.TextChoices):
    """
    Which pass the runner is in.

    ⚠️  The order is fixed and it matters: products, then variants, then stock.

        A stock line names a product by `sku`, and a variant names its parent
        the same way. Receiving stock before the product exists is the one
        ordering mistake that cannot be repaired by re-running — the batch would
        have to attach to something.
    """

    PRODUCTS = "PRODUCTS", _("المنتجات")
    VARIANTS = "VARIANTS", _("النسخ")
    STOCK = "STOCK", _("الرصيد الافتتاحي")
    FINISHED = "FINISHED", _("انتهى")


PHASE_ORDER = [ImportPhase.PRODUCTS, ImportPhase.VARIANTS, ImportPhase.STOCK]


class ImportJob(BaseModel):
    """One uploaded file and everything that happened to it."""

    file = models.FileField(_("الملف"), upload_to=import_file_path)
    original_filename = models.CharField(_("اسم الملف"), max_length=255, blank=True)

    #: SHA-256 of the uploaded bytes.
    #
    # ⚠️  Not a uniqueness constraint — a **warning**. Re-importing the same file
    #     is legitimate (a failed run, a corrected environment), but doing it by
    #     accident on `CREATE_ONLY` produces a wall of duplicate-SKU errors, and
    #     on `UPSERT` it silently rewrites every row with data the admin thought
    #     they had already superseded. The API answers "you imported this exact
    #     file on the 3rd" and lets them decide.
    file_hash = models.CharField(_("بصمة الملف"), max_length=64, blank=True, db_index=True)

    mode = models.CharField(_("النمط"), max_length=16, db_index=True)
    status = models.CharField(
        _("الحالة"),
        max_length=16,
        choices=ImportStatus.choices,
        default=ImportStatus.UPLOADED,
        db_index=True,
    )
    phase = models.CharField(
        _("المرحلة"),
        max_length=16,
        choices=ImportPhase.choices,
        default=ImportPhase.PRODUCTS,
    )

    # ── Counters ───────────────────────────────────────────
    #: Rows found per sheet at upload: {"products": 9840, "stock": 9840}
    row_counts = models.JSONField(_("عدد الصفوف"), default=dict, blank=True)

    #: How far the current phase has advanced — the resume point.
    cursor = models.PositiveIntegerField(_("المؤشر"), default=0)

    created_count = models.PositiveIntegerField(_("المُنشأ"), default=0)
    updated_count = models.PositiveIntegerField(_("المُحدَّث"), default=0)
    skipped_count = models.PositiveIntegerField(_("المتخطّى"), default=0)
    failed_count = models.PositiveIntegerField(_("الفاشل"), default=0)

    #: Filled by the dry run: rows that would be created / updated / rejected.
    preview = models.JSONField(_("نتيجة الفحص"), default=dict, blank=True)

    # ── Options chosen at upload ───────────────────────────
    #: Create a brand or manufacturer named in the sheet but absent from the database.
    #
    # ⚠️  Off by default, and that is the safe direction. A typo in a brand name
    #     under "on" creates a second brand rather than failing one row — and the
    #     catalogue ends up with «Pfizer» and «Pfzier» side by side, which nobody
    #     notices until a customer filters by brand.
    create_missing_brands = models.BooleanField(_("إنشاء البراندات الناقصة"), default=False)

    # ⚠️  **There is deliberately no equivalent option for categories.**
    #
    #     A category carries a materialised path that is rebuilt for every
    #     descendant beneath it, and inventing one from a spreadsheet cell puts
    #     an unreviewed node into the store's public menu tree. Unlike a brand,
    #     there is no safe default — so rather than an option nobody should
    #     turn on, the answer is that a missing category is an error and the
    #     admin creates it on the categories screen.

    # ── Ownership and timing ───────────────────────────────
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="import_jobs",
        verbose_name=_("بدأها"),
    )
    started_at = models.DateTimeField(_("بدأ في"), null=True, blank=True)
    finished_at = models.DateTimeField(_("انتهى في"), null=True, blank=True)

    #: Touched after every chunk — this is how an abandoned job is recognised.
    #
    # ⚠️  Without it a job stuck at `RUNNING` because the admin closed the tab is
    #     indistinguishable from one being actively processed, and the periodic
    #     runner either never picks it up or fights the browser for it.
    heartbeat_at = models.DateTimeField(_("آخر نبضة"), null=True, blank=True, db_index=True)

    error_message = models.TextField(_("رسالة الخطأ"), blank=True)

    class Meta:
        verbose_name = _("وظيفة استيراد")
        verbose_name_plural = _("وظائف الاستيراد")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["status", "heartbeat_at"]),
        ]

    def __str__(self):
        return f"{self.original_filename or self.pk} · {self.status}"

    # ── Derived ────────────────────────────────────────────

    @property
    def total_rows(self) -> int:
        return sum(int(value) for value in (self.row_counts or {}).values())

    @property
    def processed_rows(self) -> int:
        return self.created_count + self.updated_count + self.skipped_count + self.failed_count

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL

    @property
    def is_running(self) -> bool:
        """
        Whether another chunk is owed.

        ⚠️  The client loop must test **this**, not `not is_terminal`.

            `VALIDATED` is neither running nor terminal — it is the pause where
            the admin reads the preview and decides. A loop written against
            `is_terminal` spins on that pause forever, hammering the advance
            endpoint with calls that correctly do nothing.
        """
        return self.status in ADVANCEABLE

    @property
    def progress_percent(self) -> int:
        total = self.total_rows
        if not total:
            return 100 if self.is_terminal else 0
        return min(100, round(self.processed_rows * 100 / total))

    def touch(self, **fields) -> None:
        """
        ⚠️  A targeted `update`, never `save()` on the whole row.

            The runner writes progress after every chunk while the admin's screen
            polls the same row. A full save carries whatever the in-memory copy
            held — including a status read before the last chunk — and quietly
            walks the job backwards.
        """
        fields["heartbeat_at"] = timezone.now()
        for name, value in fields.items():
            setattr(self, name, value)
        type(self).objects.filter(pk=self.pk).update(**fields)


class ImportRowError(TimeStampedModel):
    """
    One rejected row.

    ⚠️  `BigAutoField`, not a UUID — this table has no URL and no API of its own
        (ADR-25/28). It is written in bulk and read as a block.

    ⚠️  And `row_number` is the number **the admin sees in Excel**, not an index
        into anything. An off-by-two here — the header row and the key row — is
        the difference between a report that fixes the file and one that sends
        them hunting through ten thousand rows.
    """

    job = models.ForeignKey(
        ImportJob, on_delete=models.CASCADE, related_name="errors", verbose_name=_("الوظيفة")
    )
    sheet = models.CharField(_("الورقة"), max_length=20, db_index=True)
    row_number = models.PositiveIntegerField(_("رقم الصف"))

    #: Blank when the failure belongs to the whole row rather than one cell.
    column = models.CharField(_("العمود"), max_length=64, blank=True)

    #: The offending value, truncated — enough to recognise, not enough to be a copy of the file.
    value = models.CharField(_("القيمة"), max_length=200, blank=True)
    message = models.TextField(_("الرسالة"))

    #: `sku` of the row, so the admin can search the report by product.
    identifier = models.CharField(_("المعرّف"), max_length=64, blank=True, db_index=True)

    class Meta:
        verbose_name = _("خطأ صف")
        verbose_name_plural = _("أخطاء الصفوف")
        ordering = ["sheet", "row_number", "column"]
        indexes = [models.Index(fields=["job", "sheet", "row_number"])]

    def __str__(self):
        return f"{self.sheet}:{self.row_number} · {self.column}"
