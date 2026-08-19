"""
Tests for adding study bundles to the cart.

⚠️  These live in `cart/`, not `academic/`.

    `academic` is in L2 and `cart` in L5 — and the test touches both.
    The standing rule: **a test lives in the highest domain among those it
    touches**, so the dependency stays downward.

    And `import-linter` caught it being placed in `academic` the moment it was written.
"""

from decimal import Decimal

import pytest
from django.apps import apps

from academic.models import BundleItem, StudyBundle
from accounts.models import AccountType, User
from cart import services as cart_services
from catalog.models import Category, Product
from customers.models import CustomerProfile
from inventory import services as inventory_services

PASSWORD = "Str0ng-Test-Pass!23"


def location_model():
    return apps.get_model("inventory", "StockLocation")


@pytest.fixture
def location(db):
    return location_model().objects.create(
        code="main", name_ar="الرئيسي", name_en="Main", is_default=True
    )


@pytest.fixture
def student_user(db):
    user = User.objects.create_user(
        email="student@test.local", password=PASSWORD, account_type=AccountType.STUDENT
    )
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def faculty(db):
    from academic.models import Faculty, University

    university = University.objects.create(code="cu", name_ar="القاهرة", name_en="Cairo")
    return Faculty.objects.create(
        university=university,
        code="pharm",
        name_ar="الصيدلة",
        name_en="Pharmacy",
        years_count=5,
    )


@pytest.fixture
def products(db):
    category = Category.objects.create(name_ar="فئة", name_en="Category")
    return [
        Product.objects.create(
            sku=f"B-{i}",
            name_ar=f"صنف {i}",
            name_en=f"Item {i}",
            category=category,
            base_price=Decimal("50.00"),
        )
        for i in range(3)
    ]


@pytest.fixture
def stocked_bundle(faculty, products, location):
    bundle = StudyBundle.objects.create(
        faculty=faculty, academic_year=2, name_ar="حزمة", name_en="Bundle"
    )
    for product in products:
        BundleItem.objects.create(bundle=bundle, product=product, quantity=2)
        inventory_services.receive(product, 10, Decimal("30.00"), location=location)
    return bundle


@pytest.mark.django_db
class TestBundleToCart:
    def test_bundle_expands_into_separate_lines(self, student_user, stocked_bundle, products):
        """
        ⚠️  A bundle is not a product.

        Adding it as a single item means phantom stock that does not reflect
        its components' availability, and pricing that ignores the customer's
        price list.
        """
        cart = cart_services.get_active_cart(user=student_user)
        result = cart_services.add_bundle(cart, stocked_bundle, user=student_user)

        assert result["is_complete"]
        assert len(result["added"]) == 3
        assert cart.lines.count() == 3
        assert cart.lines.first().quantity == 2

    def test_partial_failure_still_adds_what_it_can(
        self, student_user, stocked_bundle, products, location
    ):
        """
        ⚠️  One item out of three being out of stock must not block the other two.

        Rejecting the whole bundle over one item loses the entire sale.
        """
        inventory_services.sell_immediately(products[0], 10, location=location)

        cart = cart_services.get_active_cart(user=student_user)
        result = cart_services.add_bundle(cart, stocked_bundle, user=student_user)

        assert not result["is_complete"]
        assert len(result["added"]) == 2
        assert len(result["skipped"]) == 1
        assert result["skipped"][0]["code"] == "INSUFFICIENT_STOCK"

    def test_essentials_only_skips_optional_items(self, student_user, faculty, products, location):
        bundle = StudyBundle.objects.create(
            faculty=faculty, academic_year=2, name_ar="حزمة", name_en="Bundle"
        )
        BundleItem.objects.create(bundle=bundle, product=products[0], is_essential=True)
        BundleItem.objects.create(bundle=bundle, product=products[1], is_essential=False)

        for product in products[:2]:
            inventory_services.receive(product, 10, Decimal("30.00"), location=location)

        cart = cart_services.get_active_cart(user=student_user)
        result = cart_services.add_bundle(cart, bundle, user=student_user, essentials_only=True)

        assert len(result["added"]) == 1


@pytest.mark.django_db
class TestProfileSeparation:
    def test_student_profile_is_separate_from_customer_profile(self):
        """
        ⚠️  Being a student is **additional** context that ends at graduation;
            their customer profile remains.

        Merging them means dead academic fields on every non-student customer's profile.
        """
        customer_fields = {f.name for f in CustomerProfile._meta.get_fields()}

        assert "university" not in customer_fields
        assert "faculty" not in customer_fields
        assert "academic_year" not in customer_fields
