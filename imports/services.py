"""
The runner — one chunk of work per call, resumable from the database.

⚠️  **Nothing here runs to completion in a single call, and that is the design.**

    There is no queue (ADR-42) and Passenger kills a long request. So the unit
    of work is a chunk: read the file from the cursor, do a few hundred rows in
    one transaction, write the counters down, return. Whoever calls again picks
    up exactly where this stopped.

    Three callers exist and they are interchangeable:

        the admin's browser   →  a loop against POST .../advance/   (live progress)
        run_periodic          →  a safety net for abandoned jobs
        a management command  →  the terminal, for the first big load

⚠️  And **each chunk commits on its own.**

    One transaction around ten thousand rows holds locks on ten thousand
    products while the shop is selling them, and rolls back four minutes of work
    because row 9,880 had a bad date. Per-chunk commits mean a partial result —
    which is a state the model names (`PARTIAL`) rather than an accident.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from catalog.models import Product, ProductVariant
from core.errors import BusinessError, ErrorCode
from core.identifiers import random_code
from core.models.audit import AuditAction, AuditLog
from imports import reader, references, spec, validators
from imports.models import (
    ADVANCEABLE,
    PHASE_ORDER,
    ImportJob,
    ImportPhase,
    ImportRowError,
    ImportStatus,
)
from inventory import services as inventory_services
from inventory.models import StockLocation

logger = logging.getLogger(__name__)

#: A job whose heartbeat is older than this is considered abandoned by its browser.
#
# ⚠️  Not a timeout on the work — a chunk takes seconds. It is how the periodic
#     runner tells "the admin is actively driving this" from "the laptop closed
#     at row four thousand". Too short and cron races the browser for the same
#     chunk; too long and a stalled import waits an hour for its rescue.
ABANDONED_AFTER = timedelta(minutes=3)


# ═══════════════════════════════════════════════════════════
#  Creating a job
# ═══════════════════════════════════════════════════════════


def file_digest(uploaded_file) -> str:
    """
    SHA-256 of the uploaded bytes, read in blocks.

    ⚠️  `uploaded_file.read()` in one go pulls a twenty-megabyte file into memory
        beside the copy Django is already holding. And the seek back to zero is
        not optional — without it the file that gets saved is empty, which
        surfaces as "the sheet has no rows" long after the upload succeeded.
    """
    digest = hashlib.sha256()
    for block in uploaded_file.chunks(chunk_size=64 * 1024):
        digest.update(block)
    uploaded_file.seek(0)
    return digest.hexdigest()


def create_job(
    uploaded_file,
    *,
    mode: str,
    actor=None,
    create_missing_brands: bool = False,
) -> ImportJob:
    """
    Store the file and record its shape. **Nothing is validated row by row here.**

    ⚠️  The shape check happens before the job is saved, and it is worth the
        double open: a file with no `products` sheet, or one missing `sku`, is a
        mistake the admin fixes in ten seconds — and making them wait through a
        dry run of ten thousand rows to be told the sheet is named `Sheet1` is
        the difference between a tool they use and one they avoid.
    """
    if uploaded_file.size > spec.MAX_FILE_BYTES:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            detail=f"حجم الملف يتجاوز {spec.MAX_FILE_BYTES // (1024 * 1024)} ميجابايت",
        )

    digest = file_digest(uploaded_file)

    try:
        shapes = reader.inspect(
            uploaded_file,
            {name: spec.required_keys_for(name, mode) for name in spec.SHEETS},
        )
    except Exception as exc:
        logger.warning("import: unreadable upload (%s)", exc)
        raise BusinessError(ErrorCode.IMPORT_FILE_UNREADABLE) from exc
    finally:
        uploaded_file.seek(0)

    products = shapes[spec.Sheet.PRODUCTS]
    if not products.present:
        raise BusinessError(
            ErrorCode.IMPORT_SHEET_MISSING,
            detail="الملف لا يحتوي على ورقة باسم «products» — نزّل القالب وانسخ بياناتك فيه",
        )

    missing = {
        name: shape.missing_required
        for name, shape in shapes.items()
        if shape.present and shape.missing_required
    }
    if missing:
        described = "؛ ".join(
            f"{name}: {'، '.join(keys)}" for name, keys in missing.items()
        )
        raise BusinessError(ErrorCode.IMPORT_COLUMN_MISSING, detail=described)

    row_counts = {
        name: shape.row_count for name, shape in shapes.items() if shape.present and shape.row_count
    }
    total = sum(row_counts.values())
    if total == 0:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR, detail="الملف لا يحتوي على أي صف بيانات"
        )
    if max(row_counts.values()) > spec.MAX_ROWS_PER_FILE:
        raise BusinessError(
            ErrorCode.IMPORT_TOO_MANY_ROWS,
            detail=f"الحد {spec.MAX_ROWS_PER_FILE:,} صف للورقة الواحدة — قسّم الملف",
        )

    job = ImportJob.objects.create(
        file=uploaded_file,
        original_filename=getattr(uploaded_file, "name", "")[:255],
        file_hash=digest,
        mode=mode,
        status=ImportStatus.UPLOADED,
        row_counts=row_counts,
        started_by=actor,
        create_missing_brands=create_missing_brands,
    )

    # ⚠️  The columns actually present are recorded now, while the file is open.
    #
    #     On an update pass, a column **absent from the sheet** must leave the
    #     stored value alone, while a column present and empty must clear it.
    #     Without this record the two are indistinguishable, and an update-only
    #     import of a price list wipes every description in the catalogue.
    job.preview = {
        "present_columns": {
            name: sorted(shape.index.keys()) for name, shape in shapes.items() if shape.present
        }
    }
    job.save(update_fields=["preview"])

    return job


def earlier_import_of(job: ImportJob) -> ImportJob | None:
    """
    The last completed job that used this exact file.

    ⚠️  Reported, never enforced. Re-running a file is legitimate — a run that
        failed halfway, a corrected category tree. What is not legitimate is
        doing it **without knowing**, which on `UPSERT` silently rewrites every
        row with data the admin believed they had already replaced.
    """
    if not job.file_hash:
        return None
    return (
        ImportJob.objects.filter(
            file_hash=job.file_hash,
            status__in=[ImportStatus.DONE, ImportStatus.PARTIAL],
        )
        .exclude(pk=job.pk)
        .order_by("-created_at")
        .first()
    )


# ═══════════════════════════════════════════════════════════
#  Phase plumbing
# ═══════════════════════════════════════════════════════════

_PHASE_SHEET = {
    ImportPhase.PRODUCTS: spec.Sheet.PRODUCTS,
    ImportPhase.VARIANTS: spec.Sheet.VARIANTS,
    ImportPhase.STOCK: spec.Sheet.STOCK,
}

_PHASE_CHUNK = {
    ImportPhase.PRODUCTS: spec.PRODUCT_CHUNK_SIZE,
    ImportPhase.VARIANTS: spec.PRODUCT_CHUNK_SIZE,
    ImportPhase.STOCK: spec.STOCK_CHUNK_SIZE,
}


def _rows_in_phase(job: ImportJob) -> int:
    sheet = _PHASE_SHEET.get(job.phase)
    return int((job.row_counts or {}).get(sheet, 0)) if sheet else 0


def _next_phase(job: ImportJob) -> str:
    """
    Advance to the next phase that actually has rows.

    ⚠️  Skipping empty phases matters more than it looks: a file with no
        `variants` sheet would otherwise spend a call moving through a phase
        with nothing in it, and the progress bar stalls at a number that never
        changes while the admin watches.
    """
    remaining = PHASE_ORDER[PHASE_ORDER.index(job.phase) + 1 :]
    for phase in remaining:
        if int((job.row_counts or {}).get(_PHASE_SHEET[phase], 0)):
            return phase
    return ImportPhase.FINISHED


def _present(job: ImportJob, sheet: str) -> set[str]:
    return set((job.preview or {}).get("present_columns", {}).get(sheet, []))


def _record_errors(job: ImportJob, errors: list[validators.RowError]) -> None:
    if not errors:
        return
    ImportRowError.objects.bulk_create(
        [
            ImportRowError(
                job=job,
                sheet=error.sheet,
                row_number=error.row_number,
                column=error.column[:64],
                value=str(error.value)[:200],
                message=error.message,
                identifier=str(error.identifier)[:64],
            )
            for error in errors
        ],
        batch_size=500,
    )


# ═══════════════════════════════════════════════════════════
#  The dry run
# ═══════════════════════════════════════════════════════════


def start_validation(job: ImportJob) -> ImportJob:
    """Reset the cursors and clear any previous report, then hand over to `advance`."""
    if job.status in (ImportStatus.RUNNING, ImportStatus.VALIDATING):
        raise BusinessError(ErrorCode.IMPORT_ALREADY_RUNNING)
    if job.is_terminal and job.status != ImportStatus.REJECTED:
        raise BusinessError(
            ErrorCode.CONFLICT, detail="هذه الوظيفة انتهت — ارفع الملف من جديد", status_code=409
        )

    # ⚠️  The previous report is deleted, not appended to. A second dry run after
    #     the admin fixed the catalogue must not still show the errors they fixed.
    job.errors.all().delete()

    preview = dict(job.preview or {})
    preview.pop("summary", None)
    preview["duplicates"] = _scan_duplicates(job)

    job.touch(
        status=ImportStatus.VALIDATING,
        phase=_first_nonempty(job),
        cursor=0,
        created_count=0,
        updated_count=0,
        skipped_count=0,
        failed_count=0,
        preview=preview,
        error_message="",
        started_at=timezone.now(),
        finished_at=None,
    )
    return job


def _scan_duplicates(job: ImportJob) -> dict[str, list[str]]:
    """
    One pass over the identifier columns alone, before any chunk runs.

    ⚠️  **A duplicate SKU inside the file cannot be caught chunk by chunk.**

        Each chunk only sees its own five hundred rows, so the same code at row
        40 and row 7,000 passes both times: the first chunk finds nothing in the
        database because nothing is written yet, and the second finds nothing
        because it never saw the first. The dry run then promises ten thousand
        products and the execution delivers 9,999 — or, on `CREATE_ONLY`, fails
        at row 7,000 on an error the preview swore was not there.

        So the identifiers are scanned once, up front. Reading a single column of
        fifty thousand rows in read-only mode costs a couple of seconds and a set
        of strings, and it turns the whole class of duplicate errors into
        something the admin sees before they commit to anything.

    ⚠️  And **every** occurrence is rejected, not the later ones.

        Which of two rows carrying `MED-0001` is the intended one is a question
        only the admin can answer, and picking the first silently imports
        whichever happened to be pasted higher.
    """
    duplicates: dict[str, list[str]] = {}

    for sheet, key in ((spec.Sheet.PRODUCTS, "sku"), (spec.Sheet.VARIANTS, "sku")):
        if not int((job.row_counts or {}).get(sheet, 0)):
            continue

        seen: set[str] = set()
        repeated: set[str] = set()
        for row in reader.read_rows(job.file, sheet):
            value = str(row.get(key) or "").strip()
            if not value:
                continue
            if value in seen:
                repeated.add(value)
            seen.add(value)

        if repeated:
            duplicates[sheet] = sorted(repeated)

    return duplicates


def _duplicates_for(job: ImportJob, sheet: str) -> set[str]:
    return set((job.preview or {}).get("duplicates", {}).get(sheet, []))


def _file_product_skus(job: ImportJob) -> set[str]:
    """
    Every SKU the `products` sheet carries — **for the dry run only.**

    ⚠️  Without this the preview is worthless on any file that carries stock.

        The phases run products → variants → stock, and a dry run writes
        nothing. So by the time the stock phase validates row 1, the product it
        names does not exist in the database and never will until execution —
        and every single stock line came back "no product with this code". A
        preview that rejects a correct file teaches the admin to skip previews.

        The execution has no such problem: by then the products phase has
        actually committed, and the ordinary database lookup is the truth.

    ⚠️  Memoised on the instance, not on the row.

        Fifty thousand SKUs is most of a megabyte, and re-reading that out of a
        `JSONField` once per chunk costs more than the scan it saves. Within one
        process — the management command, or a request handling several chunks —
        this pays once; across requests it pays per call, and a single-column
        read-only scan is a fraction of the chunk it precedes.
    """
    cached = getattr(job, "_file_skus", None)
    if cached is not None:
        return cached

    skus = {
        str(row.get("sku") or "").strip()
        for row in reader.read_rows(job.file, spec.Sheet.PRODUCTS, only=frozenset({"sku"}))
    }
    skus.discard("")
    job._file_skus = skus
    return skus


def _file_variant_skus(job: ImportJob) -> set[str]:
    """The `variants` sheet's own codes — the same dry-run problem, one sheet over."""
    cached = getattr(job, "_file_variant_skus_cache", None)
    if cached is not None:
        return cached

    skus = {
        str(row.get("sku") or "").strip()
        for row in reader.read_rows(job.file, spec.Sheet.VARIANTS, only=frozenset({"sku"}))
    }
    skus.discard("")
    job._file_variant_skus_cache = skus
    return skus


