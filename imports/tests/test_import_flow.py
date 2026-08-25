"""
The whole flow: upload → dry run → execute → publish.

⚠️  These tests drive the runner the way every caller does — `advance` in a
    loop until `is_running` goes false. Calling the private chunk functions
    directly would test the writers while leaving the state machine, which is
    where the two real bugs were, untested.
"""

from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.models import Product, ProductVariant
from imports import services, spec
from imports.models import ImportJob, ImportStatus
from imports.tests.conftest import workbook
from inventory.models import Batch, Stock, StockMovement

pytestmark = pytest.mark.django_db


def upload(payload: bytes, *, mode=spec.ImportMode.CREATE_ONLY, actor=None) -> ImportJob:
    return services.create_job(
        SimpleUploadedFile("catalogue.xlsx", payload), mode=mode, actor=actor
    )


def run(job: ImportJob) -> ImportJob:
    """Drive to a stop, with a hard cap so a stuck state machine fails loudly."""
    for _ in range(400):
        if not job.is_running:
            return job
        services.advance(job)
    raise AssertionError(f"job never stopped — {job.status}/{job.phase}/{job.cursor}")


def validated(job: ImportJob) -> ImportJob:
    services.start_validation(job)
    return run(job)


def executed(job: ImportJob) -> ImportJob:
    services.start_execution(job)
    return run(job)


# ═══════════════════════════════════════════════════════════
#  The happy path
# ═══════════════════════════════════════════════════════════


class TestCreate:
    def test_a_clean_file_validates_then_imports(self, make_product_row):
        job = upload(workbook({"products": [make_product_row(f"SKU-{n}") for n in range(5)]}))

        validated(job)
        assert job.status == ImportStatus.VALIDATED
        assert job.preview["summary"] == {"will_create": 5, "will_update": 0, "rejected": 0}
        # ⚠️  Nothing is written by a dry run. This is the whole promise.
        assert Product.objects.count() == 0

        executed(job)
        assert job.status == ImportStatus.DONE
        assert Product.objects.count() == 5

    def test_imported_products_are_drafts_until_published(self, make_product_row):
        """
        ⚠️  Ten thousand products appearing in the storefront the instant an
            import finishes is an outage with a catalogue attached.
        """
        rows = [make_product_row("A"), make_product_row("B")]
        job = executed(validated(upload(workbook({"products": rows}))))

        assert Product.objects.filter(is_active=True).count() == 0

        assert services.publish(job) == 2
        assert Product.objects.filter(is_active=True).count() == 2

    def test_the_sheet_may_still_ask_for_an_active_product(self, make_product_row):
        rows = [make_product_row("A", is_active="نعم")]
        executed(validated(upload(workbook({"products": rows}))))

        assert Product.objects.get(sku="A").is_active is True

    def test_slugs_are_unique_even_for_identical_names(self, make_product_row, category):
        """
        ⚠️  `bulk_create` bypasses `SlugMixin.save`, so the slugs are built in
            memory before the insert — including collisions inside one chunk.
        """
        rows = [
            make_product_row(f"S{n}", name_en="Same Name", name_ar="نفس الاسم") for n in range(6)
        ]
        executed(validated(upload(workbook({"products": rows}))))

        slugs = list(Product.objects.values_list("slug", flat=True))
        assert len(slugs) == 6
        assert len(set(slugs)) == 6

    def test_a_slug_colliding_with_an_existing_product_is_suffixed(
        self, make_product_row, category
    ):
        Product.objects.create(
            sku="OLD", name_ar="قديم", name_en="Widget", category=category, base_price=Decimal("1")
        )
        original = Product.objects.get(sku="OLD").slug

        rows = [make_product_row("NEW", name_en="Widget")]
        executed(validated(upload(workbook({"products": rows}))))

        assert Product.objects.get(sku="NEW").slug != original


# ═══════════════════════════════════════════════════════════
#  Rejection
# ═══════════════════════════════════════════════════════════


