"""
Coupon SCOPE — one product, some products, or all products.

⚠️  The owner defines a coupon's scope as ONE product, SOME products or ALL of them. The
    discount is calculated on the eligible cart lines only, never on the whole cart:

        no products and no categories  =  ALL products
        otherwise                      =  the lines whose product is listed (or whose
                                          product's category is)

    This file pins the engine (`promotions.services.validate`, driven with hand-built
    priced lines so every number is known) and the admin API (writable `products` /
    `categories`, `scope_summary`, the `scope` filter). The same calculation prices the
    cart and the order — that end-to-end equality is pinned in
    `cart/tests/test_coupon_scope_cart.py` and `orders/tests/test_coupon_scope_orders.py`
    (a test lives in the highest domain it touches).
"""

from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from catalog.models import Category, Product
from pricing.services import PricedLine
from promotions import services
from promotions.models import Coupon
from promotions.services import RejectionReason as Reason
from promotions.tests.conftest import make_coupon, make_user

pytestmark = pytest.mark.django_db

D = Decimal


# ═══════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════


def priced(unit="100", qty=1, discount="0") -> PricedLine:
    """A priced line with no tax — `net` is `unit × qty − discount`."""
    return PricedLine(
        quantity=qty,
        unit_price=D(unit),
        list_price=D(unit),
        discount_amount=D(discount),
        tax_rate=D("0"),
        tax_amount=D("0"),
    )


def product(sku, category, price="100.00") -> Product:
    return Product.objects.create(
        sku=sku, name_ar=f"م {sku}", name_en=f"P {sku}", category=category, base_price=D(price)
    )


@pytest.fixture
def cat_a(db):
    return Category.objects.create(slug="scope-a", name_ar="أ", name_en="A")


@pytest.fixture
def cat_b(db):
    return Category.objects.create(slug="scope-b", name_ar="ب", name_en="B")


@pytest.fixture
def shop(cat_a, cat_b):
    """Three products: two in category A, one in B."""
    return {
        "a1": product("SC-A1", cat_a),
        "a2": product("SC-A2", cat_a),
        "b1": product("SC-B1", cat_b),
    }


def cart_of(shop, *keys, **lines):
    """`[(product, priced_line, ref)]` — the ref stands in for the cart line id."""
    result = []
    for key in keys:
        result.append((shop[key], priced(), key))
    for key, line in lines.items():
        result.append((shop[key], line, key))
    return result


def check(coupon, items, **kwargs):
    from accounts.models import User

    buyer = User.objects.filter(email="scope-buyer@test.local").first() or make_user(
        "scope-buyer@test.local"
    )
    return services.validate(coupon.code, buyer, items, **kwargs)


# ═══════════════════════════════════════════════════════════
#  The scope matrix
# ═══════════════════════════════════════════════════════════