def _rows_in_phase_for(job: ImportJob, phase: str) -> int:
    return int((job.row_counts or {}).get(_PHASE_SHEET[phase], 0))


def _first_nonempty(job: ImportJob) -> str:
    for phase in PHASE_ORDER:
        if _rows_in_phase_for(job, phase):
            return phase
    return ImportPhase.FINISHED


def start_execution(job: ImportJob) -> ImportJob:
    """
    ⚠️  Only from `VALIDATED`. There is no "just run it" path, deliberately.

        The dry run costs one pass over a file that is about to get three, and
        it is the only moment where a mistake is free. Allowing execution from
        `UPLOADED` would make it optional, and an optional safety step on ten
        thousand rows is a safety step nobody takes.
    """
    if job.status == ImportStatus.RUNNING:
        raise BusinessError(ErrorCode.IMPORT_ALREADY_RUNNING)
    if job.status != ImportStatus.VALIDATED:
        raise BusinessError(ErrorCode.IMPORT_NOT_VALIDATED)

    job.touch(
        status=ImportStatus.RUNNING,
        phase=_first_nonempty(job),
        cursor=0,
        created_count=0,
        updated_count=0,
        skipped_count=0,
        failed_count=0,
        started_at=timezone.now(),
    )
    job.errors.all().delete()
    return job


