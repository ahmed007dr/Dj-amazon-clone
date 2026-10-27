"""
Guest-cart hardening (guest checkout, phase 1).

⚠️  Three things were true of the guest cart before a visitor could *buy* with it:

      1. the session key was stored exactly as sent (no format, no length check);
      2. nothing stopped two ACTIVE carts sharing one key;
      3. a bundle could be added with no account at all.

    Each is cheap to ignore while a guest cart is only a basket, and expensive
    once it is the thing an order is made from.
"""

from decimal import Decimal

import pytest
from django.apps import apps
from django.db import IntegrityError, transaction
from django.urls import reverse
from rest_framework.test import APIClient

from academic.models import BundleItem, StudyBundle
from access.models import AccessPolicy
from accounts.models import AccountType, User
from cart import services
from cart.models import Cart, CartLine, CartStatus
from catalog.models import Category, Product
from core.errors import BusinessError
from inventory import services as inventory_services

PASSWORD = "Str0ng-Test-Pass!23"
KEY = "5b0c8a52-1d33-4d3c-9b58-0c1b6b6a0a01"


def make_user(email, account_type=AccountType.STUDENT):
    user = User.objects.create_user(email=email, password=PASSWORD, account_type=account_type)
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def location(db):
    return apps.get_model("inventory", "StockLocation").objects.create(
        code="main", name_ar="الرئيسي", name_en="Main", is_default=True
    )


@pytest.fixture
def policies(db):
    from django.core.management import call_command

    call_command("seed_access_policies", verbosity=0)
    return {p.code: p for p in AccessPolicy.objects.all()}


@pytest.fixture
def category(db):
    return Category.objects.create(name_ar="فئة", name_en="Category")


def make_product(sku, category, policy, location, stock=20):
    product = Product.objects.create(
        sku=sku,
        name_ar=f"منتج {sku}",
        name_en=f"Product {sku}",
        category=category,
        base_price=Decimal("100.00"),
        access_policy=policy,
    )
    inventory_services.receive(product, stock, Decimal("60.00"), location=location)
    return product


@pytest.fixture
def product(category, policies, location):
    return make_product("G-001", category, policies["public"], location)


# ═══════════════════════════════════════════════════════════
#  The session key
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSessionKeyValidation:
    @pytest.mark.parametrize(
        "bad",
        [
            "guest-abc-123",  # not a UUID
            "x" * 65,  # would overflow the column (a 500 on Postgres)
            "x" * 4000,
            "not a uuid at all",
            "../../etc/passwd",
            "12345678-1234-1234-1234-12345678901",  # one char short
        ],
    )
    def test_malformed_key_is_a_400_not_a_500(self, product, bad):
        response = APIClient().post(
            reverse("v1:cart:lines"),
            {"product": str(product.pk), "quantity": 1},
            format="json",
            HTTP_X_CART_SESSION=bad,
        )
        assert response.status_code == 400
        assert response.data["code"] == "VALIDATION_ERROR"
        assert not Cart.objects.exists()

    def test_missing_key_is_still_a_400(self, product):
        response = APIClient().get(reverse("v1:cart:detail"))
        assert response.status_code == 400

    def test_one_browser_is_one_cart_whatever_the_spelling(self, product):
        """`ABC…` and `abc…` must not open two carts for the same browser."""
        guest = APIClient()
        for spelling in (KEY, KEY.upper(), KEY.replace("-", "")):
            guest.post(
                reverse("v1:cart:lines"),
                {"product": str(product.pk), "quantity": 1},
                format="json",
                HTTP_X_CART_SESSION=spelling,
            )

        assert Cart.objects.filter(status=CartStatus.ACTIVE).count() == 1
        assert Cart.objects.get().session_key == KEY
        assert CartLine.objects.get().quantity == 3

    def test_merge_validates_the_key_too(self, product):
        member = make_user("member@test.local")
        client = APIClient()
        client.force_authenticate(user=member)

        bad = client.post(reverse("v1:cart:merge"), {"session_key": "x" * 200}, format="json")
        assert bad.status_code == 400

        not_text = client.post(reverse("v1:cart:merge"), {"session_key": 12345}, format="json")
        assert not_text.status_code == 400

        missing = client.post(reverse("v1:cart:merge"), {}, format="json")
        assert missing.status_code == 400

        fine = client.post(reverse("v1:cart:merge"), {"session_key": KEY}, format="json")
        assert fine.status_code == 200