class TestValidation:
    def test_one_bad_row_rejects_the_file(self, make_product_row):
        """
        ⚠️  Letting it through and dropping the bad row is how an import of
            9,999 products quietly loses the one that mattered.
        """
        rows = [make_product_row("GOOD"), make_product_row("BAD", category_path="no/such/path")]
        job = validated(upload(workbook({"products": rows})))

        assert job.status == ImportStatus.REJECTED
        assert job.failed_count == 1
        assert job.errors.filter(identifier="BAD").exists()

    def test_execution_is_impossible_without_a_dry_run(self, make_product_row):
        from core.errors import BusinessError

        job = upload(workbook({"products": [make_product_row("A")]}))
        with pytest.raises(BusinessError):
            services.start_execution(job)

    def test_a_rejected_file_cannot_be_executed(self, make_product_row):
        from core.errors import BusinessError

        rows = [make_product_row("A", base_price="مجانًا")]
        job = validated(upload(workbook({"products": rows})))
        assert job.status == ImportStatus.REJECTED

        with pytest.raises(BusinessError):
            services.start_execution(job)

    def test_the_error_names_the_column_and_the_row_the_admin_sees(self, make_product_row):
        """
        ⚠️  Row numbering is off by two — the header row and the hidden key row.
            A report that says "row 3" about row 5 sends the admin hunting.
        """
        rows = [make_product_row("A"), make_product_row("B", kind="NOT_A_KIND")]
        job = validated(upload(workbook({"products": rows})))

        error = job.errors.get(identifier="B")
        assert error.row_number == spec.FIRST_DATA_ROW + 1
        assert error.column == "نوع المنتج *"

    def test_a_duplicate_sku_inside_the_file_is_caught(self, make_product_row):
        """
        ⚠️  The failure a chunk cannot see on its own — the repeat may be seven
            thousand rows later, in a chunk that has no memory of the first.
        """
        rows = [make_product_row("DUP"), make_product_row("OTHER"), make_product_row("DUP")]
        job = validated(upload(workbook({"products": rows})))

        assert job.status == ImportStatus.REJECTED
        # Both occurrences are rejected — which of the two is right is not ours to guess.
        assert job.errors.filter(identifier="DUP").count() == 2
        assert not job.errors.filter(identifier="OTHER").exists()

    def test_a_coercion_failure_is_not_reported_as_a_missing_field(self, make_product_row):
        job = validated(upload(workbook({"products": [make_product_row("A", base_price="خمسة")]})))

        messages = list(job.errors.values_list("message", flat=True))
        assert any("خمسة" in message for message in messages)
        assert not any("فارغ" in message for message in messages)


# ═══════════════════════════════════════════════════════════
#  The regulatory rules — shared with the admin form
# ═══════════════════════════════════════════════════════════


class TestRegulatory:
    def test_a_medicine_needs_a_regulatory_class(self, make_product_row):
        """The rule now lives in `catalog.rules`, so the sheet obeys it too."""
        job = validated(upload(workbook({"products": [make_product_row("MED", kind="MEDICINE")]})))

        assert job.status == ImportStatus.REJECTED
        assert job.errors.filter(message__contains="تصنيفًا تنظيميًا").exists()

    def test_prescription_cannot_be_otc(self, make_product_row):
        rows = [
            make_product_row(
                "MED",
                kind="MEDICINE",
                regulatory_class="OTC",
                requires_prescription="نعم",
            )
        ]
        job = validated(upload(workbook({"products": rows})))
        assert job.status == ImportStatus.REJECTED

    def test_a_restricted_product_without_a_policy_is_rejected(self, make_product_row):
        """
        ⚠️  An empty access policy means the default, which means everyone —
            and on a prescription medicine that is publication to every visitor.
        """
        rows = [
            make_product_row(
                "RX", kind="MEDICINE", regulatory_class="PRESCRIPTION", requires_prescription="نعم"
            )
        ]
        job = validated(upload(workbook({"products": rows})))

        assert job.status == ImportStatus.REJECTED
        assert job.errors.filter(message__contains="سياسة وصول").exists()


