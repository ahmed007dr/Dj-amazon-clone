"""
Reference classification from the admin panel — categories, brands and manufacturers.

⚠️  **This is a precondition, not a luxury**: the category is mandatory on
    `Product`, so a store with no categories screen cannot add its first item
    from its panel. And all three used to be managed from the Django panel alone.

⚠️  Two things are guarded here: the tree does not break, and what is in use is
    not deleted silently.
"""

import pytest
from django.apps import apps
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from catalog.models import Brand, Category, Manufacturer, Product

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_user(
        email="ref-admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    admin.is_active = True
    admin.save()
    apps.get_model("administration", "AdminProfile").objects.create(user=admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


# ═══════════════════════════════════════════════════════════
#  Categories — the tree
# ═══════════════════════════════════════════════════════════


class TestCategoryTree:
    def test_creating_a_child_builds_its_path(self, admin_client):
        """
        ⚠️  The path is what makes "everything under Medicines" a single query.
            A category with a wrong path disappears from every tree query.
        """
        root = admin_client.post(
            reverse("v1:catalog:admin-categories"),
            {"name_ar": "أدوية", "name_en": "Medicines"},
            format="json",
        )
        assert root.status_code == 201

        child = admin_client.post(
            reverse("v1:catalog:admin-categories"),
            {"name_ar": "مسكّنات", "name_en": "Painkillers", "parent": root.data["id"]},
            format="json",
        )

        assert child.status_code == 201
        node = Category.objects.get(pk=child.data["id"])
        assert node.depth == 1
        assert node.path.endswith("/painkillers")

    def test_moving_a_category_rebuilds_descendant_paths(self, admin_client):
        """Moving a category changes the path of everything beneath it — ignoring that orphans descendants."""
        a = Category.objects.create(name_ar="أ", name_en="A")
        b = Category.objects.create(name_ar="ب", name_en="B")
        child = Category.objects.create(name_ar="ج", name_en="C", parent=a)

        admin_client.patch(
            reverse("v1:catalog:admin-category-detail", args=[child.pk]),
            {"parent": str(b.pk)},
            format="json",
        )

        child.refresh_from_db()
        assert child.path.startswith(b.path)

    def test_a_category_cannot_be_its_own_parent(self, admin_client):
        """
        ⚠️  A cycle makes the path rebuild call itself endlessly, hanging the
            request forever with no trace in any log.
        """
        node = Category.objects.create(name_ar="فئة", name_en="Cat")

        response = admin_client.patch(
            reverse("v1:catalog:admin-category-detail", args=[node.pk]),
            {"parent": str(node.pk)},
            format="json",
        )
        assert response.status_code == 400

    def test_a_category_cannot_move_into_its_own_branch(self, admin_client):
        parent = Category.objects.create(name_ar="أب", name_en="Parent")
        child = Category.objects.create(name_ar="ابن", name_en="Child", parent=parent)

        response = admin_client.patch(
            reverse("v1:catalog:admin-category-detail", args=[parent.pk]),
            {"parent": str(child.pk)},
            format="json",
        )
        assert response.status_code == 400

    def test_slug_and_path_are_computed_not_accepted(self, admin_client):
        """Accepting them from the client means a tree written by someone who does not know its rules."""
        response = admin_client.post(
            reverse("v1:catalog:admin-categories"),
            {"name_ar": "فئة", "name_en": "Cat", "slug": "hacked", "path": "hacked", "depth": 9},
            format="json",
        )

        assert response.status_code == 201
        node = Category.objects.get(pk=response.data["id"])
        assert node.slug != "hacked"
        assert node.depth == 0

    def test_the_list_includes_categories_hidden_from_the_menu(self, admin_client):
        """`show_in_menu` is a display classification, not a permission — and the admin manages everything."""
        Category.objects.create(name_ar="مخفية", name_en="Hidden", show_in_menu=False)

        response = admin_client.get(reverse("v1:catalog:admin-categories"))
        assert [row["name_ar"] for row in response.data] == ["مخفية"]


# ═══════════════════════════════════════════════════════════
#  Guarded deletion
# ═══════════════════════════════════════════════════════════


class TestGuardedDelete:
    def test_a_category_with_products_is_not_deleted(self, admin_client):
        """
        ⚠️  The `PROTECT` relation prevents it in the database, but the error
            arrives there as a crash rather than a message. The check here turns
            it into a sentence carrying **the count** — which is what the admin
            needs to decide.
        """
        category = Category.objects.create(name_ar="فئة", name_en="Cat")
        Product.objects.create(sku="P-1", name_ar="م", name_en="P", category=category)

        response = admin_client.delete(
            reverse("v1:catalog:admin-category-detail", args=[category.pk])
        )

        assert response.status_code == 409
        assert "1" in response.data["detail"]
        assert Category.objects.filter(pk=category.pk).exists()

    def test_a_category_with_children_is_not_deleted(self, admin_client):
        parent = Category.objects.create(name_ar="أب", name_en="Parent")
        Category.objects.create(name_ar="ابن", name_en="Child", parent=parent)

        response = admin_client.delete(
            reverse("v1:catalog:admin-category-detail", args=[parent.pk])
        )
        assert response.status_code == 409

    def test_an_empty_category_is_deleted(self, admin_client):
        category = Category.objects.create(name_ar="فارغة", name_en="Empty")

        response = admin_client.delete(
            reverse("v1:catalog:admin-category-detail", args=[category.pk])
        )

        assert response.status_code == 204
        assert not Category.objects.filter(pk=category.pk).exists()

    def test_a_brand_in_use_is_not_deleted(self, admin_client):
        category = Category.objects.create(name_ar="فئة", name_en="Cat")
        brand = Brand.objects.create(name_ar="براند", name_en="Brand")
        Product.objects.create(sku="P-2", name_ar="م", name_en="P", category=category, brand=brand)

        response = admin_client.delete(reverse("v1:catalog:admin-brand-detail", args=[brand.pk]))
        assert response.status_code == 409

    def test_a_manufacturer_with_brands_is_not_deleted(self, admin_client):
        maker = Manufacturer.objects.create(name_ar="شركة", name_en="Maker")
        Brand.objects.create(name_ar="براند", name_en="Brand", manufacturer=maker)

        response = admin_client.delete(
            reverse("v1:catalog:admin-manufacturer-detail", args=[maker.pk])
        )
        assert response.status_code == 409


# ═══════════════════════════════════════════════════════════
#  Brands and manufacturers
# ═══════════════════════════════════════════════════════════


class TestBrandsAndManufacturers:
    def test_a_brand_is_created_and_linked_to_a_manufacturer(self, admin_client):
        maker = Manufacturer.objects.create(name_ar="فايزر", name_en="Pfizer", country="US")

        response = admin_client.post(
            reverse("v1:catalog:admin-brands"),
            {"name_ar": "براند", "name_en": "Brand", "manufacturer": str(maker.pk)},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["manufacturer_name"] == "فايزر"

    def test_counts_make_the_impact_visible_before_deleting(self, admin_client):
        """Seeing "12 products" before pressing turns the decision from a guess into knowledge."""
        category = Category.objects.create(name_ar="فئة", name_en="Cat")
        brand = Brand.objects.create(name_ar="براند", name_en="Brand")
        Product.objects.create(sku="P-3", name_ar="م", name_en="P", category=category, brand=brand)

        response = admin_client.get(reverse("v1:catalog:admin-brands"))
        assert response.data[0]["product_count"] == 1

    def test_creation_is_written_to_the_audit_log(self, admin_client):
        admin_client.post(
            reverse("v1:catalog:admin-manufacturers"),
            {"name_ar": "شركة جديدة", "name_en": "New maker"},
            format="json",
        )

        entry = (
            apps.get_model("core", "AuditLog")
            .objects.filter(action="CREATE", object_repr__contains="شركة جديدة")
            .first()
        )
        assert entry is not None


# ═══════════════════════════════════════════════════════════
#  Permissions
# ═══════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "route",
    ["v1:catalog:admin-categories", "v1:catalog:admin-brands", "v1:catalog:admin-manufacturers"],
)
def test_customers_cannot_touch_the_reference_catalog(route):
    """
    ⚠️  Whoever adds a category adds a browsing surface for the whole store —
        this is the site's structure, not internal data.
    """
    customer = User.objects.create_user(email="c@test.local", password=PASSWORD)
    customer.is_active = True
    customer.save()

    client = APIClient()
    client.force_authenticate(user=customer)

    assert client.get(reverse(route)).status_code == 403
    assert (
        client.post(reverse(route), {"name_ar": "x", "name_en": "x"}, format="json").status_code
        == 403
    )
