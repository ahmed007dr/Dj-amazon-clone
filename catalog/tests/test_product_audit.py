"""
Product audit — "who added / changed this product, and when?"

⚠️  Two records are guarded here and they must agree:

        Product.created_by / updated_by   →  the columns of the admin table
        core.AuditLog (content type + id) →  the History drawer's timeline

    The summary columns are cheap to read but say nothing about *what*
    changed; the log says what, but is expensive to scan per row. Neither
    replaces the other.
"""

from decimal import Decimal

import pytest
from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from catalog import audit
from catalog.models import Category, Product, ProductKind
from core.models.audit import AuditAction, AuditLog
from core.testing import grant_all_domains

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


def make_admin(email, *, first="", last="", grant=True) -> User:
    user = User.objects.create_user(
        email=email,
        password=PASSWORD,
        account_type=AccountType.ADMIN,
        first_name=first,
        last_name=last,
    )
    user.is_active = True
    user.save()
    apps.get_model("administration", "AdminProfile").objects.create(user=user)
    if grant:
        grant_all_domains(user)
    return user


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def category(db):
    return Category.objects.create(name_ar="مستلزمات", name_en="Supplies")


@pytest.fixture
def alice(db):
    return make_admin("alice@test.local", first="Alice", last="Owner")


@pytest.fixture
def bob(db):
    return make_admin("bob@test.local", first="Bob", last="Editor")


def draft(category, **overrides) -> dict:
    body = {
        "sku": "AUD-001",
        "name_ar": "شاش طبي",
        "name_en": "Medical gauze",
        "kind": ProductKind.SUPPLY,
        "category": str(category.pk),
        "base_price": "35.00",
    }
    body.update(overrides)
    return body


def create_as(user, category, **overrides) -> dict:
    response = client_for(user).post(
        reverse("v1:catalog:admin-products"), draft(category, **overrides), format="json"
    )
    assert response.status_code == 201, response.content
    return response.json()


def history(user, product_id, **params):
    return client_for(user).get(
        reverse("v1:catalog:admin-product-history", args=[product_id]), params
    )


# ═══════════════════════════════════════════════════════════
#  created_by / updated_by
# ═══════════════════════════════════════════════════════════


class TestWhoStamp:
    def test_create_sets_created_by_and_updated_by(self, alice, category):
        body = create_as(alice, category)

        product = Product.objects.get(pk=body["id"])
        assert product.created_by_id == alice.pk
        assert product.updated_by_id == alice.pk

    def test_update_sets_updated_by_and_keeps_created_by(self, alice, bob, category):
        body = create_as(alice, category)

        response = client_for(bob).patch(
            reverse("v1:catalog:admin-product-detail", args=[body["id"]]),
            {"name_ar": "شاش معقم"},
            format="json",
        )

        assert response.status_code == 200
        product = Product.objects.get(pk=body["id"])
        assert product.created_by_id == alice.pk
        assert product.updated_by_id == bob.pk

    def test_who_cannot_be_forged_through_the_payload(self, alice, bob, category):
        """
        ⚠️  `created_by` / `updated_by` are server-stamped. Sending someone else's
            id must change nothing, or "added by" proves nothing.
        """
        body = create_as(alice, category, created_by=str(bob.pk), updated_by=str(bob.pk))

        product = Product.objects.get(pk=body["id"])
        assert product.created_by_id == alice.pk
        assert product.updated_by_id == alice.pk

        client_for(alice).patch(
            reverse("v1:catalog:admin-product-detail", args=[body["id"]]),
            {"created_by": str(bob.pk)},
            format="json",
        )
        product.refresh_from_db()
        assert product.created_by_id == alice.pk

    def test_delete_and_restore_stamp_updated_by(self, alice, bob, category):
        body = create_as(alice, category)

        client_for(bob).delete(reverse("v1:catalog:admin-product-detail", args=[body["id"]]))
        product = Product.all_objects.get(pk=body["id"])
        assert product.deleted_at is not None
        assert product.updated_by_id == bob.pk

        client_for(alice).post(reverse("v1:catalog:admin-product-restore", args=[body["id"]]))
        product.refresh_from_db()
        assert product.deleted_at is None
        assert product.updated_by_id == alice.pk