# ═══════════════════════════════════════════════════════════
#  Modes
# ═══════════════════════════════════════════════════════════


class TestModes:
    def test_create_only_rejects_an_existing_sku(self, make_product_row, category):
        Product.objects.create(
            sku="A", name_ar="س", name_en="S", category=category, base_price=Decimal("1")
        )
        job = validated(upload(workbook({"products": [make_product_row("A")]})))

        assert job.status == ImportStatus.REJECTED
        assert job.errors.filter(message__contains="موجود مسبقًا").exists()

    def test_update_only_rejects_an_unknown_sku(self, make_product_row):
        job = validated(
            upload(
                workbook({"products": [make_product_row("GHOST")]}),
                mode=spec.ImportMode.UPDATE_ONLY,
            )
        )
        assert job.status == ImportStatus.REJECTED

    def test_upsert_does_both(self, make_product_row, category):
        Product.objects.create(
            sku="OLD", name_ar="س", name_en="S", category=category, base_price=Decimal("1")
        )
        rows = [make_product_row("OLD", base_price="99.00"), make_product_row("NEW")]
        job = validated(upload(workbook({"products": rows}), mode=spec.ImportMode.UPSERT))

        assert job.status == ImportStatus.VALIDATED
        assert job.preview["summary"] == {"will_create": 1, "will_update": 1, "rejected": 0}

        executed(job)
        assert Product.objects.get(sku="OLD").base_price == Decimal("99.00")
        assert Product.objects.filter(sku="NEW").exists()

    def test_a_price_list_update_leaves_absent_columns_alone(self, category):
        """
        ⚠️  The failure this guards is total: a two-column price list applied to
            every field would blank every description, ingredient and SEO title
            in the catalogue — an "update" that destroys more than it changes.
        """
        Product.objects.create(
            sku="A",
            name_ar="اسم",
            name_en="Name",
            description_ar="وصف مهم",
            active_ingredient_en="Paracetamol",
            category=category,
            base_price=Decimal("10.00"),
        )

        payload = workbook(
            {"products": [{"sku": "A", "base_price": "77.00"}]},
            columns={"products": ["sku", "base_price"]},
        )
        executed(validated(upload(payload, mode=spec.ImportMode.UPDATE_ONLY)))

        product = Product.objects.get(sku="A")
        assert product.base_price == Decimal("77.00")
        assert product.description_ar == "وصف مهم"
        assert product.active_ingredient_en == "Paracetamol"
        assert product.name_ar == "اسم"

    def test_updating_never_changes_the_slug(self, category):
        """ADR-27 — a renamed product keeps its URL."""
        product = Product.objects.create(
            sku="A", name_ar="قديم", name_en="Old", category=category, base_price=Decimal("1")
        )
        original = product.slug

        payload = workbook(
            {"products": [{"sku": "A", "name_ar": "جديد", "name_en": "Brand New"}]},
            columns={"products": ["sku", "name_ar", "name_en"]},
        )
        executed(validated(upload(payload, mode=spec.ImportMode.UPDATE_ONLY)))

        product.refresh_from_db()
        assert product.name_en == "Brand New"
        assert product.slug == original


# ═══════════════════════════════════════════════════════════
#  Opening stock
# ═══════════════════════════════════════════════════════════


