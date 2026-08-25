"""
The template — **generated from the database on every download.**

⚠️  Never a static file checked into the repository.

    A category added this morning has to appear in the dropdown of a template
    downloaded this afternoon. A file on disk goes stale the first time anyone
    touches the catalogue, and the admin then fills three hundred rows with a
    category code the server rejects — with the template itself as their proof
    that the code was valid.

    `ProductFormOptionsAPI` states this rule for the admin form's dropdowns.
    This is the same rule, for the same reason, in a different medium.

⚠️  And the dropdowns are **real Excel validation**, not a note asking politely.

    A comment saying "use the codes in the reference sheet" is read by nobody.
    A cell that refuses the value is read by everybody, and it moves the entire
    class of "invalid category" errors from a report the admin reads after
    waiting, to the moment they typed it.
"""

from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from imports import references, spec

# ═══════════════════════════════════════════════════════════
#  Styling
# ═══════════════════════════════════════════════════════════

_REQUIRED_FILL = PatternFill("solid", fgColor="1F6F54")
_OPTIONAL_FILL = PatternFill("solid", fgColor="E8EDEB")
_CONDITIONAL_FILL = PatternFill("solid", fgColor="B8860B")
_EXAMPLE_FONT = Font(color="9AA5A0", italic=True, size=10)
_HEADER_REQUIRED_FONT = Font(color="FFFFFF", bold=True, size=11)
_HEADER_OPTIONAL_FONT = Font(color="1B2320", bold=True, size=11)
_THIN = Side(style="thin", color="C9D2CE")


def _autofilter_and_freeze(worksheet, column_count: int) -> None:
    """
    ⚠️  The freeze is at `A3`, below **both** header rows.

        Scrolling to row 4,000 of a ten-thousand-row sheet with the headers gone
        is how a column of costs gets typed into the column beside it.
    """
    worksheet.freeze_panes = "A3"
    if column_count:
        last = get_column_letter(column_count)
        worksheet.auto_filter.ref = f"A{spec.HEADER_ROW}:{last}{spec.HEADER_ROW}"


def _write_sheet(workbook: Workbook, sheet_name: str, data: references.ReferenceData) -> None:
    columns = spec.columns_for(sheet_name)
    worksheet = workbook.create_sheet(sheet_name)

    # ⚠️  Right-to-left, because the sheet is Arabic.
    #     Left-to-right puts column A on the far right of the admin's screen and
    #     every explanation in this file describes a layout they are not seeing.
    worksheet.sheet_view.rightToLeft = True

    for position, column in enumerate(columns, start=1):
        letter = get_column_letter(position)
        worksheet.column_dimensions[letter].width = column.width

        conditional = column.required_when is not None
        header = worksheet.cell(row=spec.HEADER_ROW, column=position, value=column.header)
        header.fill = (
            _REQUIRED_FILL
            if column.required
            else _CONDITIONAL_FILL
            if conditional
            else _OPTIONAL_FILL
        )
        header.font = (
            _HEADER_REQUIRED_FONT
            if column.required or conditional
            else _HEADER_OPTIONAL_FONT
        )
        header.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        header.border = Border(bottom=_THIN)

        note = column.note
        if conditional:
            other, values = column.required_when
            note = f"إلزامي حين يكون «{other}» ضمن: {'، '.join(sorted(values))}.\n{note}".strip()
        if note:
            # ⚠️  A comment, not a second explanatory row. A row would be data to
            #     the reader, and every import would start with one bogus record.
            header.comment = Comment(note, "النظام")
            header.comment.width = 320
            header.comment.height = 120

        # ── The hidden key row ─────────────────────────────
        worksheet.cell(row=spec.KEY_ROW, column=position, value=column.key)

        if column.example:
            worksheet.cell(row=spec.FIRST_DATA_ROW, column=position, value=column.example).font = (
                _EXAMPLE_FONT
            )

    # ⚠️  Hidden, and the example row is left visible on purpose.
    #
    #     The key row is machinery; showing it invites someone to "fix" the
    #     English. The example row is instruction — and an admin who overwrites
    #     it has done exactly the right thing, which is why row 3 is the first
    #     data row rather than a reserved one.
    worksheet.row_dimensions[spec.KEY_ROW].hidden = True

    _apply_validations(worksheet, columns, data)
    _autofilter_and_freeze(worksheet, len(columns))