# ═══════════════════════════════════════════════════════════
#  One chunk
# ═══════════════════════════════════════════════════════════


def advance(job: ImportJob) -> ImportJob:
    """
    Do one chunk of whatever this job is currently doing, and return it updated.

    Safe to call on a finished job — it returns immediately, which is what makes
    the browser loop and the periodic runner able to race without coordination.
    """
    if job.status not in ADVANCEABLE:
        return job

    if job.phase == ImportPhase.FINISHED:
        return _finish(job)

    dry_run = job.status == ImportStatus.VALIDATING

    try:
        handled = _run_chunk(job, dry_run=dry_run)
    except Exception as exc:
        logger.exception("import job %s failed in phase %s", job.pk, job.phase)
        job.touch(
            status=ImportStatus.FAILED,
            error_message=f"{type(exc).__name__}: {exc}"[:2000],
            finished_at=timezone.now(),
        )
        return job

    cursor = job.cursor + handled
    if cursor >= _rows_in_phase(job) or handled == 0:
        job.touch(phase=_next_phase(job), cursor=0)
    else:
        job.touch(cursor=cursor)

    if job.phase == ImportPhase.FINISHED:
        return _finish(job)

    return job


def _finish(job: ImportJob) -> ImportJob:
    if job.status == ImportStatus.VALIDATING:
        summary = {
            "will_create": job.created_count,
            "will_update": job.updated_count,
            "rejected": job.failed_count,
        }
        preview = dict(job.preview or {})
        preview["summary"] = summary

        # ⚠️  A file with a single bad row is `REJECTED`, not `VALIDATED`.
        #
        #     The alternative — letting it through and dropping the bad rows —
        #     is how an import of 9,999 products quietly loses one that mattered.
        #     The admin fixes the row and validates again; the cost is a click,
        #     and the gain is that "ready" means all of it.
        status = ImportStatus.REJECTED if job.failed_count else ImportStatus.VALIDATED
        job.touch(
            status=status,
            phase=ImportPhase.FINISHED,
            preview=preview,
            finished_at=timezone.now(),
        )
        return job

    status = ImportStatus.PARTIAL if job.failed_count else ImportStatus.DONE
    job.touch(status=status, phase=ImportPhase.FINISHED, finished_at=timezone.now())

    # ⚠️  **One** audit entry for the whole job, not one per product.
    #
    #     Ten thousand `AuditLog` rows for a single deliberate act buries every
    #     other entry of that day, and answers no question the counters here do
    #     not already answer.
    AuditLog.objects.create(
        actor=job.started_by,
        action=AuditAction.CREATE,
        object_repr=f"استيراد جماعي {job.original_filename}"[:200],
        changes={
            "job": str(job.pk),
            "mode": job.mode,
            "created": job.created_count,
            "updated": job.updated_count,
            "failed": job.failed_count,
        },
    )
    return job