class TestScopeMatrix:
    def test_no_scope_means_all_products(self, shop):
        coupon = make_coupon("ALLP", value=D("10"))

        result = check(coupon, cart_of(shop, "a1", "b1"))

        assert result.is_valid
        assert result.discount_amount == D("20.00")  # 10% of 200
        assert result.applies_to == "ALL"
        assert set(result.eligible_refs) == {"a1", "b1"}
        assert result.eligible_subtotal == D("200.00")

    def test_one_product_discounts_only_that_line(self, shop):
        coupon = make_coupon("ONE", value=D("10"))
        coupon.products.add(shop["a1"])

        result = check(coupon, cart_of(shop, "a1", "a2", "b1"))

        assert result.is_valid
        assert result.discount_amount == D("10.00")  # 10% of the 100 line, not of 300
        assert result.applies_to == "SOME"
        assert result.eligible_refs == ("a1",)
        assert result.eligible_subtotal == D("100.00")
        assert result.line_count == 3

    def test_several_products(self, shop):
        coupon = make_coupon("SOME", value=D("10"))
        coupon.products.add(shop["a1"], shop["b1"])

        result = check(coupon, cart_of(shop, "a1", "a2", "b1"))

        assert result.discount_amount == D("20.00")
        assert set(result.eligible_refs) == {"a1", "b1"}
        assert result.applies_to == "SOME"

    def test_a_category_scope_covers_every_product_in_it(self, shop, cat_a):
        coupon = make_coupon("CATA", value=D("10"))
        coupon.categories.add(cat_a)

        result = check(coupon, cart_of(shop, "a1", "a2", "b1"))

        assert result.discount_amount == D("20.00")
        assert set(result.eligible_refs) == {"a1", "a2"}

    def test_products_and_categories_add_up(self, shop, cat_a):
        coupon = make_coupon("MIXED", value=D("10"))
        coupon.categories.add(cat_a)
        coupon.products.add(shop["b1"])

        result = check(coupon, cart_of(shop, "a1", "a2", "b1"))

        assert result.applies_to == "ALL"  # every line is covered
        assert result.discount_amount == D("30.00")

    def test_every_line_eligible_reads_as_all(self, shop):
        coupon = make_coupon("ALLLINES", value=D("10"))
        coupon.products.add(shop["a1"], shop["a2"])

        result = check(coupon, cart_of(shop, "a1", "a2"))

        assert result.applies_to == "ALL"

    def test_no_eligible_line_is_refused_with_a_clear_bilingual_reason(self, shop):
        coupon = make_coupon("NONE", value=D("10"))
        coupon.products.add(shop["a1"])

        result = check(coupon, cart_of(shop, "b1", "a2"))

        assert not result.is_valid
        assert result.reason is Reason.NO_ELIGIBLE_ITEMS
        assert result.reason.value == "COUPON_NO_ELIGIBLE_ITEMS"
        assert result.message == "هذا الكوبون لا ينطبق على الأصناف في سلتك"
        assert result.message_en == "This coupon doesn't apply to the items in your cart"
        assert result.discount_amount == 0

    def test_a_scoped_coupon_on_an_empty_cart_is_refused(self, shop):
        coupon = make_coupon("EMPTY", value=D("10"))
        coupon.products.add(shop["a1"])

        assert check(coupon, []).reason is Reason.NO_ELIGIBLE_ITEMS

    def test_a_colour_line_follows_its_product(self, shop):
        """
        ⚠️  The scope is the product. Two lines of one product (two colours, two
            quantities) are both eligible — the variant is not part of the scope.
        """
        coupon = make_coupon("COLOURS", value=D("10"))
        coupon.products.add(shop["a1"])
        items = [
            (shop["a1"], priced("100", 2), "blue-line"),
            (shop["a1"], priced("120", 1), "red-line"),
            (shop["b1"], priced("100", 1), "other"),
        ]

        result = check(coupon, items)

        assert set(result.eligible_refs) == {"blue-line", "red-line"}
        assert result.eligible_subtotal == D("320.00")
        assert result.discount_amount == D("32.00")

    def test_a_deleted_product_does_not_widen_the_scope_to_everything(self, shop):
        """
        ⚠️  A coupon made for ONE product whose product is later deleted must not read as
            "no scope" — that would silently turn a single-product code store-wide.
        """
        coupon = make_coupon("GONE", value=D("10"))
        coupon.products.add(shop["a1"])
        shop["a1"].delete()  # soft delete

        result = check(coupon, cart_of(shop, "a2", "b1"))

        assert result.reason is Reason.NO_ELIGIBLE_ITEMS


# ═══════════════════════════════════════════════════════════
#  The money
# ═══════════════════════════════════════════════════════════


