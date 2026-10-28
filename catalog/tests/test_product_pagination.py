"""
The storefront product list — numbered pages.

⚠️  Three things are pinned here, each one a way a pager quietly lies:

      1. the page order is **total**: a page boundary falling inside a run of equal
         prices must not repeat a product or drop one;
      2. `pages` counts what the shopper can see — the stock and policy filters are in the
         queryset, so a page is never short and the pager never offers an empty last page;
      3. a page past the end is a `404`, which the storefront turns into "back to page 1".
"""

from decimal import Decimal

import pytest
from django.apps import apps
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from access.models import AccessPolicy
from catalog.models import Category, Product

pytestmark = pytest.mark.django_db

URL = "v1:catalog:products"


@pytest.fixture
def category(db):
    return Category.objects.create(name_ar="مستلزمات", name_en="Supplies")


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


def make_products(count, category, policy, location, *, price="50.00", in_stock=True, prefix="PG"):
    """
    `count` published products that **tie on price and on name** — the awkward case for paging.

    A product with no stock row is not in the public catalogue, so `in_stock=False` simply
    skips the row.
    """
    made = []
    for i in range(count):
        product = Product.objects.create(
            sku=f"{prefix}-{i:03d}",
            name_ar="منتج متطابق",
            name_en=f"Same name {prefix} {i}",
            category=category,
            base_price=Decimal(price),
            access_policy=policy,
        )
        if in_stock:
            apps.get_model("inventory", "Stock").objects.create(
                product=product, location=location, quantity_physical=5
            )
        made.append(product)
    return made


def get(params=None):
    return APIClient().get(reverse(URL), params or {})


def walk(params):
    """Every page of a listing, followed through `pages` — the product ids in the order served."""
    first = get({**params, "page": 1})
    assert first.status_code == 200
    ids = [row["id"] for row in first.data["results"]]
    for number in range(2, first.data["pages"] + 1):
        page = get({**params, "page": number})
        assert page.status_code == 200
        ids.extend(row["id"] for row in page.data["results"])
    return ids


# ═══════════════════════════════════════════════════════════
#  The shape
# ═══════════════════════════════════════════════════════════


class TestShape:
    def test_a_page_carries_its_number_and_the_page_count_but_no_total(
        self, category, policies, location
    ):
        """⚠️  `pages` is exposed, `count` never is — ADR-32 softened, not removed."""
        make_products(30, category, policies["public"], location)

        data = get().data

        assert list(data) == ["results", "page", "pages", "next", "previous"]
        assert "count" not in data
        assert data["page"] == 1
        assert data["pages"] == 2

    def test_the_first_page_holds_twenty_four_and_links_forward_only(
        self, category, policies, location
    ):
        make_products(30, category, policies["public"], location)

        data = get().data

        assert len(data["results"]) == 24
        assert data["previous"] is None
        assert "page=2" in data["next"]

    def test_the_second_page_holds_the_rest_and_links_back_only(
        self, category, policies, location
    ):
        make_products(30, category, policies["public"], location)

        data = get({"page": 2}).data

        assert data["page"] == 2
        assert len(data["results"]) == 6
        assert data["next"] is None
        assert data["previous"] is not None

    def test_a_single_page_still_says_so(self, category, policies, location):
        make_products(3, category, policies["public"], location)

        data = get().data

        assert (data["page"], data["pages"]) == (1, 1)
        assert data["next"] is None and data["previous"] is None

    def test_the_card_limit_sets_the_page_size(self, category, policies, location):
        """The home page asks for eight."""
        make_products(30, category, policies["public"], location)

        data = get({"limit": 8}).data

        assert len(data["results"]) == 8
        assert data["pages"] == 4

    def test_an_oversized_limit_is_clamped_not_refused(self, category, policies, location):
        make_products(3, category, policies["public"], location)

        response = get({"limit": 100000})

        assert response.status_code == 200
        assert len(response.data["results"]) == 3

    def test_an_empty_catalogue_is_one_empty_page_not_an_error(self, policies, location):
        response = get()

        assert response.status_code == 200
        assert response.data["results"] == []
        assert response.data["page"] == 1

    def test_the_query_count_does_not_grow_with_the_page(
        self, category, policies, location
    ):
        make_products(8, category, policies["public"], location)
        get({"limit": 8})  # a throw-away call first: the first request warms process-level caches
        with CaptureQueriesContext(connection) as small:
            get({"limit": 8})

        make_products(30, category, policies["public"], location, prefix="MORE")
        with CaptureQueriesContext(connection) as large:
            get({"limit": 24})

        assert len(large) == len(small)


# ═══════════════════════════════════════════════════════════
#  A page that does not exist
# ═══════════════════════════════════════════════════════════


class TestOutOfRange:
    @pytest.mark.parametrize("page", ["3", "0", "-1", "abc"])
    def test_a_page_past_the_end_is_not_found(self, category, policies, location, page):
        make_products(30, category, policies["public"], location)

        assert get({"page": page}).status_code == 404

    def test_the_last_page_vanishing_between_two_clicks_is_a_404_not_a_500(
        self, category, policies, location
    ):
        """
        ⚠️  The shopper is on page 2 of 2; the one item on it sells out. The pager they
            are looking at still offers page 2 — the answer must be a clean `404` the
            client can recover from, and page 1 must still work.
        """
        make_products(25, category, policies["public"], location)
        only = get({"page": 2}).data["results"]
        assert len(only) == 1

        apps.get_model("inventory", "Stock").objects.filter(product_id=only[0]["id"]).update(
            quantity_physical=0
        )

        assert get({"page": 2}).status_code == 404
        assert get({"page": 1}).status_code == 200