def _run_chunk(job: ImportJob, *, dry_run: bool) -> int:
    """Returns how many rows were consumed. Zero means the phase is exhausted."""
    sheet = _PHASE_SHEET[job.phase]
    limit = _PHASE_CHUNK[job.phase]

    rows = list(reader.read_rows(job.file, sheet, start=job.cursor, limit=limit))
    if not rows:
        return 0

    data = references.load()

    if job.phase == ImportPhase.PRODUCTS:
        _chunk_products(job, rows, data, dry_run=dry_run)
    elif job.phase == ImportPhase.VARIANTS:
        _chunk_variants(job, rows, dry_run=dry_run)
    else:
        _chunk_stock(job, rows, data, dry_run=dry_run)

    return len(rows)


# ═══════════════════════════════════════════════════════════
#  products
# ═══════════════════════════════════════════════════════════

#: Column key → model attribute. Anything absent maps to itself.
_PRODUCT_FIELD = {
    "category_path": "category_id",
    "brand_slug": "brand_id",
    "manufacturer_slug": "manufacturer_id",
    "tax_class_code": "tax_class_id",
    "access_policy_code": "access_policy_id",
}


def _create_missing_partners(job, rows, data) -> bool:
    """
    Create the brands and manufacturers this chunk names but the catalogue lacks.

    ⚠️  **Off by default, and this is the one place it earns being an option.**

        A first load of ten thousand items from a distributor names two hundred
        brands, none of which exist yet. Without this the admin creates two
        hundred brands by hand before their first import — which is the moment
        most people give up on the feature. With it left on permanently, a typo
        creates «Pfzier» beside «Pfizer» and nobody notices until a customer
        filters by brand and sees two.

        So it is a deliberate choice made per file, and the safe answer is the
        default.

    ⚠️  Created **one at a time**, never `bulk_create`.

        `SlugMixin.save` is what generates the slug, and there are at most a few
        hundred of these against ten thousand products — the cost is nothing and
        the alternative is hand-rolling slug generation for a second model.

    ⚠️  And **categories are not in this list.**

        A category carries a materialised path that is rebuilt for every
        descendant beneath it, and inventing one from a spreadsheet cell puts an
        unreviewed node into the store's public menu tree. There is no safe
        default for that, so there is no option for it.
    """
    if not job.create_missing_brands:
        return False

    from catalog.models import Brand, Manufacturer

    created = False
    for key, table, names, model in (
        ("brand_slug", data.brands, data.brand_names, Brand),
        ("manufacturer_slug", data.manufacturers, data.manufacturer_names, Manufacturer),
    ):
        wanted = {
            str(row.get(key) or "").strip()
            for row in rows
            if str(row.get(key) or "").strip()
        }
        missing = {
            value for value in wanted if value not in table and value.casefold() not in names
        }
        for value in sorted(missing):
            # ⚠️  The cell fills **both** languages (ADR-34). A brand with a blank
            #     English name renders as an empty string on the English store,
            #     which reads as a missing product rather than a missing translation.
            record = model.objects.create(name_ar=value, name_en=value)
            table[record.slug] = record.pk
            names[value.casefold()] = record.pk
            created = True

    return created