class TestStock:
    def test_stock_arrives_through_inventory_not_by_writing_the_balance(
        self, make_product_row, location
    ):
        """
        ⚠️  A batch **and** a movement, or the ledger and the balance disagree
            from the very first row.
        """
        payload = workbook(
            {
                "products": [make_product_row("A")],
                "stock": [
                    {
                        "sku": "A",
                        "quantity": 250,
                        "unit_cost": "7.25",
                        "expires_at": "2027-06-30",
                        "location_code": location.code,
                    }
                ],
            }
        )
        job = executed(validated(upload(payload)))

        assert job.status == ImportStatus.DONE
        product = Product.objects.get(sku="A")

        batch = Batch.objects.get(product=product)
        assert batch.quantity_remaining == 250
        assert batch.unit_cost == Decimal("7.25")
        assert batch.expires_at.isoformat() == "2027-06-30"

        assert StockMovement.objects.filter(product=product).count() == 1
        assert Stock.objects.get(product=product, location=location).quantity_physical == 250

    def test_the_dry_run_accepts_a_product_the_same_file_creates(self, make_product_row, location):
        """
        ⚠️  The bug that made the preview useless: phases run products → stock
            and a dry run writes nothing, so every stock row came back "no
            product with this code" on a perfectly correct file.
        """
        payload = workbook(
            {
                "products": [make_product_row("A")],
                "stock": [{"sku": "A", "quantity": 10, "unit_cost": "1.00"}],
            }
        )
        job = validated(upload(payload))

        assert job.status == ImportStatus.VALIDATED
        assert job.failed_count == 0

    def test_quantity_without_a_cost_is_rejected(self, make_product_row, location):
        """
        ⚠️  ADR-09 — without the batch cost, the profit of a sale made months
            later cannot be computed, and no later fix recovers it.
        """
        payload = workbook(
            {
                "products": [make_product_row("A")],
                "stock": [{"sku": "A", "quantity": 10}],
            }
        )
        job = validated(upload(payload))

        assert job.status == ImportStatus.REJECTED
        assert job.errors.filter(sheet="stock").exists()

    def test_a_zero_quantity_is_rejected(self, make_product_row, location):
        payload = workbook(
            {
                "products": [make_product_row("A")],
                "stock": [{"sku": "A", "quantity": 0, "unit_cost": "1.00"}],
            }
        )
        assert validated(upload(payload)).status == ImportStatus.REJECTED

    def test_stock_for_an_unknown_product_is_rejected(self, make_product_row, location):
        payload = workbook(
            {
                "products": [make_product_row("A")],
                "stock": [{"sku": "GHOST", "quantity": 5, "unit_cost": "1.00"}],
            }
        )
        assert validated(upload(payload)).status == ImportStatus.REJECTED

    def test_an_empty_location_falls_back_to_the_default(self, make_product_row, location):
        payload = workbook(
            {
                "products": [make_product_row("A")],
                "stock": [{"sku": "A", "quantity": 5, "unit_cost": "2.00"}],
            }
        )
        executed(validated(upload(payload)))

        assert Batch.objects.get(product__sku="A").location_id == location.pk


# ═══════════════════════════════════════════════════════════
#  Variants
# ═══════════════════════════════════════════════════════════


class TestVariants:
    def test_variants_attach_to_a_parent_from_the_same_file(self, make_product_row):
        payload = workbook(
            {
                "products": [make_product_row("GLV")],
                "variants": [
                    {
                        "parent_sku": "GLV",
                        "sku": "GLV-M",
                        "name_ar": "وسط",
                        "name_en": "Medium",
                        "attributes": "size=M",
                        "price_adjustment": "-2.50",
                    }
                ],
            }
        )
        job = executed(validated(upload(payload)))

        assert job.status == ImportStatus.DONE
        variant = ProductVariant.objects.get(sku="GLV-M")
        assert variant.product.sku == "GLV"
        assert variant.attributes == {"size": "M"}
        assert variant.price_adjustment == Decimal("-2.50")

    def test_a_variant_may_not_take_a_product_code(self, make_product_row):
        """
        ⚠️  Two unique columns on two tables. A scanner then resolves one code to
            two different things depending on which lookup ran first.
        """
        payload = workbook(
            {
                "products": [make_product_row("A"), make_product_row("B")],
                "variants": [
                    {"parent_sku": "A", "sku": "B", "name_ar": "س", "name_en": "S"}
                ],
            }
        )
        assert validated(upload(payload)).status == ImportStatus.REJECTED


# ═══════════════════════════════════════════════════════════
#  Brands and manufacturers
# ═══════════════════════════════════════════════════════════