class TestSerializerFields:
    def test_admin_list_exposes_dates_and_people_as_small_objects(self, alice, bob, category):
        body = create_as(alice, category)
        client_for(bob).patch(
            reverse("v1:catalog:admin-product-detail", args=[body["id"]]),
            {"name_en": "Sterile gauze"},
            format="json",
        )

        response = client_for(bob).get(reverse("v1:catalog:admin-products"))
        row = response.json()["results"][0]

        assert row["created_by"] == {
            "id": str(alice.pk),
            "name": "Alice Owner",
            "email": "alice@test.local",
        }
        assert row["updated_by"]["email"] == "bob@test.local"
        assert row["created_at"] and row["updated_at"]

    def test_legacy_product_without_a_stamp_serialises_as_null(self, alice, category):
        """Products created before the audit columns existed simply show "—"."""
        product = Product.objects.create(
            sku="OLD-1", name_ar="قديم", name_en="Old", category=category
        )

        row = client_for(alice).get(reverse("v1:catalog:admin-products")).json()["results"][0]

        assert row["id"] == str(product.pk)
        assert row["created_by"] is None
        assert row["updated_by"] is None

    def test_who_fields_are_not_writable(self, alice, bob, category):
        from catalog.serializers import AdminProductSerializer

        fields = AdminProductSerializer().fields
        assert fields["created_by"].read_only
        assert fields["updated_by"].read_only

    def test_list_does_not_run_a_query_per_product(
        self, alice, bob, category, django_assert_max_num_queries
    ):
        """
        ⚠️  "Added by" and "last modified by" are on every row, so resolving the
            two users lazily would be 2N extra queries. They are joined.
        """
        for index in range(12):
            create_as(alice if index % 2 else bob, category, sku=f"Q-{index}")

        client = client_for(alice)
        url = reverse("v1:catalog:admin-products")
        # Auth, permission lookups, the page query and the count — never one per row.
        with django_assert_max_num_queries(8):
            response = client.get(url, {"limit": 50})

        assert response.status_code == 200
        assert len(response.json()["results"]) == 12


class TestOrdering:
    def test_orders_by_last_modified(self, alice, category):
        first = create_as(alice, category, sku="ORD-1")
        create_as(alice, category, sku="ORD-2")

        # Touch the *older* product so it becomes the most recently modified.
        client_for(alice).patch(
            reverse("v1:catalog:admin-product-detail", args=[first["id"]]),
            {"name_en": "Touched"},
            format="json",
        )

        response = client_for(alice).get(
            reverse("v1:catalog:admin-products"), {"ordering": "-updated_at"}
        )
        assert [row["sku"] for row in response.json()["results"]] == ["ORD-1", "ORD-2"]

    def test_unknown_ordering_falls_back_instead_of_failing(self, alice, category):
        create_as(alice, category)
        response = client_for(alice).get(
            reverse("v1:catalog:admin-products"), {"ordering": "password"}
        )
        assert response.status_code == 200


# ═══════════════════════════════════════════════════════════
#  AuditLog entries
# ═══════════════════════════════════════════════════════════


class TestAuditEntries:
    def test_create_entry_references_the_product(self, alice, category):
        body = create_as(alice, category)

        entry = AuditLog.objects.get(action=AuditAction.CREATE)
        assert entry.actor_id == alice.pk
        assert entry.content_type == ContentType.objects.get_for_model(Product)
        assert entry.object_id == body["id"]
        assert entry.object_repr == "منتج AUD-001"
        assert entry.changes["sku"] == "AUD-001"

    def test_update_writes_a_diff_of_the_changed_fields_only(self, alice, bob, category):
        body = create_as(alice, category)

        client_for(bob).patch(
            reverse("v1:catalog:admin-product-detail", args=[body["id"]]),
            {"name_ar": "شاش معقم", "name_en": "Medical gauze"},  # name_en is unchanged
            format="json",
        )

        entry = AuditLog.objects.get(action=AuditAction.UPDATE)
        assert entry.actor_id == bob.pk
        assert entry.object_id == body["id"]
        assert entry.changes == {"name_ar": {"old": "شاش طبي", "new": "شاش معقم"}}

    def test_a_no_op_update_writes_no_entry(self, alice, category):
        body = create_as(alice, category)
        before = AuditLog.objects.count()

        response = client_for(alice).patch(
            reverse("v1:catalog:admin-product-detail", args=[body["id"]]),
            {"name_ar": "شاش طبي", "base_price": "35"},  # same values, other spelling
            format="json",
        )

        assert response.status_code == 200
        assert AuditLog.objects.count() == before

    def test_price_change_has_its_own_action(self, alice, category):
        body = create_as(alice, category)

        client_for(alice).patch(
            reverse("v1:catalog:admin-product-detail", args=[body["id"]]),
            {"base_price": "40.50"},
            format="json",
        )

        entry = AuditLog.objects.get(action=AuditAction.PRICE_CHANGE)
        assert entry.changes == {"base_price": {"old": "35.00", "new": "40.50"}}
        assert not AuditLog.objects.filter(action=AuditAction.UPDATE).exists()

    def test_price_and_other_edits_in_one_save_are_two_entries(self, alice, category):
        """So that filtering the log by "price change" shows only price moves."""
        body = create_as(alice, category)

        client_for(alice).patch(
            reverse("v1:catalog:admin-product-detail", args=[body["id"]]),
            {"base_price": "50", "name_en": "Gauze v2"},
            format="json",
        )

        price = AuditLog.objects.get(action=AuditAction.PRICE_CHANGE)
        update = AuditLog.objects.get(action=AuditAction.UPDATE)
        assert list(price.changes) == ["base_price"]
        assert list(update.changes) == ["name_en"]

    def test_delete_and_restore_reference_the_product(self, alice, category):
        body = create_as(alice, category)
        client_for(alice).delete(reverse("v1:catalog:admin-product-detail", args=[body["id"]]))
        client_for(alice).post(reverse("v1:catalog:admin-product-restore", args=[body["id"]]))

        for action in (AuditAction.DELETE, AuditAction.RESTORE):
            entry = AuditLog.objects.get(action=action)
            assert entry.object_id == body["id"]
            assert entry.content_type == ContentType.objects.get_for_model(Product)

    def test_helper_is_usable_without_a_request(self, alice, category):
        """Package-level helper other features (colours, tasks) log through."""
        product = Product.objects.create(sku="H-1", name_ar="ا", name_en="a", category=category)

        entry = audit.log_product_change(
            None, product, AuditAction.UPDATE, {"x": 1}, actor=alice, object_repr="لون منتج H-1"
        )

        assert entry.actor_id == alice.pk
        assert entry.object_id == str(product.pk)
        assert entry.object_repr == "لون منتج H-1"
        assert entry.ip_address is None


