"""
اختبارات الكتالوج.

⚠️  ثلاث مجموعات حرجة:
      ١. الفلترة بالسياسات — المقيّد لا يظهر ولا يُفتح بالرابط
      ٢. غياب N+1 — الخطأ الذي أنتجه النموذج القديم
      ٣. ثبات الـ slug — تغييره يكسر الروابط و SEO
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
    """منتجان: عام ومقيّد بالصيدليات."""
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
#  الفلترة بالسياسات
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
        ⚠️  الفارق بين `403` و`404` يكشف قائمة المقيّد بمسح الروابط.
        """
        client = APIClient()
        client.force_authenticate(user=make_user("direct@test.local"))

        response = client.get(
            reverse("v1:catalog:product-detail", args=[catalog["restricted"].slug])
        )
        assert response.status_code == 404

    def test_search_does_not_leak_restricted(self, catalog):
        """البحث بالاسم الصريح لا يكشف المقيّد."""
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
#  الأداء — الخطأ الذي أنتجه النموذج القديم
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestNoNPlusOne:
    def test_product_list_query_count_is_constant(
        self, policies, category, django_assert_max_num_queries
    ):
        """
        ⚠️  النموذج القديم وضع `avg_rate` و`reviews_count` كـ
            properties على `Product` — استعلامان لكل صف.
            عشرون منتجًا = ٤١ استعلامًا.

        هنا العدد ثابت مهما كبر عدد المنتجات.
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
#  الشجرة
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
        ⚠️  نقل فئة يغيّر مسار كل ما تحتها.

        تجاهل ذلك يترك أحفادًا بمسارات ميتة فيختفون من كل استعلام
        شجري — ومنتجاتهم تختفي من صفحة الفئة الأب.
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
        """فتح فئة أب يُظهر منتجات ما تحتها."""
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
        """PROTECT — حذف فئة تحمل منتجات يترك منتجات بلا تصنيف."""
        from django.db.models import ProtectedError

        with pytest.raises(ProtectedError):
            category.hard_delete()


# ═══════════════════════════════════════════════════════════
#  الـ slug
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSlugStability:
    def test_slug_is_generated_once_and_never_changes(self, catalog):
        """
        ⚠️  الكود القديم أعاد توليد الـ slug في **كل حفظ** — أي أن
            تعديل اسم منتج يكسر رابطه وكل فهرسة أشارت إليه.
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
#  حدود النطاق
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestDomainBoundaries:
    def test_product_has_no_stock_field(self):
        """
        ⚠️  `Product.quantity` كان الانتهاك رقم H4 في التدقيق —
            الكتالوج يجيب عن سؤال المخزون.
        """
        forbidden = {"quantity", "stock", "available", "in_stock", "stock_quantity"}
        actual = {f.name for f in Product._meta.get_fields()}
        assert not (forbidden & actual)

    def test_product_has_no_computed_rating_property(self):
        """
        ⚠️  `avg_rate` و`reviews_count` كانتا properties تستعلمان
            لكل صف — الانتهاك H8.

        البديل: `reviews.ProductRating` عبر `select_related`.
        """
        assert not hasattr(Product, "avg_rate")
        assert not hasattr(Product, "reviews_count")

    def test_product_has_no_final_price_field(self):
        """السعر النهائي يحسبه `pricing` حسب العميل."""
        actual = {f.name for f in Product._meta.get_fields()}
        assert "price" not in actual
        assert "final_price" not in actual
        assert "base_price" in actual  # مرجع للمحرك لا سعر نهائي