def _apply_validations(worksheet, columns, data: references.ReferenceData) -> None:
    """
    Attach dropdowns and type checks down the sheet.

    ⚠️  Excel's inline list has a hard limit near 255 characters, and a catalogue
        with four hundred brands blows past it — the file then opens with a
        repair prompt and the admin's first experience of the feature is a
        corruption warning. So a long list is written to the reference sheet and
        pointed at by range; only short enumerations go inline.
    """
    last_row = spec.FIRST_DATA_ROW + spec.MAX_ROWS_PER_FILE

    for position, column in enumerate(columns, start=1):
        letter = get_column_letter(position)
        cell_range = f"{letter}{spec.FIRST_DATA_ROW}:{letter}{last_row}"

        validation: DataValidation | None = None

        if column.kind == spec.Kind.CHOICE and column.source:
            values = data.choice_values(column.source)
            if values:
                validation = _list_validation(worksheet, column, values, inline_ok=True)

        elif column.kind == spec.Kind.REF and column.source:
            values = data.choice_values(_reference_attribute(column.source))
            if values:
                validation = _list_validation(worksheet, column, values, inline_ok=False)

        elif column.kind == spec.Kind.BOOL:
            validation = DataValidation(
                type="list", formula1='"نعم,لا"', allow_blank=True, showDropDown=False
            )
            validation.error = "اكتب نعم أو لا"

        elif column.kind == spec.Kind.MONEY:
            validation = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0")
            validation.error = "قيمة رقمية لا تقلّ عن صفر"

        elif column.kind == spec.Kind.INT:
            validation = DataValidation(type="whole", operator="greaterThanOrEqual", formula1="0")
            validation.error = "رقم صحيح لا يقلّ عن صفر"

        elif column.kind == spec.Kind.DATE:
            validation = DataValidation(
                type="date", operator="greaterThan", formula1="DATE(1990,1,1)"
            )
            validation.error = "تاريخ بصيغة YYYY-MM-DD"

        if validation is None:
            continue

        # ⚠️  A **warning**, not a hard stop — except where a code is the only
        #     acceptable input.
        #
        #     Excel's `stop` style refuses a paste of five hundred rows outright
        #     rather than flagging the offending cells, and pasting is how a real
        #     catalogue arrives. `warning` lets the paste land and leaves the
        #     server's dry run to be the authority, which it is regardless.
        validation.errorStyle = "warning"
        validation.showErrorMessage = True
        validation.errorTitle = column.header

        worksheet.add_data_validation(validation)
        validation.add(cell_range)


def _reference_attribute(source: str) -> str:
    """`category_path` is the column's source name; `categories` is the table's."""
    return {"category_path": "categories"}.get(source, source)


#: Where each long list is parked on the reference sheet, filled by `_write_reference`.
_RANGES: dict[str, str] = {}


def _list_validation(worksheet, column, values, *, inline_ok: bool) -> DataValidation:
    joined = ",".join(values)
    if inline_ok and len(joined) < 250:
        validation = DataValidation(type="list", formula1=f'"{joined}"', allow_blank=True)
    else:
        source = _reference_attribute(column.source)
        reference = _RANGES.get(source)
        if not reference:
            # No range was written — fall back to no dropdown rather than a
            # formula pointing at nothing, which is what triggers the repair prompt.
            validation = DataValidation(
                type="textLength", operator="lessThanOrEqual", formula1="64"
            )
        else:
            validation = DataValidation(type="list", formula1=reference, allow_blank=True)
    return validation