# ═══════════════════════════════════════════════════════════
#  History endpoint
# ═══════════════════════════════════════════════════════════


class TestHistoryEndpoint:
    def test_lists_the_timeline_newest_first_with_actor_and_changes(self, alice, bob, category):
        body = create_as(alice, category)
        client_for(bob).patch(
            reverse("v1:catalog:admin-product-detail", args=[body["id"]]),
            {"name_ar": "شاش معقم"},
            format="json",
        )

        response = history(alice, body["id"])

        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        newest, oldest = data["results"]
        assert newest["action"] == "UPDATE"
        assert newest["action_label"]
        assert newest["actor"] == {
            "id": str(bob.pk),
            "name": "Bob Editor",
            "email": "bob@test.local",
        }
        assert newest["changes"]["name_ar"]["new"] == "شاش معقم"
        assert oldest["action"] == "CREATE"
        assert oldest["actor"]["email"] == "alice@test.local"

    def test_another_products_entries_do_not_leak_in(self, alice, category):
        one = create_as(alice, category, sku="ONE")
        two = create_as(alice, category, sku="TWO")

        assert history(alice, one["id"]).json()["count"] == 1
        assert history(alice, two["id"]).json()["count"] == 1

    def test_legacy_entries_are_matched_by_their_text(self, alice, category):
        """Rows written before the generic reference existed carried only the SKU in text."""
        product = Product.objects.create(sku="LEG-1", name_ar="ق", name_en="L", category=category)
        AuditLog.objects.create(
            actor=alice, action=AuditAction.CREATE, object_repr="منتج LEG-1", changes={}
        )
        AuditLog.objects.create(
            actor=alice, action=AuditAction.CREATE, object_repr="منتج OTHER", changes={}
        )

        data = history(alice, product.pk).json()

        assert data["count"] == 1
        assert data["results"][0]["object_repr"] == "منتج LEG-1"

    def test_deleted_product_still_has_a_history(self, alice, category):
        body = create_as(alice, category)
        client_for(alice).delete(reverse("v1:catalog:admin-product-detail", args=[body["id"]]))

        actions = [row["action"] for row in history(alice, body["id"]).json()["results"]]

        assert actions == ["DELETE", "CREATE"]

    def test_filters_by_actor_and_action(self, alice, bob, category):
        body = create_as(alice, category)
        client_for(bob).patch(
            reverse("v1:catalog:admin-product-detail", args=[body["id"]]),
            {"base_price": "99"},
            format="json",
        )

        by_bob = history(alice, body["id"], actor=str(bob.pk)).json()
        assert [row["action"] for row in by_bob["results"]] == ["PRICE_CHANGE"]

        prices = history(alice, body["id"], action="PRICE_CHANGE").json()
        assert prices["count"] == 1

        assert history(alice, body["id"], actor="not-a-uuid").json()["count"] == 0

    def test_unknown_product_is_404(self, alice):
        import uuid

        assert history(alice, uuid.uuid4()).status_code == 404

    def test_requires_the_catalog_permission(self, alice, category):
        body = create_as(alice, category)
        nobody = make_admin("nobody@test.local", grant=False)

        assert history(nobody, body["id"]).status_code == 403
        assert APIClient().get(
            reverse("v1:catalog:admin-product-history", args=[body["id"]])
        ).status_code in (401, 403)

    def test_decimal_spelling_is_not_a_price_change(self):
        """`35.00` vs `35.0` vs `35` is one price; the snapshot quantises to the column."""
        product = Product(sku="D", name_ar="د", name_en="d", base_price=Decimal("35"))
        other = Product(sku="D", name_ar="د", name_en="d", base_price=Decimal("35.00"))

        assert audit.diff(audit.snapshot(product), audit.snapshot(other)) == {}