class TestAmounts:
    def test_the_percentage_is_taken_after_line_discounts(self, shop):
        coupon = make_coupon("NETBASE", value=D("10"))
        coupon.products.add(shop["a1"])
        items = [(shop["a1"], priced("100", 2, discount="40"), "a1"), (shop["b1"], priced(), "b1")]

        result = check(coupon, items)

        assert result.eligible_subtotal == D("160.00")  # 200 − the 40 item-level discount
        assert result.discount_amount == D("16.00")

    def test_the_percentage_cap_applies_to_the_eligible_amount(self, shop):
        coupon = make_coupon("CAPPED", value=D("50"), max_discount_amount=D("30.00"))
        coupon.products.add(shop["a1"])
        items = [(shop["a1"], priced("100", 5), "a1"), (shop["b1"], priced("1000"), "b1")]

        result = check(coupon, items)

        assert result.discount_amount == D("30.00")  # 50% of 500 would be 250

    def test_a_fixed_amount_is_capped_at_the_eligible_subtotal(self, shop):
        coupon = make_coupon("FIX", kind="FIXED", value=D("150"))
        coupon.products.add(shop["a1"])
        items = [(shop["a1"], priced("100"), "a1"), (shop["b1"], priced("900"), "b1")]

        result = check(coupon, items)

        # 150 off, but only 100 is eligible — not 150 taken from the 900 beside it
        assert result.discount_amount == D("100.00")

    def test_a_fixed_amount_below_the_eligible_subtotal_is_given_whole(self, shop):
        coupon = make_coupon("FIX2", kind="FIXED", value=D("25"))
        coupon.products.add(shop["a1"])

        assert check(coupon, cart_of(shop, "a1", "b1")).discount_amount == D("25.00")

    def test_the_minimum_order_is_judged_on_the_eligible_subtotal(self, shop):
        """
        ⚠️  Decision: for a SCOPED coupon "minimum order 500" means 500 of the *covered*
            items. Counting the rest of the cart would let a 20 EGP covered item qualify
            because of an unrelated 480 EGP one.
        """
        coupon = make_coupon("MINSCOPE", value=D("10"), min_order_amount=D("500.00"))
        coupon.products.add(shop["a1"])
        items = [(shop["a1"], priced("100"), "a1"), (shop["b1"], priced("900"), "b1")]

        result = check(coupon, items)

        assert not result.is_valid
        assert result.reason is Reason.MINIMUM_NOT_MET

    def test_the_minimum_is_met_when_the_eligible_items_reach_it(self, shop):
        coupon = make_coupon("MINOK", value=D("10"), min_order_amount=D("500.00"))
        coupon.products.add(shop["a1"])
        items = [(shop["a1"], priced("100", 5), "a1"), (shop["b1"], priced("10"), "b1")]

        result = check(coupon, items)

        assert result.is_valid
        assert result.discount_amount == D("50.00")

    def test_without_a_scope_the_minimum_is_the_whole_cart(self, shop):
        coupon = make_coupon("MINALL", value=D("10"), min_order_amount=D("500.00"))
        items = [(shop["a1"], priced("100"), "a1"), (shop["b1"], priced("900"), "b1")]

        assert check(coupon, items).is_valid

    def test_free_shipping_ignores_the_product_scope(self, shop):
        """FREE_SHIPPING is not about products: it applies even with no covered line."""
        coupon = make_coupon("SHIPFREE", kind="FREE_SHIPPING", value=D("0"))
        coupon.products.add(shop["a1"])

        result = check(coupon, cart_of(shop, "b1"))

        assert result.is_valid
        assert result.free_shipping is True
        assert result.discount_amount == 0
        assert result.applies_to == "ALL"

    def test_free_shipping_minimum_is_the_whole_cart(self, shop):
        coupon = make_coupon(
            "SHIPMIN", kind="FREE_SHIPPING", value=D("0"), min_order_amount=D("150.00")
        )
        coupon.products.add(shop["a1"])

        assert check(coupon, cart_of(shop, "a1", "b1")).is_valid  # 200 >= 150, scope ignored
        assert not check(coupon, cart_of(shop, "b1")).is_valid


# ═══════════════════════════════════════════════════════════
#  The admin API
# ═══════════════════════════════════════════════════════════


