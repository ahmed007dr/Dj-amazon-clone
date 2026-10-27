"""
An import stamps who ran it onto the products it touched.

⚠️  Imports write with `bulk_create` / `bulk_update`, which skip `save()` and so
    skip `auto_now` and anything a serializer would have stamped. Without this,
    the "added by" / "last modified by" columns of the admin table are blank for
    exactly the bulk of a real catalogue.
"""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import AccountType, User
from catalog.models import Product
from imports import services, spec
from imports.tests.conftest import workbook

pytestmark = pytest.mark.django_db


def make_user(email: str) -> User:
    user = User.objects.create_user(
        email=email, password="Str0ng-Test-Pass!23", account_type=AccountType.ADMIN
    )
    user.is_active = True
    user.save()
    return user


def run_import(payload: bytes, *, mode, actor):
    job = services.create_job(SimpleUploadedFile("catalogue.xlsx", payload), mode=mode, actor=actor)
    for step in (services.start_validation, services.start_execution):
        step(job)
        for _ in range(400):
            if not job.is_running:
                break
            services.advance(job)
    return job


def test_created_products_carry_the_importing_user(make_product_row):
    importer = make_user("importer-a@test.local")

    run_import(
        workbook({"products": [make_product_row("IMP-1"), make_product_row("IMP-2")]}),
        mode=spec.ImportMode.CREATE_ONLY,
        actor=importer,
    )

    products = list(Product.objects.order_by("sku"))
    assert [p.sku for p in products] == ["IMP-1", "IMP-2"]
    assert all(p.created_by_id == importer.pk for p in products)
    assert all(p.updated_by_id == importer.pk for p in products)


def test_updated_products_get_updated_by_but_keep_created_by(make_product_row):
    first = make_user("importer-a@test.local")
    second = make_user("importer-b@test.local")
    run_import(
        workbook({"products": [make_product_row("IMP-1")]}),
        mode=spec.ImportMode.CREATE_ONLY,
        actor=first,
    )
    created = Product.objects.get(sku="IMP-1")

    # A price-list style update: only `sku` and `base_price` columns.
    run_import(
        workbook(
            {"products": [make_product_row("IMP-1", base_price="99.00")]},
            columns={"products": ["sku", "base_price"]},
        ),
        mode=spec.ImportMode.UPSERT,
        actor=second,
    )

    product = Product.objects.get(sku="IMP-1")
    assert str(product.base_price) == "99.00"
    assert product.created_by_id == first.pk
    assert product.updated_by_id == second.pk
    # ⚠️  `bulk_update` bypasses `auto_now`; the stamp is applied by hand.
    assert product.updated_at > created.updated_at