def _predict_missing_partners(job, rows, data) -> None:
    """
    Mark the brands the file would create, **without creating them**.

    ⚠️  A preview that creates two hundred brands is not a preview.

        But rejecting those rows is not right either: the admin turned the
        option on precisely so those brands would be made, and execution is only
        reachable from a preview that passed — so an error here would make the
        option impossible to use at all.

        The middle answer is a seeded key with no id. `validators._resolve`
        tests membership rather than the value, so the row validates, nothing is
        written, and the summary counts it as a product that will be created.
    """
    if not job.create_missing_brands:
        return

    for key, table, names in (
        ("brand_slug", data.brands, data.brand_names),
        ("manufacturer_slug", data.manufacturers, data.manufacturer_names),
    ):
        for row in rows:
            value = str(row.get(key) or "").strip()
            if value and value not in table and value.casefold() not in names:
                names[value.casefold()] = None


def _chunk_products(job, rows, data, *, dry_run: bool) -> None:
    # ⚠️  Before validation, because both passes need the reference maps to
    #     already reflect what the option promises.
    if dry_run:
        _predict_missing_partners(job, rows, data)
    else:
        _create_missing_partners(job, rows, data)

    skus = [str(row.get("sku") or "").strip() for row in rows]
    skus = [sku for sku in skus if sku]

    # ⚠️  `all_objects` — soft-deleted products included.
    #
    #     `sku` is unique across the whole table, deleted rows and all. Looking
    #     only at the living ones makes a re-imported code look new, and the
    #     insert dies on a unique violation that names a product the admin
    #     cannot see anywhere in the panel.
    existing = dict(
        Product.all_objects.filter(sku__in=skus).values_list("sku", "id")
    )

    result = validators.validate_products(
        rows,
        data,
        mode=job.mode,
        existing_skus=existing,
        duplicate_skus=_duplicates_for(job, spec.Sheet.PRODUCTS),
    )

    _record_errors(job, result.errors)

    if dry_run:
        job.touch(
            created_count=job.created_count + result.created,
            updated_count=job.updated_count + result.updated,
            failed_count=job.failed_count + len({e.row_number for e in result.errors}),
        )
        return

    creates = [row for row in result.clean if row.action == "CREATE"]
    updates = [row for row in result.clean if row.action == "UPDATE"]

    with transaction.atomic():
        created = _create_products(creates)
        updated = _update_products(job, updates, existing)

    job.touch(
        created_count=job.created_count + created,
        updated_count=job.updated_count + updated,
        failed_count=job.failed_count + len({e.row_number for e in result.errors}),
    )


