"""
The error report — **a file the admin fixes and uploads again.**

⚠️  Not a list of error messages. The failing rows themselves, with their
    original values, plus one extra column saying what is wrong with each.

    A JSON array of three thousand errors is unreadable, and a spreadsheet of
    "row 4,812 · column · message" makes the admin scroll a ten-thousand-row
    source file hunting for row 4,812 three thousand times. Handing back the bad
    rows as a valid import file collapses the whole loop: fix in place, upload,
    done.

⚠️  Which is why it carries the header row **and the hidden key row**.

    The report is a template. Stripping them would make the corrected file
    unreadable to the importer that produced it — and the admin would have to
    copy their fixes back into the original by hand, which is the error-prone
    step this file exists to remove.
"""

from __future__ import annotations

import io
from collections import defaultdict

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from imports import spec
from imports.models import ImportJob

_ERROR_FILL = PatternFill("solid", fgColor="C0392B")
_HEADER_FILL = PatternFill("solid", fgColor="1F6F54")
_WHITE_BOLD = Font(color="FFFFFF", bold=True)

#: Beyond this the report stops being a work list and becomes a second problem.
#
# ⚠️  A file where forty thousand rows failed does not need a row-by-row report;
#     it needs one sentence saying the category column is wrong throughout. The
#     cap keeps the download small and the message honest.
MAX_REPORTED_ROWS = 5_000


def build(job: ImportJob) -> bytes:
    """The failing rows of every sheet, ready to correct and re-upload."""
    errors_by_sheet: dict[str, dict[int, list[str]]] = defaultdict(lambda: defaultdict(list))

    for sheet, row_number, column, message in job.errors.values_list(
        "sheet", "row_number", "column", "message"
    ):
        label = f"{column}: {message}" if column else message
        errors_by_sheet[sheet][row_number].append(label)

    workbook = Workbook()
    workbook.remove(workbook.active)

    _write_summary(workbook, job, errors_by_sheet)

    for sheet_name in (spec.Sheet.PRODUCTS, spec.Sheet.VARIANTS, spec.Sheet.STOCK):
        rows = errors_by_sheet.get(sheet_name)
        if rows:
            _write_failed_rows(workbook, job, sheet_name, rows)

    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()


def _write_summary(workbook: Workbook, job: ImportJob, errors_by_sheet: dict) -> None:
    worksheet = workbook.create_sheet("الملخّص")
    worksheet.sheet_view.rightToLeft = True
    worksheet.column_dimensions["A"].width = 46
    worksheet.column_dimensions["B"].width = 18

    total_rows = sum(len(rows) for rows in errors_by_sheet.values())

    # ⚠️  A dry run writes nothing, and its counters are predictions. Labelling
    #     them "created" produces a report saying 1,197 products were imported
    #     when the catalogue is untouched — and the admin stops looking for them.
    from imports.models import ImportStatus

    dry = job.status in (ImportStatus.VALIDATED, ImportStatus.REJECTED, ImportStatus.VALIDATING)
    lines = [
        ("تقرير أخطاء الاستيراد", ""),
        ("الملف", job.original_filename),
        ("الحالة", job.get_status_display()),
        ("صفوف بها أخطاء", total_rows),
        ("سيُنشأ" if dry else "تمّ إنشاؤه", job.created_count),
        ("سيُحدَّث" if dry else "تمّ تحديثه", job.updated_count),
        ("", ""),
        ("صحّح الصفوف في الأوراق التالية ثم ارفع هذا الملف نفسه.", ""),
        ("عمود «أخطاء الصف» يُتجاهَل عند الرفع — لا تحذفه ولا تملأه.", ""),
    ]

    for row, (label, value) in enumerate(lines, start=1):
        cell = worksheet.cell(row=row, column=1, value=label)
        cell.font = Font(bold=row == 1, size=13 if row == 1 else 11)
        if value != "":
            worksheet.cell(row=row, column=2, value=value)

    # ⚠️  The most frequent message, named explicitly.
    #
    #     Three thousand failures are almost never three thousand problems —
    #     they are one wrong column repeated. Saying which one turns an
    #     afternoon of row-by-row correction into a find-and-replace.
    counts: dict[str, int] = defaultdict(int)
    for rows in errors_by_sheet.values():
        for messages in rows.values():
            for message in messages:
                counts[message.split(":")[0]] += 1

    if counts:
        row = len(lines) + 2
        worksheet.cell(row=row, column=1, value="أكثر الأعمدة تكرارًا في الأخطاء").font = _WHITE_BOLD
        worksheet.cell(row=row, column=1).fill = _HEADER_FILL
        worksheet.cell(row=row, column=2).fill = _HEADER_FILL
        for offset, (column, count) in enumerate(
            sorted(counts.items(), key=lambda pair: -pair[1])[:10], start=1
        ):
            worksheet.cell(row=row + offset, column=1, value=column)
            worksheet.cell(row=row + offset, column=2, value=count)


