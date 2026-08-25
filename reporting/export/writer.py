"""
Writing an export workbook.

⚠️  **Money is written as a number, and dates as dates — not as text.**

    ADR-31 requires money to be a **string in JSON**, because `JSON.parse`
    turns a decimal into a binary double and loses it. In a spreadsheet the
    opposite is required, and for the same underlying reason — fidelity to the
    reader. A column of text does not answer `SUM`, does not sort numerically,
    and shows the green "number stored as text" triangle on every cell. The
    entire purpose of the file is analysis, and a text column defeats it.

    So `Decimal` goes in as a number with a `0.00` format, and a date goes in as
    a real date. The ADR is about JSON transport; this is neither.

⚠️  And the workbook is opened `write_only=True`, always.

    The ordinary mode holds every cell of the sheet as an object until `save()`.
    At the fifty-thousand-row ceiling that is millions of objects on a shared
    host with a hard memory cap — the same reason `imports/reader.py` never
    opens a workbook any way but read-only.
"""

from __future__ import annotations

import datetime as dt
import io
from collections.abc import Iterator
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

#: The ceiling for one file — the same number as `imports.spec.MAX_ROWS_PER_FILE`.
#
# ⚠️  Not an arbitrary round number: an export and an import of the same dataset
#     must agree on what fits in one file, or the round trip breaks at exactly
#     the size where it matters most.
MAX_EXPORT_ROWS = 50_000

_HEADER_FILL = PatternFill("solid", fgColor="1F6F54")
_HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
_META_LABEL = Font(bold=True)
_MUTED = Font(color="9AA5A0")

#: Excel number formats. Written per cell, because a column-wide format does not
#: exist in the file format — Excel fakes it in the UI.
MONEY_FORMAT = "#,##0.00"
INT_FORMAT = "#,##0"
DATE_FORMAT = "yyyy-mm-dd"
DATETIME_FORMAT = "yyyy-mm-dd hh:mm"


class Kind:
    """What a column holds — decides the Excel format, nothing else."""

    TEXT = "text"
    INT = "int"
    MONEY = "money"
    DATE = "date"
    DATETIME = "datetime"
    BOOL = "bool"


_FORMATS = {
    Kind.MONEY: MONEY_FORMAT,
    Kind.INT: INT_FORMAT,
    Kind.DATE: DATE_FORMAT,
    Kind.DATETIME: DATETIME_FORMAT,
}

#: Wider by default for the kinds that hold prose.
_WIDTHS = {
    Kind.TEXT: 24,
    Kind.INT: 12,
    Kind.MONEY: 14,
    Kind.DATE: 13,
    Kind.DATETIME: 17,
    Kind.BOOL: 10,
}


def _coerce(value, kind: str):
    """
    Turn a database value into what Excel should hold.

    ⚠️  `None` stays `None` rather than becoming an empty string.

        An empty cell and a cell holding `""` look identical and behave
        differently: `COUNT` skips the first and counts the second, so a column
        of "how many products have no barcode" comes out wrong by exactly the
        number of rows the export touched.
    """
    if value is None:
        return None

    if kind == Kind.BOOL:
        # ⚠️  Arabic words, not TRUE/FALSE. The reader is an Arabic-speaking
        #     analyst, and Excel's own boolean renders as TRUE/FALSE regardless
        #     of locale — which is the one thing they cannot filter by name.
        return "نعم" if value else "لا"

    if kind == Kind.MONEY:
        # ⚠️  Passed as `Decimal`, and openpyxl converts it to a float on write —
        #     because **xlsx has no decimal type**. Every number in a spreadsheet
        #     is a double, including in Excel itself; there is no way around it
        #     and no point pretending otherwise.
        #
        #     What this does buy is that the conversion happens exactly once, at
        #     the file boundary, from the exact stored value. Doing arithmetic in
        #     `float` on the way here — summing a line total, subtracting a cost —
        #     is where `core/money.py`'s objection actually bites, and every
        #     computed column in `datasets/` stays in `Decimal` until this line.
        return value if isinstance(value, Decimal) else Decimal(str(value))

    if kind == Kind.DATETIME and isinstance(value, dt.datetime):
        # ⚠️  Naive, because Excel has no concept of a timezone.
        #
        #     An aware datetime makes openpyxl raise on write. Converting to the
        #     project's local time first is what makes "17:00" mean five in the
        #     afternoon in Cairo rather than in UTC — the same mistake ADR-83
        #     names for the peak-hours report.
        from django.utils import timezone

        return timezone.localtime(value).replace(tzinfo=None) if timezone.is_aware(value) else value

    if kind in (Kind.INT, Kind.DATE):
        return value

    return str(value)