class TestPartners:
    def test_a_brand_resolves_by_its_arabic_name_not_only_its_slug(
        self, make_product_row, category, db
    ):
        """
        ⚠️  A supplier's price list says «فايزر», not `pfizer`. Slug-only
            resolution failed the single most common column in a real
            distributor file, on every row.
        """
        from catalog.models import Brand

        brand = Brand.objects.create(name_ar="فايزر", name_en="Pfizer")
        job = executed(
            validated(upload(workbook({"products": [make_product_row("A", brand_slug="فايزر")]})))
        )

        assert job.status == ImportStatus.DONE
        assert Product.objects.get(sku="A").brand_id == brand.pk

    def test_an_english_name_matches_case_insensitively(self, make_product_row, category, db):
        from catalog.models import Brand

        brand = Brand.objects.create(name_ar="فايزر", name_en="Pfizer")
        rows = [make_product_row("A", brand_slug="PFIZER")]
        executed(validated(upload(workbook({"products": rows}))))

        assert Product.objects.get(sku="A").brand_id == brand.pk

    def test_an_unknown_brand_is_an_error_by_default(self, make_product_row, category):
        job = validated(upload(workbook({"products": [make_product_row("A", brand_slug="ghost")]})))

        assert job.status == ImportStatus.REJECTED
        assert job.errors.filter(column__contains="البراند").exists()

    def test_the_option_creates_the_missing_brand(self, make_product_row, category):
        """
        ⚠️  The case the option exists for: a first load naming two hundred
            brands none of which exist yet.
        """
        from catalog.models import Brand

        payload = workbook({"products": [make_product_row("A", brand_slug="نوفارتس")]})
        job = services.create_job(
            SimpleUploadedFile("c.xlsx", payload),
            mode=spec.ImportMode.CREATE_ONLY,
            create_missing_brands=True,
        )

        # ⚠️  The preview must **pass**, or the option is unreachable — execution
        #     is only possible from a validated dry run.
        validated(job)
        assert job.status == ImportStatus.VALIDATED
        # And it must not have created anything yet.
        assert not Brand.objects.filter(name_ar="نوفارتس").exists()

        executed(job)
        brand = Brand.objects.get(name_ar="نوفارتس")
        assert brand.name_en == "نوفارتس"
        assert Product.objects.get(sku="A").brand_id == brand.pk

    def test_the_option_creates_each_brand_once_across_rows(self, make_product_row, category):
        from catalog.models import Brand

        rows = [make_product_row(f"S{n}", brand_slug="باير") for n in range(5)]
        job = services.create_job(
            SimpleUploadedFile("c.xlsx", workbook({"products": rows})),
            mode=spec.ImportMode.CREATE_ONLY,
            create_missing_brands=True,
        )
        executed(validated(job))

        assert Brand.objects.filter(name_ar="باير").count() == 1


# ═══════════════════════════════════════════════════════════
#  Resumption
# ═══════════════════════════════════════════════════════════


class TestResume:
    def test_a_job_resumes_from_its_cursor(self, make_product_row, monkeypatch):
        """
        ⚠️  The closed-laptop case. Progress is a database row precisely so a
            second caller can finish what the first abandoned.
        """
        monkeypatch.setattr(spec, "PRODUCT_CHUNK_SIZE", 2)
        monkeypatch.setattr(
            services, "_PHASE_CHUNK", {**services._PHASE_CHUNK, "PRODUCTS": 2}
        )

        rows = [make_product_row(f"S{n}") for n in range(6)]
        job = validated(upload(workbook({"products": rows})))
        services.start_execution(job)

        services.advance(job)
        assert job.status == ImportStatus.RUNNING
        partial = Product.objects.count()
        assert 0 < partial < 6

        # A completely fresh instance — nothing carried in memory.
        reloaded = ImportJob.objects.get(pk=job.pk)
        assert reloaded.cursor == partial
        run(reloaded)

        assert reloaded.status == ImportStatus.DONE
        assert Product.objects.count() == 6

    def test_the_periodic_runner_rescues_an_abandoned_job(self, make_product_row):
        from django.utils import timezone

        job = validated(upload(workbook({"products": [make_product_row("A")]})))
        services.start_execution(job)
        # ⚠️  Not `touch` — that helper stamps the heartbeat with "now" by
        #     definition, which is exactly what makes it useless for backdating.
        ImportJob.objects.filter(pk=job.pk).update(
            heartbeat_at=timezone.now() - services.ABANDONED_AFTER * 2
        )

        assert services.resume_abandoned() == 1
        assert Product.objects.filter(sku="A").exists()

    def test_a_fresh_job_is_left_alone(self, make_product_row):
        """A job the browser is actively driving must not be raced by cron."""
        job = validated(upload(workbook({"products": [make_product_row("A")]})))
        services.start_execution(job)

        assert services.resume_abandoned() == 0


