"""
Cart tests.

⚠️  The critical group is **re-validation**: a cart lives for days, and
    everything the add decision was based on may change before checkout.
"""

from decimal import Decimal

import pytest
from django.apps import apps

from access.models import AccessPolicy
from accounts.models import AccountType, User
from cart import services
from cart.models import Cart, CartLine, CartStatus
from catalog.models import Category, Product
from core.errors import BusinessError
from inventory import services as inventory_services
from promotions.models import Coupon, CouponKind

PASSWORD = "Str0ng-Test-Pass!23"


def location_model():
    return apps.get_model("inventory", "StockLocation")


def make_user(email, account_type=AccountType.STUDENT):
    user = User.objects.create_user(email=email, password=PASSWORD, account_type=account_type)
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def location(db):
    return location_model().objects.create(
        code="main", name_ar="الرئيسي", name_en="Main", is_default=True
    )


@pytest.fixture
def policies(db):
    from django.core.management import call_command

    call_command("seed_access_policies", verbosity=0)
    return {p.code: p for p in AccessPolicy.objects.all()}


@pytest.fixture
def user(db):
    return make_user("buyer@test.local")


@pytest.fixture
def product(db, location, policies):
    category = Category.objects.create(name_ar="فئة", name_en="Category")
    product = Product.objects.create(
        sku="P-001",
        name_ar="منتج",
        name_en="Product",
        category=category,
        base_price=Decimal("100.00"),
        access_policy=policies["public"],
    )
    inventory_services.receive(product, 20, Decimal("60.00"), location=location)
    return product


@pytest.fixture
def cart(user):
    return services.get_active_cart(user=user)


# ═══════════════════════════════════════════════════════════
#  Fundamentals
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCartBasics:
    def test_one_active_cart_per_user(self, user):
        first = services.get_active_cart(user=user)
        second = services.get_active_cart(user=user)
        assert first.pk == second.pk

    def test_adding_same_product_accumulates(self, cart, product, user):
        services.add_line(cart, product, 2, user=user)
        services.add_line(cart, product, 3, user=user)

        assert cart.lines.count() == 1
        assert cart.lines.first().quantity == 5

    def test_setting_quantity_to_zero_removes_the_line(self, cart, product, user):
        line = services.add_line(cart, product, 2, user=user)
        services.set_quantity(cart, line, 0)

        assert cart.lines.count() == 0

    def test_cart_stores_no_prices(self):
        """
        ⚠️  The price is computed on every display.

        Storing it means a cart showing yesterday's price after today's change —
        and the customer sees one number and is charged another.
        """
        names = {f.name for f in CartLine._meta.get_fields()}

        assert "price" not in names
        assert "unit_price" not in names
        assert "total" not in names
        assert "tax_amount" not in names


# ═══════════════════════════════════════════════════════════
#  Ownership
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestOwnership:
    def test_cannot_modify_another_users_line(self, cart, product, user):
        other = make_user("other@test.local")
        other_cart = services.get_active_cart(user=other)
        other_line = services.add_line(other_cart, product, 1, user=other)

        with pytest.raises(BusinessError) as exc:
            services.set_quantity(cart, other_line, 5)
        assert exc.value.status_code == 404

    def test_cannot_remove_another_users_line(self, cart, product, user):
        other = make_user("other2@test.local")
        other_cart = services.get_active_cart(user=other)
        other_line = services.add_line(other_cart, product, 1, user=other)

        with pytest.raises(BusinessError):
            services.remove_line(cart, other_line)

        assert CartLine.objects.filter(pk=other_line.pk).exists()


# ═══════════════════════════════════════════════════════════
#  Stock
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestStockChecks:
    def test_cannot_add_beyond_available(self, cart, product, user):
        with pytest.raises(BusinessError) as exc:
            services.add_line(cart, product, 25, user=user)
        assert exc.value.code == "INSUFFICIENT_STOCK"

    def test_accumulation_is_checked_against_the_total(self, cart, product, user):
        """
        ⚠️  The check is on the total quantity after the addition, not on the added amount alone.

        Without it, stock can be exceeded through a series of small additions.
        """
        services.add_line(cart, product, 15, user=user)

        with pytest.raises(BusinessError):
            services.add_line(cart, product, 10, user=user)


# ═══════════════════════════════════════════════════════════
#  Re-validation — the heart of this domain
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRevalidation:
    def test_line_carries_the_product_thumbnail(self, cart, product, user):
        """
        ⚠️  `primary_images` is a `Prefetch(to_attr=...)` — it **does not exist**
            on the product unless the queryset asked for it, and the serializer's
            `getattr(..., None)` then reads as "this product has no image".

            The failure is silent: no error, every cart line just falls back to
            the placeholder glyph. This test is the only thing that catches it.
        """
        from django.core.files.base import ContentFile

        from cart.serializers import CartSnapshotSerializer
        from catalog.models import ProductImage

        image = ProductImage(product=product, is_primary=True)
        image.image.save("primary.jpg", ContentFile(b"not-really-a-jpeg"), save=True)

        services.add_line(cart, product, 1, user=user)
        snapshot = services.revalidate(cart)

        assert getattr(snapshot.lines[0][0][0], "primary_images", None), (
            "revalidate() must prefetch the primary image onto the product"
        )

        line = CartSnapshotSerializer(snapshot).data["lines"][0]
        assert line["image"] == image.image.url

    def test_clean_cart_is_checkoutable(self, cart, product, user):
        services.add_line(cart, product, 2, user=user)
        snapshot = services.revalidate(cart)

        assert snapshot.is_checkoutable
        assert not snapshot.has_issues
        assert snapshot.priced.subtotal == Decimal("200.00")

    def test_deactivated_product_raises_an_issue(self, cart, product, user):
        services.add_line(cart, product, 1, user=user)

        product.is_active = False
        product.save()

        snapshot = services.revalidate(cart)
        assert not snapshot.is_checkoutable
        assert snapshot.issues[0].code == "PRODUCT_UNAVAILABLE"

    def test_lost_access_raises_an_issue(self, cart, product, user, policies):
        """
        ⚠️  A customer may lose eligibility after adding — an expired licence, say.
        """
        services.add_line(cart, product, 1, user=user)

        product.access_policy = policies["pharmacy_only"]
        product.save()

        snapshot = services.revalidate(cart)
        assert snapshot.issues[0].code == "PRODUCT_ACCESS_DENIED"

    def test_stock_drop_raises_an_issue_with_the_available_amount(
        self, cart, product, user, location
    ):
        services.add_line(cart, product, 10, user=user)
        inventory_services.sell_immediately(product, 15, location=location)

        snapshot = services.revalidate(cart)
        issue = snapshot.issues[0]

        assert issue.code == "INSUFFICIENT_STOCK"
        assert issue.available == 5

    def test_price_change_is_reflected_immediately(self, cart, product, user):
        services.add_line(cart, product, 1, user=user)
        assert services.revalidate(cart).priced.subtotal == Decimal("100.00")

        product.base_price = Decimal("150.00")
        product.save()

        assert services.revalidate(cart).priced.subtotal == Decimal("150.00")