def _create_products(clean_rows) -> int:
    """
    ⚠️  `bulk_create`, which means **`save()` never runs** — and `SlugMixin.save`
        is what fills the slug. So the slugs are built here, in memory, before
        the insert.

        The alternative is `unique_slug()` per row, and that helper does an
        `.exists()` query every time it is called: ten thousand round trips to
        answer a question one `IN` query answers for the whole chunk.
    """
    if not clean_rows:
        return 0

    candidates: dict[int, str] = {}
    for position, row in enumerate(clean_rows):
        source = row.values.get("name_en") or row.values.get("name_ar") or row.identifier
        candidates[position] = slugify(str(source), allow_unicode=True) or "item"

    taken = set(
        Product.all_objects.filter(slug__in=set(candidates.values())).values_list("slug", flat=True)
    )

    objects = []
    for position, row in enumerate(clean_rows):
        slug = candidates[position]
        if slug in taken:
            # ⚠️  The same suffix `unique_slug` uses, for the same reason: a
            #     counter would need to know how many exist, which is another
            #     query, and two workers would pick the same number anyway.
            slug = f"{slug}-{random_code(5).lower()}"
        taken.add(slug)

        objects.append(Product(slug=slug, **row.values))

    Product.objects.bulk_create(objects, batch_size=spec.PRODUCT_CHUNK_SIZE)
    return len(objects)


def _update_products(job, clean_rows, existing: dict) -> int:
    """
    ⚠️  Only the columns **present in the sheet** are written.

        A price-list update carries `sku` and `base_price` and nothing else. If
        every field were applied, the missing columns would arrive as empty
        strings and blank every description, ingredient and SEO title in the
        catalogue — an "update" that destroys more than it changes.

    ⚠️  And `slug` is never touched (ADR-27). A renamed product keeps its URL.
    """
    if not clean_rows:
        return 0

    present = _present(job, spec.Sheet.PRODUCTS)
    fields = sorted({_PRODUCT_FIELD.get(key, key) for key in present} - {"sku", "slug"})
    if not fields:
        return 0

    by_sku = {
        product.sku: product
        for product in Product.all_objects.filter(
            pk__in=[existing[row.identifier] for row in clean_rows if row.identifier in existing]
        )
    }

    changed = []
    for row in clean_rows:
        product = by_sku.get(row.identifier)
        if product is None:
            continue
        for attribute in fields:
            if attribute in row.values:
                setattr(product, attribute, row.values[attribute])
        changed.append(product)

    if changed:
        # ⚠️  `all_objects`, matching the queryset the rows were fetched through.
        #     `objects` filters the soft-deleted out, so an update touching a
        #     deleted product would report success and write nothing.
        Product.all_objects.bulk_update(changed, fields, batch_size=spec.PRODUCT_CHUNK_SIZE)
    return len(changed)


# ═══════════════════════════════════════════════════════════
#  variants
# ═══════════════════════════════════════════════════════════