# ═══════════════════════════════════════════════════════════
#  One active cart per guest key
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestOneActiveCartPerSession:
    def test_the_database_refuses_a_second_active_cart(self):
        Cart.objects.create(session_key=KEY)
        with pytest.raises(IntegrityError), transaction.atomic():
            Cart.objects.create(session_key=KEY)

    def test_a_converted_or_merged_cart_does_not_block_a_new_one(self):
        old = Cart.objects.create(session_key=KEY)
        old.status = CartStatus.CONVERTED
        old.save()
        Cart.objects.create(session_key=KEY)  # the next basket of the same browser

    def test_user_carts_with_no_key_are_unaffected(self):
        # The constraint is over non-empty keys: members' carts all have ""
        Cart.objects.create(user=make_user("a@test.local"))
        Cart.objects.create(user=make_user("b@test.local"))

    def test_losing_the_creation_race_returns_the_winners_cart(self, monkeypatch):
        """
        Two first requests: both see "no cart", one creates it. The loser must
        get *that* cart back instead of a 500.
        """
        winner = Cart.objects.create(session_key=KEY)

        real_filter = Cart.objects.filter
        seen = {"first_calls": 0}

        class BlindOnce:
            def __init__(self, queryset):
                self.queryset = queryset

            def first(self):
                seen["first_calls"] += 1
                return None if seen["first_calls"] == 1 else self.queryset.first()

        monkeypatch.setattr(Cart.objects, "filter", lambda *a, **k: BlindOnce(real_filter(*a, **k)))

        cart = services.get_active_cart(session_key=KEY)

        assert cart.pk == winner.pk
        assert seen["first_calls"] == 2

    def test_migration_folds_existing_duplicates(self, product):
        """
        The data step of 0002 must leave nothing for the new index to reject.
        The legacy state (two ACTIVE carts, one key) is exactly what the new
        index refuses, so the index is dropped first — inside the test's own
        transaction, which rolls it back afterwards.
        """
        import importlib

        from django.db import connection

        migration = importlib.import_module("cart.migrations.0002_unique_active_cart_per_session")

        with connection.cursor() as cursor:
            cursor.execute("DROP INDEX unique_active_cart_per_session")

        first = Cart.objects.create(session_key=KEY)
        CartLine.objects.create(cart=first, product=product, quantity=2)
        second = Cart.objects.create(session_key=KEY)
        CartLine.objects.create(cart=second, product=product, quantity=3)

        migration.merge_duplicate_active_guest_carts(apps, None)

        active = Cart.objects.filter(session_key=KEY, status=CartStatus.ACTIVE)
        assert active.count() == 1
        assert active.get().lines.get().quantity == 5
        assert Cart.objects.filter(session_key=KEY, status=CartStatus.MERGED).count() == 1


# ═══════════════════════════════════════════════════════════
#  Bundles need an account
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def bundle(category, policies, location):
    from academic.models import Faculty, University

    university = University.objects.create(code="cu", name_ar="القاهرة", name_en="Cairo")
    faculty = Faculty.objects.create(
        university=university, code="ph", name_ar="الصيدلة", name_en="Pharmacy", years_count=5
    )
    bundle = StudyBundle.objects.create(
        faculty=faculty, academic_year=1, name_ar="حزمة", name_en="Bundle"
    )
    item = make_product("B-001", category, policies["public"], location)
    BundleItem.objects.create(bundle=bundle, product=item, quantity=1)
    return bundle