def build(
    *,
    sheet_title: str,
    columns,
    rows: Iterator[tuple],
    meta: dict,
) -> tuple[bytes, int]:
    """
    Write one dataset. Returns the bytes and the number of data rows written.

    ⚠️  `rows` is consumed as an **iterator**, and the count comes back rather
        than being asked for up front.

        Calling `len()` on the queryset would run the whole query a second time,
        and materialising it into a list to count it defeats the streaming that
        the write-only workbook exists for. The caller checks the ceiling with a
        `count()` before it gets here; this function reports what it actually wrote.
    """
    workbook = Workbook(write_only=True)

    written = _write_data_sheet(workbook, sheet_title, columns, rows)

    # ⚠️  `_meta` is written **last** so it can state the true row count, and it
    #     is placed last in the tab order for the same reason people want the
    #     data first. A file whose first tab is provenance gets closed and
    #     reopened on the second tab every single time.
    _write_meta_sheet(workbook, {**meta, "عدد الصفوف": written})

    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue(), written


def _write_data_sheet(workbook: Workbook, title: str, columns, rows) -> int:
    worksheet = workbook.create_sheet(_safe_title(title))

    # ⚠️  Right-to-left: the headers are Arabic, and a left-to-right sheet puts
    #     column A on the far right of the analyst's screen.
    worksheet.sheet_view.rightToLeft = True

    for position, column in enumerate(columns, start=1):
        letter = get_column_letter(position)
        worksheet.column_dimensions[letter].width = column.width or _WIDTHS.get(column.kind, 20)

    # ⚠️  `freeze_panes` is set **before the first row**, and `auto_filter` after.
    #
    #     The asymmetry is real, not a style choice. In write-only mode openpyxl
    #     serialises the sheet view as soon as the first row is written, so a
    #     freeze assigned afterwards is silently dropped — the file saves, opens
    #     and scrolls the header away, with nothing anywhere to say why. The
    #     filter is different: its `ref` needs the final row count, which does
    #     not exist until the last row has been appended.
    worksheet.freeze_panes = "A2"

    header_cells = []
    for column in columns:
        cell = WriteOnlyCell(worksheet, value=column.header)
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        header_cells.append(cell)
    worksheet.append(header_cells)

    kinds = [column.kind for column in columns]
    written = 0

    for row in rows:
        cells = []
        for value, kind in zip(row, kinds, strict=False):
            coerced = _coerce(value, kind)
            cell = WriteOnlyCell(worksheet, value=coerced)
            if coerced is not None and (fmt := _FORMATS.get(kind)):
                cell.number_format = fmt
            cells.append(cell)
        worksheet.append(cells)
        written += 1

    if columns and written:
        worksheet.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{written + 1}"

    return written


def _write_meta_sheet(workbook: Workbook, meta: dict) -> None:
    """
    Where this file came from.

    ⚠️  **The most valuable sheet in the workbook, and the one nobody asks for.**

        An export gets emailed, saved to a desktop and opened three weeks later.
        Without provenance nobody can tell which period it covers or which
        filters produced it — so it gets compared against a different quarter
        and a decision is made on the difference between two unrelated numbers.
    """
    worksheet = workbook.create_sheet("_عن هذا الملف")
    worksheet.sheet_view.rightToLeft = True
    worksheet.column_dimensions["A"].width = 28
    worksheet.column_dimensions["B"].width = 52

    for label, value in meta.items():
        label_cell = WriteOnlyCell(worksheet, value=str(label))
        label_cell.font = _META_LABEL
        value_cell = WriteOnlyCell(worksheet, value="—" if value in (None, "") else str(value))
        worksheet.append([label_cell, value_cell])

    note = WriteOnlyCell(
        worksheet,
        value="مولَّد آليًا — أي تعديل هنا لا يغيّر شيئًا في النظام",
    )
    note.font = _MUTED
    worksheet.append([])
    worksheet.append([note])


def _safe_title(title: str) -> str:
    """
    ⚠️  Excel refuses a sheet name over 31 characters or containing `[]:*?/\\`,
        and openpyxl raises rather than trimming — so an Arabic dataset name
        long enough to be descriptive would crash the export instead of
        shortening the tab.
    """
    cleaned = "".join(character for character in title if character not in "[]:*?/\\")
    return cleaned[:31] or "البيانات"