def draft(**overrides) -> dict:
    body = {
        "code": "SCOPED10",
        "name_ar": "حملة",
        "name_en": "Campaign",
        "kind": "PERCENTAGE",
        "value": "10.00",
    }
    body.update(overrides)
    return body


class TestAdminScopeFields:
    def test_products_and_categories_are_writable_id_lists(self, admin_client, shop, cat_b):
        response = admin_client.post(
            reverse("v1:promotions:coupons"),
            draft(products=[str(shop["a1"].pk)], categories=[str(cat_b.pk)]),
            format="json",
        )

        assert response.status_code == 201, response.data
        coupon = Coupon.objects.get(code="SCOPED10")
        assert list(coupon.products.all()) == [shop["a1"]]
        assert list(coupon.categories.all()) == [cat_b]
        assert response.data["products"] == [shop["a1"].pk]

    def test_an_update_replaces_and_clears_the_scope(self, admin_client, shop):
        coupon = make_coupon("EDITME")
        coupon.products.add(shop["a1"], shop["a2"])
        url = reverse("v1:promotions:coupon-detail", args=[coupon.pk])

        response = admin_client.patch(url, {"products": [str(shop["b1"].pk)]}, format="json")
        assert response.status_code == 200
        assert list(coupon.products.all()) == [shop["b1"]]
        # ⚠️  The response describes the scope AFTER the save, not the prefetched one
        assert response.data["scope_summary"]["product_count"] == 1
        assert response.data["scope_summary"]["products"][0]["sku"] == "SC-B1"

        response = admin_client.patch(url, {"products": []}, format="json")
        assert response.status_code == 200
        assert coupon.products.count() == 0
        assert response.data["scope_summary"]["type"] == "ALL"

    def test_an_unknown_product_is_refused(self, admin_client):
        response = admin_client.post(
            reverse("v1:promotions:coupons"),
            draft(products=["00000000-0000-0000-0000-000000000000"]),
            format="json",
        )

        assert response.status_code == 400
        assert "products" in response.data["fields"]
        assert not Coupon.objects.filter(code="SCOPED10").exists()

    def test_a_deleted_product_is_refused(self, admin_client, shop):
        shop["a1"].delete()

        response = admin_client.post(
            reverse("v1:promotions:coupons"), draft(products=[str(shop["a1"].pk)]), format="json"
        )

        assert response.status_code == 400
        assert "products" in response.data["fields"]

    def test_an_unknown_category_is_refused(self, admin_client):
        response = admin_client.post(
            reverse("v1:promotions:coupons"),
            draft(categories=["00000000-0000-0000-0000-000000000000"]),
            format="json",
        )

        assert response.status_code == 400
        assert "categories" in response.data["fields"]

    def test_a_new_coupon_is_open_to_guests_by_default(self, admin_client):
        response = admin_client.post(reverse("v1:promotions:coupons"), draft(), format="json")

        assert response.status_code == 201
        assert response.data["allow_guests"] is True

    def test_allow_guests_can_be_turned_off(self, admin_client):
        response = admin_client.post(
            reverse("v1:promotions:coupons"), draft(allow_guests=False), format="json"
        )

        assert response.status_code == 201
        assert Coupon.objects.get(code="SCOPED10").allow_guests is False