# ═══════════════════════════════════════════════════════════
#  Coupons
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCoupons:
    @pytest.fixture
    def coupon(self, db):
        return Coupon.objects.create(
            code="SAVE20",
            name_ar="خصم",
            name_en="Discount",
            kind=CouponKind.PERCENTAGE,
            value=Decimal("20.00"),
        )

    def test_valid_coupon_applies(self, cart, product, user, coupon):
        services.add_line(cart, product, 2, user=user)
        snapshot = services.apply_coupon(cart, "SAVE20")

        assert snapshot.coupon_result.is_valid
        assert snapshot.coupon_result.discount_amount == Decimal("40.00")

        cart.refresh_from_db()
        assert cart.coupon_code == "SAVE20"

    def test_cart_stores_the_code_not_the_amount(self, cart, product, user, coupon):
        """
        ⚠️  Storing the value means a discount computed against a cart that changed afterwards.
        """
        names = {f.name for f in Cart._meta.get_fields()}

        assert "coupon_code" in names
        assert "coupon_discount" not in names
        assert "discount_amount" not in names

    def test_discount_follows_cart_changes(self, cart, product, user, coupon):
        services.add_line(cart, product, 1, user=user)
        services.apply_coupon(cart, "SAVE20")
        assert services.revalidate(cart).priced.coupon_discount == Decimal("20.00")

        services.add_line(cart, product, 1, user=user)
        assert services.revalidate(cart).priced.coupon_discount == Decimal("40.00")

    def test_minimum_order_is_enforced(self, cart, product, user):
        Coupon.objects.create(
            code="BIG50",
            name_ar="كبير",
            name_en="Big",
            kind=CouponKind.FIXED,
            value=Decimal("50.00"),
            min_order_amount=Decimal("500.00"),
        )
        services.add_line(cart, product, 1, user=user)

        snapshot = services.apply_coupon(cart, "BIG50")
        assert not snapshot.coupon_result.is_valid
        assert snapshot.coupon_result.reason.value == "MINIMUM_ORDER_NOT_MET"

    def test_percentage_cap_is_respected(self, cart, product, user):
        Coupon.objects.create(
            code="CAP",
            name_ar="بسقف",
            name_en="Capped",
            kind=CouponKind.PERCENTAGE,
            value=Decimal("50.00"),
            max_discount_amount=Decimal("30.00"),
        )
        services.add_line(cart, product, 5, user=user)  # 500

        snapshot = services.apply_coupon(cart, "CAP")
        assert snapshot.coupon_result.discount_amount == Decimal("30.00")  # not 250

    def test_unknown_code_is_rejected_without_raising(self, cart, product, user):
        """The customer is trying codes — rejection is an expected state, not an error."""
        services.add_line(cart, product, 1, user=user)
        snapshot = services.apply_coupon(cart, "NOPE")

        assert not snapshot.coupon_result.is_valid
        assert snapshot.coupon_result.reason.value == "COUPON_NOT_FOUND"


# ═══════════════════════════════════════════════════════════
#  Merging the guest cart
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestGuestMerge:
    def test_guest_cart_is_created_by_session(self, product):
        cart = services.get_active_cart(session_key="guest-session-1")
        assert cart.user is None
        assert cart.session_key == "guest-session-1"

    def test_merge_sums_quantities(self, user, product):
        """
        ⚠️  Quantities are added, not replaced.

        Someone who added two items as a guest and then logged in to find one in
        their saved cart expects three. Replacing loses what they just chose.
        """
        guest_cart = services.get_active_cart(session_key="guest-1")
        services.add_line(guest_cart, product, 2)

        user_cart = services.get_active_cart(user=user)
        services.add_line(user_cart, product, 1, user=user)

        merged = services.merge_guest_cart(user, "guest-1")

        assert merged.pk == user_cart.pk
        assert merged.lines.first().quantity == 3

        guest_cart.refresh_from_db()
        assert guest_cart.status == CartStatus.MERGED

    def test_merge_without_a_guest_cart_is_safe(self, user, product):
        user_cart = services.get_active_cart(user=user)
        services.add_line(user_cart, product, 1, user=user)

        merged = services.merge_guest_cart(user, "nonexistent")
        assert merged.pk == user_cart.pk
        assert merged.lines.count() == 1
