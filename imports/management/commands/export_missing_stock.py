"""
Export the products that have no opening balance, in the importer's own `stock` format.

    python manage.py export_missing_stock --out opening-stock.xlsx

⚠️  **Why a command and not a screen.**

    This is a one-off migration, not an operation. A catalogue imported without
    its `stock` sheet leaves every product at zero available — and since a
    product whose available quantity is zero does not appear in the storefront,
    that catalogue is invisible until somebody enters the quantities. The gap is
    counted in thousands of rows, which is a spreadsheet's job and not a form's.

⚠️  **It writes the sheet the importer already reads — it does not invent a format.**

    The columns come from `imports.spec.STOCK_COLUMNS`, so the file this produces
    goes straight back through `/imports/` with no transformation. A bespoke
    layout would have needed a bespoke reader, and the two would drift the first
    time a column was added to one of them.

⚠️  **And it fills in no quantity.**

    `quantity` and `unit_cost` are left empty on purpose. A default of zero is
    not an opening balance but its absence, and a guessed cost makes the profit
    on every later sale wrong in a way no report can flag — the importer refuses
    a quantity without a cost for exactly that reason.
"""

from __future__ import annotations

import io
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalog.models import Product
from imports import spec
from inventory.models import StockLocation

#: The columns the admin fills in — the rest of the sheet is optional
_FILL_IN = ("quantity", "unit_cost")