# ═══════════════════════════════════════════════════════════
#  File-level rejection
# ═══════════════════════════════════════════════════════════


class TestFileShape:
    def test_a_missing_products_sheet_is_rejected_at_upload(self, location):
        from core.errors import BusinessError

        payload = workbook({"stock": [{"sku": "A", "quantity": 1, "unit_cost": "1"}]})
        with pytest.raises(BusinessError):
            upload(payload)

    def test_a_missing_required_column_is_rejected_at_upload(self, category):
        """
        ⚠️  Named at upload, not after a dry run of ten thousand rows. The admin
            fixes it in ten seconds and should not wait to be told.
        """
        from core.errors import BusinessError

        payload = workbook(
            {"products": [{"name_ar": "س", "name_en": "S"}]},
            columns={"products": ["name_ar", "name_en"]},
        )
        with pytest.raises(BusinessError) as caught:
            upload(payload)
        # ⚠️  The `message` is the generic catalogue string; `detail` is where
        #     the offending columns are named, and it is what the admin reads.
        assert "sku" in caught.value.to_dict()["detail"]

    def test_an_empty_file_is_rejected(self, category):
        from core.errors import BusinessError

        with pytest.raises(BusinessError):
            upload(workbook({"products": []}))

    def test_re_uploading_the_same_file_is_reported_not_blocked(self, make_product_row):
        payload = workbook({"products": [make_product_row("A")]})
        first = executed(validated(upload(payload)))

        second = upload(payload)
        earlier = services.earlier_import_of(second)

        assert earlier is not None
        assert earlier.pk == first.pk


# ═══════════════════════════════════════════════════════════
#  Cancellation and the audit trail
# ═══════════════════════════════════════════════════════════


class TestLifecycle:
    def test_cancelling_stops_the_remaining_chunks(self, make_product_row, monkeypatch):
        monkeypatch.setattr(
            services, "_PHASE_CHUNK", {**services._PHASE_CHUNK, "PRODUCTS": 2}
        )

        rows = [make_product_row(f"S{n}") for n in range(6)]
        job = validated(upload(workbook({"products": rows})))
        services.start_execution(job)
        services.advance(job)

        services.cancel(job, reason="غلط")
        assert job.status == ImportStatus.CANCELLED

        # ⚠️  Committed rows stay. Saying otherwise would be a lie — the stock
        #     movements they produced are in an append-only ledger.
        written = Product.objects.count()
        run(job)
        assert Product.objects.count() == written

    def test_one_audit_entry_for_the_whole_job(self, make_product_row, admin):
        """
        ⚠️  Ten thousand audit rows for a single deliberate act buries every
            other entry of that day.
        """
        from core.models.audit import AuditLog

        before = AuditLog.objects.count()
        rows = [make_product_row(f"S{n}") for n in range(5)]
        job = upload(workbook({"products": rows}), actor=admin)
        executed(validated(job))

        assert AuditLog.objects.count() == before + 1
        entry = AuditLog.objects.order_by("-created_at").first()
        assert entry.changes["created"] == 5

    def test_validating_twice_clears_the_previous_report(self, make_product_row):
        """A second dry run must not still show errors the admin fixed."""
        job = validated(upload(workbook({"products": [make_product_row("A", kind="WRONG")]})))
        assert job.errors.exists()

        validated(job)
        assert job.errors.count() == 1  # reported once, not twice