def _chunk_variants(job, rows, *, dry_run: bool) -> None:
    parent_skus = {str(row.get("parent_sku") or "").strip() for row in rows}
    variant_skus = {str(row.get("sku") or "").strip() for row in rows}
    parent_skus.discard("")
    variant_skus.discard("")

    known = dict(
        Product.all_objects.filter(sku__in=parent_skus | variant_skus).values_list("sku", "id")
    )
    existing_variants = set(
        ProductVariant.all_objects.filter(sku__in=variant_skus).values_list("sku", flat=True)
    )

    if dry_run:
        # ⚠️  A parent created by the products sheet of this very file counts as
        #     existing — see `_file_product_skus`. The id is `None` because there
        #     is none yet, and nothing is written on a dry run.
        for sku in _file_product_skus(job) & (parent_skus | variant_skus):
            known.setdefault(sku, None)

    result = validators.validate_variants(
        rows,
        known_skus=known,
        existing_variant_skus=existing_variants,
        duplicate_skus=_duplicates_for(job, spec.Sheet.VARIANTS),
    )
    _record_errors(job, result.errors)

    failed_rows = len({e.row_number for e in result.errors})

    if dry_run:
        job.touch(
            created_count=job.created_count + result.created,
            updated_count=job.updated_count + result.updated,
            failed_count=job.failed_count + failed_rows,
        )
        return

    creates = [row for row in result.clean if row.action == "CREATE"]
    updates = [row for row in result.clean if row.action == "UPDATE"]

    with transaction.atomic():
        if creates:
            ProductVariant.objects.bulk_create(
                [ProductVariant(**row.values) for row in creates],
                batch_size=spec.PRODUCT_CHUNK_SIZE,
            )

        updated = 0
        if updates:
            present = _present(job, spec.Sheet.VARIANTS)
            fields = sorted(present - {"sku", "parent_sku"})
            by_sku = {
                variant.sku: variant
                for variant in ProductVariant.all_objects.filter(
                    sku__in=[row.identifier for row in updates]
                )
            }
            changed = []
            for row in updates:
                variant = by_sku.get(row.identifier)
                if variant is None:
                    continue
                for attribute in fields:
                    if attribute in row.values:
                        setattr(variant, attribute, row.values[attribute])
                changed.append(variant)
            if changed and fields:
                ProductVariant.all_objects.bulk_update(changed, fields, batch_size=500)
            updated = len(changed)

    job.touch(
        created_count=job.created_count + len(creates),
        updated_count=job.updated_count + updated,
        failed_count=job.failed_count + failed_rows,
    )


# ═══════════════════════════════════════════════════════════
#  stock
# ═══════════════════════════════════════════════════════════


def _chunk_stock(job, rows, data, *, dry_run: bool) -> None:
    """
    ⚠️  **Every line goes through `inventory.services.receive`, one at a time.**

        Writing `Stock.quantity_physical` directly would be a hundred times
        faster and would produce stock nobody can account for: no `Batch`, so no
        expiry and no cost; no `StockMovement`, so the ledger and the balance
        disagree from the first row. `suppliers` carries the same warning in its
        own words — there is one way into stock.

    ⚠️  And each line gets **its own savepoint**.

        One product whose location was deleted mid-import must not roll back the
        199 rows beside it — the chunk would then be retried and fail again on
        the same row, forever.
    """
    skus = {str(row.get("sku") or "").strip() for row in rows}
    skus.discard("")
    variant_skus = {str(row.get("variant_sku") or "").strip() for row in rows}
    variant_skus.discard("")

    known = dict(Product.objects.filter(sku__in=skus).values_list("sku", "id"))
    known_variants = dict(
        ProductVariant.objects.filter(sku__in=variant_skus).values_list("sku", "id")
    )

    if dry_run:
        for sku in _file_product_skus(job) & skus:
            known.setdefault(sku, None)
        # ⚠️  Variants declared in the same file are equally legitimate here.
        for sku in _file_variant_skus(job) & variant_skus:
            known_variants.setdefault(sku, None)

    result = validators.validate_stock(
        rows, data, known_skus=known, known_variant_skus=known_variants
    )
    _record_errors(job, result.errors)

    failed_rows = len({e.row_number for e in result.errors})

    if dry_run:
        job.touch(
            created_count=job.created_count + result.created,
            failed_count=job.failed_count + failed_rows,
        )
        return

    # ⚠️  `None` is filtered out rather than passed through. It cannot occur on a
    #     real run — the products phase committed first — but `in_bulk` raises on
    #     a null key rather than ignoring it, and a crash here would fail a whole
    #     chunk over one row that the loop below reports cleanly on its own.
    products = Product.objects.in_bulk(
        [row.values["product_id"] for row in result.clean if row.values["product_id"]]
    )
    variants = ProductVariant.objects.in_bulk(
        [row.values["variant_id"] for row in result.clean if row.values["variant_id"]]
    )
    locations = StockLocation.objects.in_bulk(
        [row.values["location_id"] for row in result.clean if row.values["location_id"]]
    )
    default_location = StockLocation.get_default()

    received = 0
    late_errors: list[validators.RowError] = []

    for row in result.clean:
        product = products.get(row.values["product_id"])
        if product is None:
            late_errors.append(
                validators.RowError(
                    sheet=spec.Sheet.STOCK,
                    row_number=row.number,
                    message="المنتج غير موجود عند التنفيذ — ربما حُذف أثناء الاستيراد",
                    identifier=row.identifier,
                )
            )
            continue

        try:
            with transaction.atomic():
                inventory_services.receive(
                    product,
                    row.values["quantity"],
                    row.values["unit_cost"],
                    location=locations.get(row.values["location_id"]) or default_location,
                    variant=variants.get(row.values["variant_id"]),
                    expires_at=row.values["expires_at"],
                    supplier_batch_number=row.values["supplier_batch_number"],
                    performed_by=job.started_by,
                )
            received += 1
        except Exception as exc:
            late_errors.append(
                validators.RowError(
                    sheet=spec.Sheet.STOCK,
                    row_number=row.number,
                    message=f"فشل استلام الدفعة: {exc}"[:500],
                    identifier=row.identifier,
                )
            )

    _record_errors(job, late_errors)

    job.touch(
        created_count=job.created_count + received,
        failed_count=job.failed_count + failed_rows + len(late_errors),
    )