class Command(BaseCommand):
    help = "تصدير المنتجات بلا رصيد افتتاحي في صيغة ورقة stock للمستورد"

    def add_arguments(self, parser):
        parser.add_argument(
            "--out",
            default="opening-stock.xlsx",
            help="مسار الملف الناتج (افتراضي: opening-stock.xlsx)",
        )
        parser.add_argument(
            "--location",
            default="",
            help="رمز الموقع المخزني الذي يُملأ في كل صف — فارغ = الموقع الافتراضي",
        )
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="يشمل المنتجات الموقوفة أيضًا (الافتراضي: المفعّلة وحدها)",
        )

    def handle(self, *args, **options):
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Alignment, Font, PatternFill
        except ImportError as exc:  # pragma: no cover - openpyxl ships with the importer
            raise CommandError("openpyxl غير مثبّت") from exc

        location_code = options["location"].strip()
        if location_code:
            location = StockLocation.objects.filter(code=location_code).first()
            if location is None:
                raise CommandError(f"لا يوجد موقع مخزني بالرمز {location_code}")
            if not (location.is_sellable and location.is_active):
                # ⚠️  A quarantine or a damaged-goods store is not sellable, so a
                #     balance received into it leaves the product invisible anyway
                #     — the exact problem this file exists to fix.
                raise CommandError(
                    f"الموقع {location_code} غير قابل للبيع أو موقوف — "
                    "الرصيد فيه لا يُظهر المنتج في المتجر"
                )

        products = (
            Product.objects.all()
            if options["include_inactive"]
            else Product.objects.filter(is_active=True)
        )

        # ⚠️  "No stock row at all" — not "a row that reads zero".
        #
        #     They are the same to a customer and very different to whoever has to
        #     fix it: the first was never received, the second was received and
        #     sold. Only the first belongs in an opening-balance file.
        missing = products.filter(stock_records__isnull=True).order_by("sku")
        total = missing.count()

        if total == 0:
            self.stdout.write(self.style.SUCCESS("كل المنتجات لها رصيد — لا شيء للتصدير."))
            return

        if total > spec.MAX_ROWS_PER_FILE:
            # ⚠️  Refused here rather than at upload.
            #
            #     A file written now and rejected after a long upload wastes the
            #     work of filling it in. `--include-inactive` off is usually the
            #     difference; beyond that the catalogue is split by hand.
            raise CommandError(
                f"{total:,} صف يتجاوز حد المستورد ({spec.MAX_ROWS_PER_FILE:,} للورقة) — "
                "صدّر على دفعات"
            )

        workbook = Workbook()
        # ⚠️  `Workbook()` opens with a sheet already made; it becomes `products`.
        workbook.remove(workbook.active)

        fill_in = PatternFill("solid", fgColor="FFF3CD")

        def header_row(sheet_name: str, columns, *, highlight=()):
            """
            ⚠️  **Three rows, exactly as `imports.template` writes them.**

                The reader consumes two rows before the data: the Arabic labels
                and a hidden row of machine keys. A sheet with a single header row
                is not rejected — it is read with the **first product** treated as
                the key row and dropped, silently, one SKU short. It cost this
                file eleven thousand eight hundred and ninety-nine rows against
                eleven thousand nine hundred products before the count was
                compared, and nothing in the import report would ever have named
                the missing one.

                So the layout comes from `spec.HEADER_ROW` / `KEY_ROW` /
                `FIRST_DATA_ROW`, not from a literal 1 and 2.
            """
            worksheet = workbook.create_sheet(sheet_name)

            # ⚠️  Arabic sheet — left-to-right puts column A off the far edge of
            #     the admin's screen, and every instruction describes a layout
            #     they are not looking at.
            worksheet.sheet_view.rightToLeft = True

            for index, column in enumerate(columns, start=1):
                cell = worksheet.cell(row=spec.HEADER_ROW, column=index, value=column.header)
                cell.font = Font(bold=True)
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                if column.key in highlight:
                    # ⚠️  The two columns the admin must type are marked, so a file
                    #     of twelve thousand rows says where the work is at a glance.
                    cell.fill = fill_in
                worksheet.column_dimensions[cell.column_letter].width = column.width

                worksheet.cell(row=spec.KEY_ROW, column=index, value=column.key)

            # ⚠️  Hidden, like the template's: it is machinery, and showing it
            #     invites somebody to "fix" the English into Arabic.
            worksheet.row_dimensions[spec.KEY_ROW].hidden = True
            worksheet.freeze_panes = f"A{spec.FIRST_DATA_ROW}"
            return worksheet

        # ⚠️  **An empty `products` sheet, and it is not decoration.**
        #
        #     `products` is the one sheet the importer requires
        #     (`spec.REQUIRED_SHEETS`), and a file without it is refused on upload
        #     with "download the template" — advice that is wrong here, because
        #     the products already exist and only their balances are missing.
        #     Headers with no rows satisfy the check and import nothing.
        header_row(spec.Sheet.PRODUCTS, spec.SHEETS[spec.Sheet.PRODUCTS])

        columns = spec.SHEETS[spec.Sheet.STOCK]
        worksheet = header_row(spec.Sheet.STOCK, columns, highlight=_FILL_IN)

        position = {column.key: index for index, column in enumerate(columns, start=1)}

        # ⚠️  `iterator()` — twelve thousand rows are not held in memory at once.
        for row, sku in enumerate(
            missing.values_list("sku", flat=True).iterator(), start=spec.FIRST_DATA_ROW
        ):
            worksheet.cell(row=row, column=position["sku"], value=sku)
            if location_code:
                worksheet.cell(row=row, column=position["location_code"], value=location_code)

        buffer = io.BytesIO()
        workbook.save(buffer)
        workbook.close()

        destination = Path(options["out"])
        destination.write_bytes(buffer.getvalue())

        self.stdout.write(self.style.SUCCESS(f"{total:,} منتج بلا رصيد افتتاحي ← {destination}"))
        self.stdout.write(
            "\n  الخطوات:\n"
            "    ١. املأ عمودَي «الكمية» و«تكلفة الوحدة» المظللين\n"
            "    ٢. ارفع الملف من شاشة الاستيراد ونفّذ الفحص الجاف أولًا\n"
            "    ٣. بعد نجاح الفحص نفّذ الاستيراد\n"
            "\n  ⚠️  الصفوف التي تتركها فارغة تُتجاهَل — يمكنك التصدير على دفعات.\n"
        )