# ═══════════════════════════════════════════════════════════
#  The order is total
# ═══════════════════════════════════════════════════════════

ORDERINGS = [
    "created_at",
    "-created_at",
    "base_price",
    "-base_price",
    "name_ar",
    "-name_ar",
    "rating__average",
    "-rating__average",
]


class TestStableOrdering:
    @pytest.mark.parametrize("ordering", ORDERINGS)
    def test_paging_through_a_run_of_ties_serves_every_product_exactly_once(
        self, category, policies, location, ordering
    ):
        """
        ⚠️  Thirty products with one price, one name and one `created_at` — every
            sort key ties, so only the tie-breaker decides. With a page size of 7 the
            page boundaries all fall inside the tie.
        """
        made = make_products(30, category, policies["public"], location)
        Product.objects.update(created_at=made[0].created_at)

        served = walk({"ordering": ordering, "limit": 7})

        assert len(served) == 30
        assert set(served) == {str(p.pk) for p in made}

    def test_equal_prices_fall_back_to_id_in_the_direction_of_the_sort(
        self, category, policies, location
    ):
        made = make_products(30, category, policies["public"], location)
        ids = sorted(str(p.pk) for p in made)

        assert walk({"ordering": "base_price", "limit": 7}) == ids
        assert walk({"ordering": "-base_price", "limit": 7}) == ids[::-1]

    def test_the_price_still_comes_before_the_tie_breaker(self, category, policies, location):
        cheap = make_products(10, category, policies["public"], location, price="10.00", prefix="C")
        dear = make_products(10, category, policies["public"], location, price="90.00", prefix="D")

        ascending = walk({"ordering": "base_price", "limit": 6})

        assert set(ascending[:10]) == {str(p.pk) for p in cheap}
        assert set(ascending[10:]) == {str(p.pk) for p in dear}

    def test_the_same_request_twice_serves_the_same_page(self, category, policies, location):
        make_products(30, category, policies["public"], location)

        first = [r["id"] for r in get({"ordering": "base_price", "page": 2, "limit": 7}).data["results"]]
        again = [r["id"] for r in get({"ordering": "base_price", "page": 2, "limit": 7}).data["results"]]

        assert first == again

    def test_an_unknown_ordering_falls_back_to_newest_first(self, category, policies, location):
        """The allow-list is a security boundary — an arbitrary field name must not reach `order_by`."""
        make_products(5, category, policies["public"], location)

        response = get({"ordering": "access_policy__name"})

        assert response.status_code == 200
        assert [r["id"] for r in response.data["results"]] == [
            r["id"] for r in get({"ordering": "-created_at"}).data["results"]
        ]


# ═══════════════════════════════════════════════════════════
#  The filters compose with the paginator
# ═══════════════════════════════════════════════════════════


class TestFiltersComposeWithPages:
    def test_pages_count_only_what_is_in_stock(self, category, policies, location):
        """
        ⚠️  Thirty-five products exist and twelve have no stock: the shopper sees twenty-three,
            which is **one** page — a pager counting the catalogue would offer a second page
            that is empty.
        """
        make_products(23, category, policies["public"], location)
        make_products(12, category, policies["public"], location, in_stock=False, prefix="OUT")

        data = get().data

        assert data["pages"] == 1
        assert len(data["results"]) == 23

    def test_the_page_size_is_full_when_hidden_rows_sit_in_the_middle(
        self, category, policies, location
    ):
        """No page is short because a row was hidden after it was read."""
        make_products(10, category, policies["public"], location, prefix="A")
        make_products(10, category, policies["public"], location, in_stock=False, prefix="OUT")
        make_products(10, category, policies["public"], location, prefix="B")

        sizes = []
        for number in (1, 2):
            sizes.append(len(get({"limit": 15, "page": number}).data["results"]))

        assert sizes == [15, 5]

    def test_restocking_restores_the_page(self, category, policies, location):
        make_products(24, category, policies["public"], location)
        gone = make_products(1, category, policies["public"], location, in_stock=False, prefix="X")
        assert get().data["pages"] == 1

        apps.get_model("inventory", "Stock").objects.create(
            product=gone[0], location=location, quantity_physical=3
        )

        assert get().data["pages"] == 2

    def test_a_restricted_product_is_in_no_page_and_in_no_page_count(
        self, category, policies, location
    ):
        make_products(24, category, policies["public"], location)
        make_products(5, category, policies["pharmacy_only"], location, prefix="RES")

        data = get().data

        assert data["pages"] == 1
        assert not any(row["sku"].startswith("RES") for row in data["results"])

    def test_search_and_category_filters_page_the_filtered_set(self, category, policies, location):
        other = Category.objects.create(name_ar="أدوات", name_en="Tools")
        make_products(10, category, policies["public"], location, prefix="IN")
        make_products(30, other, policies["public"], location, prefix="TOOL")

        data = get({"category": other.slug, "limit": 12}).data

        assert data["pages"] == 3
        assert all(row["sku"].startswith("TOOL") for row in data["results"])

        searched = get({"search": "name IN ", "limit": 4}).data
        assert searched["pages"] == 3  # ten matches, four to a page