def _write_failed_rows(
    workbook: Workbook, job: ImportJob, sheet_name: str, failed: dict[int, list[str]]
) -> None:
    """
    Copy the original rows that failed, verbatim, and append their errors.

    ⚠️  Verbatim matters. Re-serialising the coerced value would hand back
        `2027-06-30` where the admin typed `30/6/2027`, or `123` where they
        typed `00123` — and they would be looking for a mistake in a cell that
        no longer shows what they wrote.
    """
    columns = spec.columns_for(sheet_name)
    source = load_workbook(job.file, read_only=True, data_only=True)
    try:
        if sheet_name not in source.sheetnames:
            return

        worksheet = workbook.create_sheet(sheet_name)
        worksheet.sheet_view.rightToLeft = True

        raw_rows = source[sheet_name].iter_rows(values_only=True)
        header_cells = next(raw_rows, ()) or ()
        key_cells = next(raw_rows, ()) or ()

        width = max(len(header_cells), len(columns))
        error_column = width + 1

        for position in range(1, width + 1):
            value = header_cells[position - 1] if position <= len(header_cells) else None
            cell = worksheet.cell(row=spec.HEADER_ROW, column=position, value=value)
            cell.fill = _HEADER_FILL
            cell.font = _WHITE_BOLD
            worksheet.cell(
                row=spec.KEY_ROW,
                column=position,
                value=key_cells[position - 1] if position <= len(key_cells) else None,
            )
            if position - 1 < len(columns):
                worksheet.column_dimensions[get_column_letter(position)].width = columns[
                    position - 1
                ].width

        marker = worksheet.cell(row=spec.HEADER_ROW, column=error_column, value="أخطاء الصف")
        marker.fill = _ERROR_FILL
        marker.font = _WHITE_BOLD
        worksheet.cell(row=spec.KEY_ROW, column=error_column, value="_errors")
        worksheet.column_dimensions[get_column_letter(error_column)].width = 70
        worksheet.row_dimensions[spec.KEY_ROW].hidden = True
        worksheet.freeze_panes = "A3"

        out = spec.FIRST_DATA_ROW
        for offset, cells in enumerate(raw_rows):
            if not cells or all(cell in (None, "") for cell in cells):
                continue

            number = spec.FIRST_DATA_ROW + offset
            messages = failed.get(number)
            if not messages:
                continue

            for position, value in enumerate(cells[:width], start=1):
                worksheet.cell(row=out, column=position, value=value)

            note = worksheet.cell(row=out, column=error_column, value=" · ".join(messages))
            note.font = Font(color="C0392B")
            note.alignment = Alignment(wrap_text=True, vertical="top")

            out += 1
            if out - spec.FIRST_DATA_ROW >= MAX_REPORTED_ROWS:
                worksheet.cell(
                    row=out,
                    column=1,
                    value=f"— توقّف التقرير عند {MAX_REPORTED_ROWS:,} صف —",
                ).font = Font(bold=True, color="C0392B")
                break
    finally:
        source.close()
