"""
The optional `compare_at_price` ("price before discount") column of the products sheet.

⚠️  A sheet must not be able to carry what the admin form refuses: the importer writes with
    `bulk_create`, never through a serializer, so the rule is enforced in the validator
    — from the same function (`catalog.rules.compare_at_errors`).
"""

from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.models import Product
from imports import services, spec, template
from imports.models import ImportStatus
from imports.tests.conftest import workbook

pytestmark = pytest.mark.django_db


def upload(payload: bytes, *, mode=spec.ImportMode.CREATE_ONLY):
    return services.create_job(SimpleUploadedFile("catalogue.xlsx", payload), mode=mode)


def run(job):
    for _ in range(400):
        if not job.is_running:
            return job
        services.advance(job)
    raise AssertionError(f"job never stopped — {job.status}/{job.phase}")


def validated(job):
    services.start_validation(job)
    return run(job)


def executed(job):
    services.start_execution(job)
    return run(job)


def messages(job):
    return list(job.errors.values_list("column", "message"))


class TestSpec:
    def test_the_column_is_optional_money_next_to_the_price(self):
        keys = [column.key for column in spec.PRODUCT_COLUMNS]
        column = spec.column_map(spec.Sheet.PRODUCTS)["compare_at_price"]

        assert keys.index("compare_at_price") == keys.index("base_price") + 1
        assert column.kind == spec.Kind.MONEY
        assert column.required is False
        assert column.note  # the template hint

    def test_the_template_carries_the_header_and_a_hint(self):
        from io import BytesIO

        from openpyxl import load_workbook

        book = load_workbook(BytesIO(template.build()))
        sheet = book[spec.Sheet.PRODUCTS]
        headers = [cell.value for cell in sheet[1]]
        cell = sheet[1][headers.index("السعر قبل الخصم")]

        assert cell.comment is not None
        assert "السعر المرجعي" in cell.comment.text


class TestCreate:
    def test_a_valid_value_is_written(self, make_product_row):
        rows = [make_product_row("A", base_price="35.00", compare_at_price="45.00")]

        executed(validated(upload(workbook({"products": rows}))))

        assert Product.objects.get(sku="A").compare_at_price == Decimal("45.00")

    def test_the_column_is_optional_per_row(self, make_product_row):
        rows = [make_product_row("A", compare_at_price="45.00"), make_product_row("B")]

        executed(validated(upload(workbook({"products": rows}))))

        assert Product.objects.get(sku="B").compare_at_price is None

    @pytest.mark.parametrize("value", ["35.00", "20.00"])
    def test_equal_or_lower_rejects_the_row_and_names_the_column(self, make_product_row, value):
        rows = [make_product_row("A", base_price="35.00", compare_at_price=value)]

        job = validated(upload(workbook({"products": rows})))

        assert job.status == ImportStatus.FAILED or job.preview["summary"]["rejected"] == 1
        assert any(column == "السعر قبل الخصم" for column, _ in messages(job))
        assert Product.objects.count() == 0

    def test_a_negative_value_is_rejected(self, make_product_row):
        job = validated(
            upload(workbook({"products": [make_product_row("A", compare_at_price="-5")]}))
        )

        assert any("لا يكون سالبًا" in message for _, message in messages(job))

    def test_a_cell_that_is_not_a_number_is_a_coercion_error(self, make_product_row):
        job = validated(
            upload(workbook({"products": [make_product_row("A", compare_at_price="كثير")]}))
        )

        assert any(column == "السعر قبل الخصم" for column, _ in messages(job))


class TestUpdate:
    @pytest.fixture
    def existing(self, category):
        return Product.objects.create(
            sku="OLD",
            name_ar="قديم",
            name_en="Old",
            category=category,
            base_price=Decimal("100.00"),
            compare_at_price=Decimal("150.00"),
        )

    def update(self, rows, columns):
        return upload(
            workbook({"products": rows}, columns={"products": columns}),
            mode=spec.ImportMode.UPDATE_ONLY,
        )

    def test_setting_only_the_compare_at_is_judged_against_the_stored_price(self, existing):
        low = validated(
            self.update([{"sku": "OLD", "compare_at_price": "90.00"}], ["sku", "compare_at_price"])
        )
        assert any(column == "السعر قبل الخصم" for column, _ in messages(low))

        ok = executed(
            validated(
                self.update(
                    [{"sku": "OLD", "compare_at_price": "130.00"}], ["sku", "compare_at_price"]
                )
            )
        )
        assert ok.status == ImportStatus.DONE
        existing.refresh_from_db()
        assert existing.compare_at_price == Decimal("130.00")
        assert existing.base_price == Decimal("100.00")

    def test_the_row_price_wins_over_the_stored_one(self, existing):
        rows = [{"sku": "OLD", "base_price": "200.00", "compare_at_price": "250.00"}]

        job = executed(validated(self.update(rows, ["sku", "base_price", "compare_at_price"])))

        assert job.status == ImportStatus.DONE
        existing.refresh_from_db()
        assert (existing.base_price, existing.compare_at_price) == (
            Decimal("200.00"),
            Decimal("250.00"),
        )

    def test_a_blank_cell_clears_it(self, existing):
        rows = [{"sku": "OLD", "compare_at_price": None}]

        executed(validated(self.update(rows, ["sku", "compare_at_price"])))

        existing.refresh_from_db()
        assert existing.compare_at_price is None

    def test_a_price_list_update_without_the_column_leaves_it_alone(self, existing):
        """⚠️  The most common recurring import — `sku` and `base_price` — must not erase it."""
        rows = [{"sku": "OLD", "base_price": "110.00"}]

        executed(validated(self.update(rows, ["sku", "base_price"])))

        existing.refresh_from_db()
        assert existing.base_price == Decimal("110.00")
        assert existing.compare_at_price == Decimal("150.00")
