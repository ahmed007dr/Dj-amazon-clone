"""
Creating, deleting and restoring products from the admin portal.

⚠️  These operations were available only through the API and the Django panel,
    with no route from the admin portal. The tests here guard the **contract**
    the screen depends on: the form's options, the filters, and the restorable
    soft delete.

⚠️  And `administration` is reached through `apps.get_model` rather than by
    import — it and `catalog` are independent siblings on the same layer.
"""

from decimal import Decimal

import pytest

from core.testing import grant_all_domains
from django.apps import apps
from django.urls import reverse
from rest_framework.test import APIClient

from access.models import AccessPolicy
from accounts.models import AccountType, User
from catalog.models import Category, Product, ProductKind

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


@pytest.fixture
def category(db):
    return Category.objects.create(name_ar="مستلزمات", name_en="Supplies")


@pytest.fixture
def policies(db):
    from django.core.management import call_command

    call_command("seed_access_policies", verbosity=0)
    return {policy.code: policy for policy in AccessPolicy.objects.all()}


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_user(
        email="admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    admin.is_active = True
    admin.save()
    apps.get_model("administration", "AdminProfile").objects.create(user=admin)
    grant_all_domains(admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


def draft(category, **overrides) -> dict:
    body = {
        "sku": "NEW-001",
        "name_ar": "شاش طبي",
        "name_en": "Medical gauze",
        "kind": ProductKind.SUPPLY,
        "category": str(category.pk),
        "base_price": "35.00",
    }
    body.update(overrides)
    return body


# ═══════════════════════════════════════════════════════════
#  Creation
# ═══════════════════════════════════════════════════════════


class TestCreate:
    def test_admin_creates_a_product(self, admin_client, category):
        response = admin_client.post(
            reverse("v1:catalog:admin-products"), draft(category), format="json"
        )

        assert response.status_code == 201
        product = Product.objects.get(sku="NEW-001")
        assert product.name_ar == "شاش طبي"
        assert product.category_id == category.pk

    def test_slug_is_generated_not_supplied(self, admin_client, category):
        """
        ⚠️  `slug` is read-only — changing it breaks external links and search
            engine indexing. Sending it must be ignored, not accepted.
        """
        response = admin_client.post(
            reverse("v1:catalog:admin-products"),
            draft(category, slug="attacker-chosen"),
            format="json",
        )

        assert response.status_code == 201
        assert Product.objects.get(sku="NEW-001").slug != "attacker-chosen"

    def test_duplicate_sku_is_refused(self, admin_client, category):
        """A duplicate code means two items on one shelf that the scanner cannot tell apart."""
        admin_client.post(reverse("v1:catalog:admin-products"), draft(category), format="json")

        response = admin_client.post(
            reverse("v1:catalog:admin-products"),
            draft(category, name_ar="آخر"),
            format="json",
        )

        assert response.status_code == 400
        assert "sku" in response.data["fields"]

    def test_creation_is_written_to_the_audit_log(self, admin_client, category):
        admin_client.post(reverse("v1:catalog:admin-products"), draft(category), format="json")

        entry = (
            apps.get_model("core", "AuditLog")
            .objects.filter(action="CREATE", object_repr__contains="NEW-001")
            .first()
        )
        assert entry is not None

    def test_customer_cannot_create(self, category):
        customer = User.objects.create_user(email="c@test.local", password=PASSWORD)
        customer.is_active = True
        customer.save()

        client = APIClient()
        client.force_authenticate(user=customer)

        response = client.post(reverse("v1:catalog:admin-products"), draft(category), format="json")
        assert response.status_code == 403
        assert not Product.objects.filter(sku="NEW-001").exists()


# ═══════════════════════════════════════════════════════════
#  Deletion and restoration
# ═══════════════════════════════════════════════════════════


class TestDeleteAndRestore:
    def test_deleted_product_can_be_restored(self, admin_client, category):
        """
        ⚠️  A soft delete with no restore is a permanent delete from the user's
            point of view — and the first question after an accidental delete is
            "how do I get it back?".
        """
        product = Product.objects.create(
            sku="DEL-001", name_ar="صنف", name_en="Item", category=category
        )

        admin_client.delete(reverse("v1:catalog:admin-product-detail", args=[product.pk]))
        assert not Product.objects.filter(pk=product.pk).exists()

        response = admin_client.post(reverse("v1:catalog:admin-product-restore", args=[product.pk]))

        assert response.status_code == 200
        assert Product.objects.filter(pk=product.pk).exists()

    def test_restoring_a_live_product_is_a_conflict(self, admin_client, category):
        product = Product.objects.create(
            sku="LIVE-001", name_ar="صنف", name_en="Item", category=category
        )

        response = admin_client.post(reverse("v1:catalog:admin-product-restore", args=[product.pk]))
        assert response.status_code == 409

    def test_deleted_products_are_hidden_unless_asked_for(self, admin_client, category):
        product = Product.objects.create(
            sku="DEL-002", name_ar="صنف", name_en="Item", category=category
        )
        product.delete()

        hidden = admin_client.get(reverse("v1:catalog:admin-products"))
        assert [row["sku"] for row in hidden.data["results"]] == []

        shown = admin_client.get(reverse("v1:catalog:admin-products"), {"include_deleted": "true"})
        assert [row["sku"] for row in shown.data["results"]] == ["DEL-002"]

    def test_deleted_product_leaves_the_public_catalog(self, admin_client, category):
        product = Product.objects.create(
            sku="PUB-9", name_ar="صنف", name_en="Item", category=category
        )
        admin_client.delete(reverse("v1:catalog:admin-product-detail", args=[product.pk]))

        public = APIClient().get(reverse("v1:catalog:products"))
        assert [row["sku"] for row in public.data["results"]] == []


# ═══════════════════════════════════════════════════════════
#  Filters
# ═══════════════════════════════════════════════════════════


class TestFilters:
    def test_status_filter_actually_filters(self, admin_client, category):
        """
        ⚠️  **A regression**: the frontend sends `is_active` while the server
            read `inactive` alone — so the filter passed through with no effect
            and the screen showed "active" while the results included the discontinued.

            A filter that does not filter is worse than none, because it gets believed.
        """
        Product.objects.create(
            sku="ON-1", name_ar="مفعّل", name_en="On", category=category, is_active=True
        )
        Product.objects.create(
            sku="OFF-1", name_ar="موقوف", name_en="Off", category=category, is_active=False
        )

        url = reverse("v1:catalog:admin-products")

        on = admin_client.get(url, {"is_active": "true"})
        off = admin_client.get(url, {"is_active": "false"})

        assert [row["sku"] for row in on.data["results"]] == ["ON-1"]
        assert [row["sku"] for row in off.data["results"]] == ["OFF-1"]

    def test_barcode_search_is_exact(self, admin_client, category):
        """The scanner sends a complete number — and a partial match returns a different item."""
        Product.objects.create(
            sku="BC-1",
            name_ar="صنف",
            name_en="Item",
            category=category,
            barcode="6221033000012",
        )

        response = admin_client.get(
            reverse("v1:catalog:admin-products"), {"search": "6221033000012"}
        )
        assert [row["sku"] for row in response.data["results"]] == ["BC-1"]


# ═══════════════════════════════════════════════════════════
#  Form options
# ═══════════════════════════════════════════════════════════


class TestFormOptions:
    def test_options_carry_every_list_the_form_needs(self, admin_client, category):
        response = admin_client.get(reverse("v1:catalog:admin-product-options"))

        assert response.status_code == 200
        for key in (
            "kinds",
            "regulatory_classes",
            "dosage_forms",
            "storage_conditions",
            "categories",
            "brands",
            "manufacturers",
        ):
            assert key in response.data, key

        assert response.data["kinds"][0].keys() == {"value", "label"}

    def test_categories_hidden_from_the_menu_are_still_selectable(self, admin_client):
        """
        ⚠️  `show_in_menu` is a **display** classification, not a permission one.

            The public categories endpoint filters by it, and relying on that
            here stopped the admin assigning a product to a category that genuinely exists.
        """
        hidden = Category.objects.create(
            name_ar="فئة داخلية", name_en="Internal", show_in_menu=False
        )

        response = admin_client.get(reverse("v1:catalog:admin-product-options"))
        ids = {row["id"] for row in response.data["categories"]}

        assert str(hidden.pk) in ids

    def test_category_label_shows_the_full_path(self, admin_client, category):
        """"Tablets" alone is ambiguous when it exists under both "Medicines" and "Supplements"."""
        child = Category.objects.create(name_ar="شاش", name_en="Gauze", parent=category)

        response = admin_client.get(reverse("v1:catalog:admin-product-options"))
        labels = {row["id"]: row["path_label"] for row in response.data["categories"]}

        assert labels[str(child.pk)] == "مستلزمات ← شاش"

    def test_options_carry_the_access_policies(self, admin_client, policies):
        """
        ⚠️  "Who sees this product?" is part of the creation form, not an
            advanced setting. Its absence makes every new product silently
            inherit the default — so a restricted medicine is published to
            everyone and is discovered only when someone not entitled to it buys it.
        """
        response = admin_client.get(reverse("v1:catalog:admin-product-options"))
        codes = {row["code"] for row in response.data["access_policies"]}

        assert {"public", "students", "professionals", "pharmacy_only"} <= codes

    def test_the_default_policy_comes_first(self, admin_client, policies):
        """"For everyone" is the right choice for most products — and burying it
        mid-list makes the admin restrict a public product unintentionally."""
        response = admin_client.get(reverse("v1:catalog:admin-product-options"))
        assert response.data["access_policies"][0]["is_default"] is True

    def test_each_policy_carries_its_conditions_not_just_a_name(self, admin_client, policies):
        """"Verified professionals" alone does not say that an unverified doctor is blocked."""
        response = admin_client.get(reverse("v1:catalog:admin-product-options"))
        professionals = next(
            row for row in response.data["access_policies"] if row["code"] == "professionals"
        )

        assert professionals["requires_verification"] is True
        assert "DOCTOR" in professionals["allowed_account_types"]

    def test_customer_cannot_read_options(self, category):
        customer = User.objects.create_user(email="c2@test.local", password=PASSWORD)
        customer.is_active = True
        customer.save()

        client = APIClient()
        client.force_authenticate(user=customer)

        assert client.get(reverse("v1:catalog:admin-product-options")).status_code == 403


# ═══════════════════════════════════════════════════════════
#  Editing
# ═══════════════════════════════════════════════════════════


class TestAudience:
    """
    ⚠️  **"Who sees this product?" is not a cosmetic field.**

        The policy chosen at creation is what separates a restricted medicine
        from a public product. The tests here follow the effect from the form
        through to what a visitor actually sees in the catalogue.
    """

    def test_the_chosen_policy_is_saved(self, admin_client, category, policies):
        response = admin_client.post(
            reverse("v1:catalog:admin-products"),
            draft(category, access_policy=str(policies["pharmacy_only"].pk)),
            format="json",
        )

        assert response.status_code == 201
        assert Product.objects.get(sku="NEW-001").access_policy_id == policies["pharmacy_only"].pk

    def test_a_restricted_product_is_invisible_to_guests(self, admin_client, category, policies):
        """
        ⚠️  Filtering in the queryset, not in the presentation: a restricted
            product appears in no results, in no count, and does not open by direct link.
        """
        admin_client.post(
            reverse("v1:catalog:admin-products"),
            draft(category, sku="RX-1", access_policy=str(policies["professionals"].pk)),
            format="json",
        )
        admin_client.post(
            reverse("v1:catalog:admin-products"),
            draft(category, sku="OPEN-1", access_policy=str(policies["public"].pk)),
            format="json",
        )

        public = APIClient().get(reverse("v1:catalog:products"))
        skus = {row["sku"] for row in public.data["results"]}

        assert skus == {"OPEN-1"}

    def test_a_verified_pharmacy_sees_what_a_guest_cannot(self, admin_client, category, policies):
        from accounts.models import VerificationStatus

        admin_client.post(
            reverse("v1:catalog:admin-products"),
            draft(category, sku="PH-1", access_policy=str(policies["pharmacy_only"].pk)),
            format="json",
        )

        pharmacy = User.objects.create_user(
            email="ph@test.local", password=PASSWORD, account_type=AccountType.PHARMACY
        )
        pharmacy.is_active = True
        pharmacy.verification_status = VerificationStatus.VERIFIED
        pharmacy.save()

        client = APIClient()
        client.force_authenticate(user=pharmacy)

        response = client.get(reverse("v1:catalog:products"))
        assert {row["sku"] for row in response.data["results"]} == {"PH-1"}

    def test_omitting_the_policy_falls_back_to_the_default(self, admin_client, category, policies):
        """
        ⚠️  A product with no explicit policy inherits the default — which is
            why the default is shown **by name** in the form rather than as "no selection".
        """
        admin_client.post(reverse("v1:catalog:admin-products"), draft(category), format="json")

        product = Product.objects.get(sku="NEW-001")
        assert product.access_policy_id is None

        # and a visitor sees it because the default is "public"
        public = APIClient().get(reverse("v1:catalog:products"))
        assert {row["sku"] for row in public.data["results"]} == {"NEW-001"}

    def test_the_policy_can_be_tightened_after_creation(self, admin_client, category, policies):
        """Discovering that a restricted product was published to everyone must be fixable in one click."""
        admin_client.post(reverse("v1:catalog:admin-products"), draft(category), format="json")
        product = Product.objects.get(sku="NEW-001")

        admin_client.patch(
            reverse("v1:catalog:admin-product-detail", args=[product.pk]),
            {"access_policy": str(policies["professionals"].pk)},
            format="json",
        )

        public = APIClient().get(reverse("v1:catalog:products"))
        assert [row["sku"] for row in public.data["results"]] == []


class TestUpdate:
    def test_partial_update_leaves_untouched_fields_alone(self, admin_client, category):
        """
        ⚠️  The screen sends only the fields it displays; the SEO fields are not
            among them. Saving must not erase them.
        """
        product = Product.objects.create(
            sku="UPD-1",
            name_ar="قديم",
            name_en="Old",
            category=category,
            base_price=Decimal("10.00"),
            meta_title_ar="عنوان أرشفة",
        )

        response = admin_client.patch(
            reverse("v1:catalog:admin-product-detail", args=[product.pk]),
            {"name_ar": "جديد", "base_price": "12.50"},
            format="json",
        )

        assert response.status_code == 200
        product.refresh_from_db()
        assert product.name_ar == "جديد"
        assert product.base_price == Decimal("12.50")
        assert product.meta_title_ar == "عنوان أرشفة"