@pytest.mark.django_db
class TestBundleNeedsAnAccount:
    def test_guest_cannot_add_a_bundle_over_http(self, bundle):
        response = APIClient().post(
            reverse("v1:cart:bundle"),
            {"bundle": str(bundle.pk)},
            format="json",
            HTTP_X_CART_SESSION=KEY,
        )
        assert response.status_code == 401
        assert not CartLine.objects.exists()

    def test_signed_in_user_can(self, bundle):
        member = make_user("member@test.local")
        client = APIClient()
        client.force_authenticate(user=member)

        response = client.post(reverse("v1:cart:bundle"), {"bundle": str(bundle.pk)}, format="json")

        assert response.status_code == 201
        assert response.data["bundle_result"]["is_complete"]

    def test_any_account_type_may_add_a_bundle(self, bundle):
        """The gate is "signed in", not "student" (owner decision)."""
        shopper = make_user("pharma@test.local", AccountType.PHARMACY)
        client = APIClient()
        client.force_authenticate(user=shopper)

        response = client.post(reverse("v1:cart:bundle"), {"bundle": str(bundle.pk)}, format="json")
        assert response.status_code == 201

    def test_the_service_fails_closed_for_a_guest_cart(self, bundle):
        guest_cart = services.get_active_cart(session_key=KEY)

        with pytest.raises(BusinessError) as caught:
            services.add_bundle(guest_cart, bundle)

        assert caught.value.code == "AUTHENTICATION_REQUIRED"
        assert caught.value.status_code == 401
        assert guest_cart.lines.count() == 0

    def test_the_service_refuses_an_anonymous_user_object(self, bundle):
        from django.contrib.auth.models import AnonymousUser

        guest_cart = services.get_active_cart(session_key=KEY)
        with pytest.raises(BusinessError):
            services.add_bundle(guest_cart, bundle, user=AnonymousUser())

    def test_a_members_cart_is_enough_even_without_user_argument(self, bundle):
        member = make_user("member@test.local")
        cart = services.get_active_cart(user=member)

        result = services.add_bundle(cart, bundle)  # user inferred from the cart

        assert result["is_complete"]


# ═══════════════════════════════════════════════════════════
#  Coupons are for accounts
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestGuestCoupons:
    def test_applying_a_coupon_as_a_guest_is_refused_clearly(self, product):
        from promotions.models import Coupon, CouponKind

        Coupon.objects.create(
            code="SAVE20",
            name_ar="خصم",
            name_en="Discount",
            kind=CouponKind.PERCENTAGE,
            value=Decimal("20.00"),
        )
        guest = APIClient()
        guest.post(
            reverse("v1:cart:lines"),
            {"product": str(product.pk), "quantity": 1},
            format="json",
            HTTP_X_CART_SESSION=KEY,
        )

        response = guest.post(
            reverse("v1:cart:coupon"), {"code": "SAVE20"}, format="json", HTTP_X_CART_SESSION=KEY
        )

        assert response.status_code == 200  # a refused coupon is still a 200
        assert response.data["coupon"]["is_valid"] is False
        assert response.data["coupon"]["reason"] == "COUPON_LOGIN_REQUIRED"
        assert response.data["totals"]["coupon_discount"] == "0.00"
        assert Cart.objects.get().coupon_code == ""

    def test_a_guest_learns_nothing_about_which_codes_exist(self, product):
        guest = APIClient()
        guest.post(
            reverse("v1:cart:lines"),
            {"product": str(product.pk), "quantity": 1},
            format="json",
            HTTP_X_CART_SESSION=KEY,
        )
        answers = {
            guest.post(
                reverse("v1:cart:coupon"),
                {"code": code},
                format="json",
                HTTP_X_CART_SESSION=KEY,
            ).data["coupon"]["reason"]
            for code in ("NOPE", "SAVE20", "WELCOME")
        }
        assert answers == {"COUPON_LOGIN_REQUIRED"}
