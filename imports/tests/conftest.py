"""
Shared fixtures for the import tests.

⚠️  The workbooks here are built with `openpyxl`, not checked in as binary
    files.

    A fixture `.xlsx` in the repository is opaque: nobody can tell from a diff
    what changed in it, and it goes stale the moment a column is added to
    `spec.py` — at which point the tests keep passing against a file shaped like
    last month's template. Building from the spec means the tests exercise the
    template the admin actually downloads.
"""

from __future__ import annotations

import io

import pytest
from django.apps import apps
from openpyxl import Workbook
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from catalog.models import Category
from core.testing import grant_all_domains
from imports import spec
from inventory.models import StockLocation

PASSWORD = "Str0ng-Test-Pass!23"


@pytest.fixture
def category(db):
    category = Category.objects.create(name_ar="مستلزمات", name_en="Supplies")
    category.refresh_from_db()
    return category


@pytest.fixture
def location(db):
    return StockLocation.objects.create(
        code="main", name_ar="المخزن", name_en="Warehouse", is_default=True
    )


@pytest.fixture
def admin(db):
    admin = User.objects.create_user(
        email="importer@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    admin.is_active = True
    admin.save()
    apps.get_model("administration", "AdminProfile").objects.create(user=admin)
    grant_all_domains(admin)
    return admin


@pytest.fixture
def admin_client(admin):
    client = APIClient()
    client.force_authenticate(user=admin)
    return client


# ═══════════════════════════════════════════════════════════
#  Workbook building
# ═══════════════════════════════════════════════════════════


def sheet_rows(sheet_name: str, rows: list[dict], *, columns: list[str] | None = None):
    """
    Turn dicts into the two header rows plus data, in template order.

    `columns` narrows which columns are written — which is how a test builds the
    price-list case: a sheet carrying `sku` and `base_price` and nothing else.
    """
    keys = [column.key for column in spec.columns_for(sheet_name)]
    if columns is not None:
        keys = [key for key in keys if key in columns]

    headers = {column.key: column.header for column in spec.columns_for(sheet_name)}
    output = [[headers[key] for key in keys], list(keys)]
    output.extend([[row.get(key) for key in keys] for row in rows])
    return output


def workbook(
    sheets: dict[str, list[dict]], *, columns: dict[str, list[str]] | None = None
) -> bytes:
    """`{"products": [{...}, ...]}` → the bytes of a real xlsx."""
    columns = columns or {}
    book = Workbook(write_only=True)
    for sheet_name, rows in sheets.items():
        worksheet = book.create_sheet(sheet_name)
        for row in sheet_rows(sheet_name, rows, columns=columns.get(sheet_name)):
            worksheet.append(row)

    buffer = io.BytesIO()
    book.save(buffer)
    book.close()
    return buffer.getvalue()


def product_row(sku: str, category, **overrides) -> dict:
    row = {
        "sku": sku,
        "name_ar": f"صنف {sku}",
        "name_en": f"Item {sku}",
        "category_path": category.path,
        "kind": "SUPPLY",
        "base_price": "35.00",
    }
    row.update(overrides)
    return row


@pytest.fixture
def build_workbook():
    return workbook


@pytest.fixture
def make_product_row(category):
    def factory(sku: str, **overrides):
        return product_row(sku, category, **overrides)

    return factory