def _write_reference(workbook: Workbook, data: references.ReferenceData) -> None:
    """
    The `_reference` sheet — every allowed value with its Arabic label beside it.

    ⚠️  It is written **first**, before the data sheets, because their dropdowns
        point into it by range. A sheet referenced before it exists is a broken
        formula, and Excel reports that as a damaged file.
    """
    worksheet = workbook.create_sheet(spec.Sheet.REFERENCE)
    worksheet.sheet_view.rightToLeft = True
    worksheet.column_dimensions["A"].width = 34
    worksheet.column_dimensions["B"].width = 40

    sets: list[tuple[str, str]] = [
        ("categories", "الفئات — انسخ المسار كما هو"),
        ("brands", "البراندات"),
        ("manufacturers", "الشركات المصنّعة"),
        ("access_policies", "سياسات الوصول"),
        ("tax_classes", "الفئات الضريبية"),
        ("locations", "المواقع المخزنية"),
        ("kinds", "أنواع المنتجات"),
        ("regulatory_classes", "التصنيفات التنظيمية"),
        ("dosage_forms", "الأشكال الدوائية"),
        ("storage_conditions", "شروط التخزين"),
    ]

    row = 1
    for source, title in sets:
        pairs = data.labelled(source)

        heading = worksheet.cell(row=row, column=1, value=title)
        heading.font = Font(bold=True, color="FFFFFF")
        heading.fill = _REQUIRED_FILL
        worksheet.cell(row=row, column=2).fill = _REQUIRED_FILL
        row += 1

        first = row
        for code, label in pairs:
            worksheet.cell(row=row, column=1, value=code)
            worksheet.cell(row=row, column=2, value=label)
            row += 1

        if pairs:
            _RANGES[source] = (
                f"'{spec.Sheet.REFERENCE}'!$A${first}:$A${row - 1}"
            )
        else:
            # ⚠️  An empty reference set is not a template bug — it is the store
            #     telling the admin it has no categories yet, and the import will
            #     fail on every row until it does. Saying so here is cheaper than
            #     ten thousand identical errors later.
            empty = worksheet.cell(row=row, column=1, value="— لا توجد قيم مسجّلة بعد —")
            empty.font = _EXAMPLE_FONT
            row += 1

        row += 1  # a blank line between sets

    worksheet.protection.sheet = True
    worksheet.protection.password = ""


def _write_guide(workbook: Workbook, data: references.ReferenceData) -> None:
    """The first sheet the admin sees — what this file is and the three rules that matter."""
    worksheet = workbook.create_sheet("اقرأ أولًا", 0)
    worksheet.sheet_view.rightToLeft = True
    worksheet.column_dimensions["A"].width = 100

    lines = [
        ("قالب الاستيراد الجماعي للمنتجات", True),
        ("", False),
        (f"الحد الأقصى لملف واحد: {spec.MAX_ROWS_PER_FILE:,} صف. أكبر من ذلك — قسّمه.", False),
        ("", False),
        ("ورقة «products» إلزامية. «stock» و«variants» اختياريتان.", False),
        ("", False),
        ("الأعمدة الخضراء إلزامية دائمًا. الذهبية إلزامية بشرط — مرّر على العنوان لتقرأه.", False),
        ("", False),
        ("١ — الفئة تُكتب بمسارها الكامل لا باسمها.", True),
        ("   «أقراص» وحدها موجودة تحت الأدوية والمكمّلات معًا؛ المسار هو ما يحسم أيّهما.", False),
        ("   انسخ المسار من ورقة «القيم المسموحة».", False),
        ("", False),
        ("٢ — أي صف فيه كمية يجب أن يحمل تكلفة وحدة.", True),
        ("   بدونها يستحيل حساب ربح أي بيعة لاحقة، وهو حساب لا يُستدرك بأثر رجعي.", False),
        ("", False),
        ("٣ — المستورد لا ينشر شيئًا من تلقاء نفسه.", True),
        ("   كل المنتجات تدخل غير مفعّلة. بعد مراجعة النتيجة تنشرها بضغطة واحدة.", False),
        ("", False),
        ("قبل التنفيذ يمرّ الملف بفحص جاف يقرأ كل صف بلا كتابة، ويعطيك تقريرًا", False),
        ("بأرقام الصفوف كما تراها هنا. الفحص لا يغيّر شيئًا — شغّله كما شئت.", False),
        ("", False),
        (f"عدد الفئات المسجّلة الآن: {len(data.categories)} · البراندات: {len(data.brands)}", False),
    ]

    for row, (text, bold) in enumerate(lines, start=1):
        cell = worksheet.cell(row=row, column=1, value=text)
        cell.font = Font(bold=bold, size=12 if bold else 11)
        cell.alignment = Alignment(vertical="center", wrap_text=False)

    worksheet.row_dimensions[1].height = 26


def build(data: references.ReferenceData | None = None) -> bytes:
    """The whole workbook as bytes, ready to stream."""
    data = data or references.load()

    _RANGES.clear()

    workbook = Workbook()
    # ⚠️  `Workbook()` opens with one sheet already made. Leaving it produces a
    #     stray "Sheet" the admin has to be told to ignore.
    workbook.remove(workbook.active)

    _write_reference(workbook, data)
    for sheet_name in (spec.Sheet.PRODUCTS, spec.Sheet.VARIANTS, spec.Sheet.STOCK):
        _write_sheet(workbook, sheet_name, data)
    _write_guide(workbook, data)

    workbook.active = 0

    buffer = io.BytesIO()
    workbook.save(buffer)
    workbook.close()
    return buffer.getvalue()
