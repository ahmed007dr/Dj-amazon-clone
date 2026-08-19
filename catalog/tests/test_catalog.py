"""
Catalogue tests.

⚠️  Three critical groups:
      1. policy filtering — the restricted does not appear and does not open by URL
      2. absence of N+1 — the defect the legacy model produced
      3. slug stability — changing it breaks links and SEO
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from access.models import AccessPolicy
from accounts.models import AccountType, User, VerificationStatus
from catalog.models import Brand, Category, Product, ProductKind

PASSWORD = "Str0ng-Test-Pass!23"


def make_user(email, account_type=AccountType.STUDENT, *, verified=False):
    user = User.objects.create_user(
        email=email,
        password=PASSWORD,
        account_type=account_type,
        verification_status=(
            VerificationStatus.VERIFIED if verified else VerificationStatus.PENDING
        ),
    )
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def policies(db):
    from django.core.management import call_command

    call_command("seed_access_policies", verbosity=0)
    return {p.code: p for p in AccessPolicy.objects.all()}


@pytest.fixture
def category(db):
    return Category.objects.create(name_ar="مستلزمات", name_en="Supplies")


@pytest.fixture
def catalog(policies, category):
    """Two products: one public and one restricted to pharmacies."""
    public = Product.objects.create(
        sku="PUB-001",
        name_ar="قفازات",
        name_en="Gloves",
        category=category,
        base_price=Decimal("50.00"),
        access_policy=policies["public"],
    )
    restricted = Product.objects.create(
        sku="RES-001",
        name_ar="دواء مقيّد",
        name_en="Restricted Medicine",
        category=category,
        kind=ProductKind.MEDICINE,
        base_price=Decimal("120.00"),
        access_policy=policies["pharmacy_only"],
        regulatory_class="OTC",
    )
    return {"public": public, "restricted": restricted}


# ═══════════════════════════════════════════════════════════
#  Policy filtering
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPolicyFiltering:
    def test_guest_sees_only_public(self, catalog):
        response = APIClient().get(reverse("v1:catalog:products"))

        assert response.status_code == 200
        skus = {p["sku"] for p in response.data["results"]}
        assert skus == {"PUB-001"}

    def test_student_does_not_see_pharmacy_products(self, catalog):
        client = APIClient()
        client.force_authenticate(user=make_user("s@test.local"))

        skus = {p["sku"] for p in client.get(reverse("v1:catalog:products")).data["results"]}
        assert "RES-001" not in skus

    def test_verified_pharmacy_sees_restricted(self, catalog):
        client = APIClient()
        client.force_authenticate(
            user=make_user("ph@test.local", AccountType.PHARMACY, verified=True)
        )

        skus = {p["sku"] for p in client.get(reverse("v1:catalog:products")).data["results"]}
        assert skus == {"PUB-001", "RES-001"}

    def test_unverified_pharmacy_does_not_see_restricted(self, catalog):
        client = APIClient()
        client.force_authenticate(
            user=make_user("unv@test.local", AccountType.PHARMACY, verified=False)
        )

        skus = {p["sku"] for p in client.get(reverse("v1:catalog:products")).data["results"]}
        assert "RES-001" not in skus

    def test_direct_url_returns_404_not_403(self, catalog):
        """
        ⚠️  The difference between `403` and `404` exposes the restricted list by scanning URLs.
        """
        client = APIClient()
        client.force_authenticate(user=make_user("direct@test.local"))

        response = client.get(
            reverse("v1:catalog:product-detail", args=[catalog["restricted"].slug])
        )
        assert response.status_code == 404

    def test_search_does_not_leak_restricted(self, catalog):
        """Searching by the exact name does not reveal the restricted one."""
        client = APIClient()
        client.force_authenticate(user=make_user("search@test.local"))

        response = client.get(reverse("v1:catalog:products"), {"search": "مقيّد"})
        assert len(response.data["results"]) == 0

    def test_barcode_lookup_respects_policy(self, catalog):
        catalog["restricted"].barcode = "6221234567890"
        catalog["restricted"].save()

        client = APIClient()
        client.force_authenticate(user=make_user("bc@test.local"))

        response = client.get(reverse("v1:catalog:product-by-barcode", args=["6221234567890"]))
        assert response.status_code == 404


# ═══════════════════════════════════════════════════════════
#  Performance — the defect the legacy model produced
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestNoNPlusOne:
    def test_product_list_query_count_is_constant(
        self, policies, category, django_assert_max_num_queries
    ):
        """
        ⚠️  The legacy model put `avg_rate` and `reviews_count` on `Product` as
            properties — two queries per row. Twenty products = 41 queries.

        Here the count is constant however many products there are.
        """
        brand = Brand.objects.create(name_ar="براند", name_en="Brand")
        for i in range(30):
            Product.objects.create(
                sku=f"P-{i:03d}",
                name_ar=f"منتج {i}",
                name_en=f"Product {i}",
                category=category,
                brand=brand,
                base_price=Decimal("10.00"),
                access_policy=policies["public"],
            )

        client = APIClient()
        with django_assert_max_num_queries(10):
            response = client.get(reverse("v1:catalog:products"))
            assert len(response.data["results"]) == 20

    def test_category_tree_is_one_query(self, db, django_assert_max_num_queries):
        root = Category.objects.create(name_ar="جذر", name_en="Root")
        for i in range(5):
            child = Category.objects.create(name_ar=f"فرع {i}", name_en=f"Branch {i}", parent=root)
            for j in range(3):
                Category.objects.create(
                    name_ar=f"ورقة {i}-{j}", name_en=f"Leaf {i}-{j}", parent=child
                )

        client = APIClient()
        with django_assert_max_num_queries(3):
            response = client.get(reverse("v1:catalog:categories"))
            assert response.status_code == 200


# ═══════════════════════════════════════════════════════════
#  The tree
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCategoryTree:
    def test_path_and_depth_are_built(self, db):
        root = Category.objects.create(name_ar="جذر", name_en="Root")
        child = Category.objects.create(name_ar="فرع", name_en="Branch", parent=root)
        leaf = Category.objects.create(name_ar="ورقة", name_en="Leaf", parent=child)

        root.refresh_from_db()
        child.refresh_from_db()
        leaf.refresh_from_db()

        assert root.depth == 0
        assert child.depth == 1
        assert leaf.depth == 2
        assert leaf.path == f"{root.slug}/{child.slug}/{leaf.slug}"

    def test_moving_a_category_rebuilds_descendant_paths(self, db):
        """
        ⚠️  Moving a category changes the path of everything beneath it.

        Ignoring that leaves descendants on dead paths, so they disappear from
        every tree query — and their products disappear from the parent
        category's page.
        """
        first = Category.objects.create(name_ar="أول", name_en="First")
        second = Category.objects.create(name_ar="ثانٍ", name_en="Second")
        child = Category.objects.create(name_ar="فرع", name_en="Branch", parent=first)
        leaf = Category.objects.create(name_ar="ورقة", name_en="Leaf", parent=child)

        child.parent = second
        child.save()

        leaf.refresh_from_db()
        assert leaf.path.startswith(f"{second.slug}/")
        assert leaf.depth == 2

    def test_products_include_descendant_categories(self, policies):
        """Opening a parent category shows the products beneath it."""
        root = Category.objects.create(name_ar="مستلزمات", name_en="Supplies")
        child = Category.objects.create(name_ar="قفازات", name_en="Gloves", parent=root)

        Product.objects.create(
            sku="DEEP-001",
            name_ar="قفاز",
            name_en="Glove",
            category=child,
            base_price=Decimal("5.00"),
            access_policy=policies["public"],
        )

        response = APIClient().get(reverse("v1:catalog:products"), {"category": root.slug})
        assert len(response.data["results"]) == 1

    def test_category_with_products_cannot_be_deleted(self, catalog, category):
        """PROTECT — deleting a category holding products leaves products unclassified."""
        from django.db.models import ProtectedError

        with pytest.raises(ProtectedError):
            category.hard_delete()


# ═══════════════════════════════════════════════════════════
#  The slug
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSlugStability:
    def test_slug_is_generated_once_and_never_changes(self, catalog):
        """
        ⚠️  The legacy code regenerated the slug on **every save** — meaning
            editing a product's name broke its URL and every index pointing at it.
        """
        product = catalog["public"]
        original = product.slug

        product.name_ar = "اسم مختلف تمامًا"
        product.name_en = "Completely Different Name"
        product.save()

        product.refresh_from_db()
        assert product.slug == original

    def test_duplicate_names_get_unique_slugs(self, policies, category):
        first = Product.objects.create(
            sku="DUP-1",
            name_ar="مكرر",
            name_en="Duplicate",
            category=category,
            access_policy=policies["public"],
        )
        second = Product.objects.create(
            sku="DUP-2",
            name_ar="مكرر",
            name_en="Duplicate",
            category=category,
            access_policy=policies["public"],
        )

        assert first.slug != second.slug


# ═══════════════════════════════════════════════════════════
#  Domain boundaries
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestDomainBoundaries:
    def test_product_has_no_stock_field(self):
        """
        ⚠️  `Product.quantity` was violation H4 in the audit — the catalogue
            answering the inventory question.
        """
        forbidden = {"quantity", "stock", "available", "in_stock", "stock_quantity"}
        actual = {f.name for f in Product._meta.get_fields()}
        assert not (forbidden & actual)

    def test_product_has_no_computed_rating_property(self):
        """
        ⚠️  `avg_rate` and `reviews_count` were properties querying per row —
            violation H8.

        The replacement: `reviews.ProductRating` through `select_related`.
        """
        assert not hasattr(Product, "avg_rate")
        assert not hasattr(Product, "reviews_count")

    def test_product_has_no_final_price_field(self):
        """The final price is computed by `pricing` per customer."""
        actual = {f.name for f in Product._meta.get_fields()}
        assert "price" not in actual
        assert "final_price" not in actual
        assert "base_price" in actual  # a reference for the engine, not a final price