# ═══════════════════════════════════════════════════════════
#  Publishing, cancelling, rescuing
# ═══════════════════════════════════════════════════════════


def publish(job: ImportJob, *, actor=None) -> int:
    """
    Activate everything this job created — the deliberate second step.

    ⚠️  This is why `is_active` defaults to `False` on import. The catalogue
        arrives as a draft that the admin can search, sort and spot-check, and
        becomes a storefront only when they say so. Reversing the order means
        the first thing anyone learns about a bad import is a customer's order.
    """
    if job.status not in (ImportStatus.DONE, ImportStatus.PARTIAL):
        raise BusinessError(
            ErrorCode.CONFLICT, detail="لا يُنشر إلا استيراد مكتمل", status_code=409
        )

    # ⚠️  Scoped by `created_at`, because nothing links a product back to its job.
    #
    #     A foreign key from `catalog.Product` to an import job would make the
    #     catalogue depend on the importer — the exact inversion the layer
    #     contract forbids. The window is the job's own run, which is precise
    #     enough for the one action that needs it.
    if not job.started_at or not job.finished_at:
        return 0

    return Product.objects.filter(
        created_at__gte=job.started_at,
        created_at__lte=job.finished_at,
        is_active=False,
    ).update(is_active=True)


def cancel(job: ImportJob, *, reason: str = "") -> ImportJob:
    """
    ⚠️  Cancelling stops the **remaining** chunks. It does not undo the committed ones.

        Saying otherwise would be a lie: the products are inserted, the batches
        are received and the stock movements are written into a ledger that is
        append-only by design. What cancellation buys is that row 6,000 onwards
        never happens — and the admin publishes nothing.
    """
    if job.is_terminal:
        return job
    job.touch(
        status=ImportStatus.CANCELLED,
        error_message=reason[:2000],
        finished_at=timezone.now(),
    )
    return job


def resume_abandoned(limit: int = 4) -> int:
    """
    The periodic safety net — one chunk each for jobs whose driver went away.

    ⚠️  It advances by **one chunk per job per tick**, not to completion.

        Running a job to the end inside the cron process makes the periodic
        command take minutes and blocks the six other jobs behind it — including
        the mail queue, which is scheduled every few minutes for a reason. One
        chunk per tick finishes a large import over several minutes, unattended,
        and never holds the runner hostage.
    """
    cutoff = timezone.now() - ABANDONED_AFTER
    stalled = ImportJob.objects.filter(
        status__in=[ImportStatus.RUNNING, ImportStatus.VALIDATING],
        heartbeat_at__lt=cutoff,
    ).order_by("heartbeat_at")[:limit]

    advanced = 0
    for job in stalled:
        logger.info("import: resuming abandoned job %s at %s/%s", job.pk, job.phase, job.cursor)
        advance(job)
        advanced += 1
    return advanced