class TestScopeSummary:
    def summary(self, admin_client, coupon):
        response = admin_client.get(reverse("v1:promotions:coupon-detail", args=[coupon.pk]))
        assert response.status_code == 200
        return response.data["scope_summary"]

    def test_all(self, admin_client):
        summary = self.summary(admin_client, make_coupon("S-ALL"))

        assert summary["type"] == "ALL"
        assert summary["product_count"] == 0
        assert summary["category_count"] == 0
        assert summary["products"] == []
        assert summary["more"] == 0

    def test_products(self, admin_client, shop):
        coupon = make_coupon("S-PROD")
        coupon.products.add(shop["a1"], shop["a2"])

        summary = self.summary(admin_client, coupon)

        assert summary["type"] == "PRODUCTS"
        assert summary["product_count"] == 2
        assert [row["sku"] for row in summary["products"]] == ["SC-A1", "SC-A2"]
        assert set(summary["products"][0]) >= {"id", "sku", "name_ar", "name_en"}

    def test_categories(self, admin_client, cat_a):
        coupon = make_coupon("S-CAT")
        coupon.categories.add(cat_a)

        summary = self.summary(admin_client, coupon)

        assert summary["type"] == "CATEGORIES"
        assert summary["category_count"] == 1
        assert summary["categories"][0]["name_en"] == "A"

    def test_mixed(self, admin_client, shop, cat_b):
        coupon = make_coupon("S-MIX")
        coupon.products.add(shop["a1"])
        coupon.categories.add(cat_b)

        assert self.summary(admin_client, coupon)["type"] == "MIXED"

    def test_only_the_first_ten_products_are_named(self, admin_client, cat_a):
        coupon = make_coupon("S-MANY")
        coupon.products.add(*[product(f"MANY-{i:02d}", cat_a) for i in range(13)])

        summary = self.summary(admin_client, coupon)

        assert summary["product_count"] == 13
        assert len(summary["products"]) == 10
        assert summary["more"] == 3

    def test_a_coupon_whose_only_product_was_deleted_is_still_scoped(self, admin_client, shop):
        coupon = make_coupon("S-GONE")
        coupon.products.add(shop["a1"])
        shop["a1"].delete()

        summary = self.summary(admin_client, coupon)

        assert summary["type"] == "PRODUCTS"  # never "ALL"
        assert summary["products"][0]["is_deleted"] is True
        # …and the writable id list does not carry the deleted product back
        detail = admin_client.get(reverse("v1:promotions:coupon-detail", args=[coupon.pk]))
        assert detail.data["products"] == []

    def test_the_list_costs_the_same_number_of_queries_for_one_coupon_or_many(
        self, admin_client, shop, cat_a
    ):
        """⚠️  No N+1: the summaries of a whole page are prefetched."""
        url = reverse("v1:promotions:coupons")
        first = make_coupon("Q-1")
        first.products.add(shop["a1"])
        admin_client.get(url)  # warm-up: the first request pays one-off cache queries

        with CaptureQueriesContext(connection) as one:
            assert admin_client.get(url).status_code == 200

        for index in range(2, 8):
            extra = make_coupon(f"Q-{index}")
            extra.products.add(shop["a2"], shop["b1"])
            extra.categories.add(cat_a)

        with CaptureQueriesContext(connection) as many:
            response = admin_client.get(url)
        assert response.status_code == 200
        assert len(response.data["results"]) == 7

        assert len(many) == len(one)


class TestScopeFilter:
    def codes(self, admin_client, **params):
        response = admin_client.get(reverse("v1:promotions:coupons"), params)
        assert response.status_code == 200
        return {row["code"] for row in response.data["results"]}

    def test_all_and_products(self, admin_client, shop, cat_a):
        make_coupon("F-ALL")
        by_product = make_coupon("F-PROD")
        by_product.products.add(shop["a1"], shop["a2"])  # two rows must not duplicate it
        by_category = make_coupon("F-CAT")
        by_category.categories.add(cat_a)

        assert self.codes(admin_client, scope="all") == {"F-ALL"}
        assert self.codes(admin_client, scope="products") == {"F-PROD"}
        assert self.codes(admin_client, scope="categories") == {"F-CAT"}
        assert self.codes(admin_client, scope="scoped") == {"F-PROD", "F-CAT"}
        assert self.codes(admin_client) == {"F-ALL", "F-PROD", "F-CAT"}

    def test_the_guest_filter(self, admin_client):
        make_coupon("G-OPEN")
        make_coupon("G-CLOSED", allow_guests=False)

        assert self.codes(admin_client, guests="allowed") == {"G-OPEN"}
        assert self.codes(admin_client, guests="blocked") == {"G-CLOSED"}
