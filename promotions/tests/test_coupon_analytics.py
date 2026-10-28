"""
Coupon analytics — "how many were used, what was sold through them, who holds them".

⚠️  The exit gate for the analytics: every figure on a hand-built shop matches the
    number worked out by hand in `conftest.scenario`, and the three things an owner
    could be misled by are pinned:

        · cancelled / refunded / payment-failed orders are NOT sales (but are reported)
        · the per-product discounts add back to the order's discount to the piastre
        · a list of any size costs the same number of queries
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from promotions import analytics
from promotions.models import Coupon, CouponRedemption
from promotions.tests.conftest import make_coupon, make_order, make_user

pytestmark = pytest.mark.django_db

D = Decimal


def url(name, *args):
    return reverse(f"v1:promotions:{name}", args=args)


def detail(client, coupon, **params):
    response = client.get(url("coupon-analytics", coupon.pk), params)
    assert response.status_code == 200, response.data
    return response.data


# ═══════════════════════════════════════════════════════════
#  The definition of a sale
# ═══════════════════════════════════════════════════════════


class TestSummary:
    def test_only_real_sales_are_counted(self, admin_client, scenario):
        """
        ⚠️  O3 cancelled · O4 refunded · O5 payment failed are not sales; O1, O2, O6 are.

            gross    = subtotal − line discounts   250 + 90 + 200   = 540.00
            discount = Σ coupon discount            25 + 9 + 20      =  54.00
            net      = gross − discount                              = 486.00
            total    = Σ grand total (incl. shipping) 245 + 81 + 180 = 506.00
        """
        coupon, _orders = scenario
        summary = detail(admin_client, coupon)["summary"]

        assert summary["orders"] == 3
        assert summary["customers"] == 3
        assert summary["gross_sales"] == "540.00"
        assert summary["discount_given"] == "54.00"
        assert summary["net_sales"] == "486.00"
        assert summary["order_total"] == "506.00"
        assert summary["average_order_value"] == "168.67"

    def test_excluded_orders_are_reported_apart(self, admin_client, scenario):
        coupon, _orders = scenario
        summary = detail(admin_client, coupon)["summary"]

        assert summary["cancelled_orders"] == 1
        assert summary["refunded_orders"] == 1
        assert summary["refunded_amount"] == "180.00"  # 200 − 20 coupon
        assert summary["failed_orders"] == 1

    def test_times_used_ignores_cancelled_redemptions(self, admin_client, scenario):
        """Five live redemptions (O1 O2 O4 O5 O6) and one cancelled (O3)."""
        coupon, _orders = scenario
        summary = detail(admin_client, coupon)["summary"]

        assert summary["times_used"] == 5
        assert summary["cancelled_redemptions"] == 1

    def test_first_and_last_use(self, admin_client, scenario):
        coupon, orders = scenario
        summary = detail(admin_client, coupon)["summary"]

        assert summary["first_used_at"] is not None
        assert summary["last_used_at"] is not None
        assert summary["first_used_at"] < summary["last_used_at"]

    def test_the_date_filter_narrows_every_figure(self, admin_client, scenario):
        """O6 happened 40 days ago — outside the last 30 days."""
        coupon, _orders = scenario
        since = (timezone.localdate() - timedelta(days=30)).isoformat()

        summary = detail(admin_client, coupon, date_from=since)["summary"]

        assert summary["orders"] == 2
        assert summary["gross_sales"] == "340.00"
        assert summary["discount_given"] == "34.00"
        assert summary["net_sales"] == "306.00"
        assert summary["times_used"] == 4

        before = (timezone.localdate() - timedelta(days=31)).isoformat()
        old = detail(admin_client, coupon, date_to=before)["summary"]
        assert old["orders"] == 1
        assert old["net_sales"] == "180.00"

    def test_an_inverted_range_is_refused(self, admin_client, scenario):
        """Zeros that look genuine are worse than an error."""
        coupon, _orders = scenario
        response = admin_client.get(
            url("coupon-analytics", coupon.pk),
            {"date_from": "2026-10-10", "date_to": "2026-10-01"},
        )
        assert response.status_code == 400

    def test_an_unused_coupon_is_all_zeros_not_an_error(self, admin_client):
        coupon = make_coupon("NEVER")
        body = detail(admin_client, coupon)

        assert body["summary"]["times_used"] == 0
        assert body["summary"]["orders"] == 0
        assert body["summary"]["net_sales"] == "0.00"
        assert body["summary"]["average_order_value"] == "0.00"
        assert body["summary"]["last_used_at"] is None
        assert body["products"] == []
        assert body["series"]["points"] == []

    def test_money_crosses_the_wire_as_strings(self, admin_client, scenario):
        coupon, _orders = scenario
        summary = detail(admin_client, coupon)["summary"]
        assert isinstance(summary["net_sales"], str)
        assert isinstance(summary["order_total"], str)

    def test_a_cancelled_redemption_on_a_live_order_does_not_count(self, admin_client, p1):
        """The redemption's own flag wins: the system said this use does not count."""
        coupon = make_coupon("FLAGGED")
        make_order(
            coupon,
            make_user("f@test.local"),
            [(p1, 1, "100", "0")],
            coupon_discount="10.00",
            redemption_cancelled=True,
        )
        summary = detail(admin_client, coupon)["summary"]
        assert summary["orders"] == 0
        assert summary["cancelled_orders"] == 1


class TestRemainingUses:
    def test_limits_and_balance(self, admin_client):
        owner = make_user("owner@test.local")
        coupon = make_coupon(
            "LIMITED", usage_limit=10, usage_count=3, usage_limit_per_user=2, owner=owner
        )
        CouponRedemption.objects.create(
            coupon=coupon, user=owner, discount_amount=D("5"), reference_type="order"
        )

        summary = detail(admin_client, coupon)["summary"]

        assert summary["remaining_total"] == 7
        assert summary["usage_limit_per_user"] == 2
        assert summary["owner_remaining"] == 1
        assert summary["customers_at_limit"] == 0

    def test_unlimited_is_none_not_zero(self, admin_client):
        coupon = make_coupon("OPEN")
        summary = detail(admin_client, coupon)["summary"]
        assert summary["remaining_total"] is None
        assert summary["owner_remaining"] is None

    def test_customers_at_their_personal_limit(self, admin_client):
        coupon = make_coupon("ONCE", usage_limit_per_user=1)
        for index in range(3):
            CouponRedemption.objects.create(
                coupon=coupon, user=make_user(f"once{index}@test.local"), discount_amount=D("5")
            )
        assert detail(admin_client, coupon)["summary"]["customers_at_limit"] == 3


# ═══════════════════════════════════════════════════════════
#  The product breakdown
# ═══════════════════════════════════════════════════════════


class TestProducts:
    def test_units_revenue_and_allocated_discount(self, admin_client, scenario):
        """
        P1: O1 200 + O2 (100 − 10 line discount) = 290 · 3 units · discount 20 + 9
        P2: O1 50 + O6 200                      = 250 · 5 units · discount  5 + 20
        """
        coupon, _orders = scenario
        rows = detail(admin_client, coupon)["products"]

        assert [row["sku"] for row in rows] == ["AN-1", "AN-2"]  # by revenue

        p1, p2 = rows
        assert (p1["units"], p1["revenue"], p1["discount"], p1["net_revenue"]) == (
            3,
            "290.00",
            "29.00",
            "261.00",
        )
        assert (p2["units"], p2["revenue"], p2["discount"], p2["net_revenue"]) == (
            5,
            "250.00",
            "25.00",
            "225.00",
        )

    def test_the_product_discounts_add_back_to_the_order_discounts(self, admin_client, scenario):
        coupon, _orders = scenario
        body = detail(admin_client, coupon)

        allocated = sum(D(row["discount"]) for row in body["products"])
        assert allocated == D(body["summary"]["discount_given"])

        revenue = sum(D(row["revenue"]) for row in body["products"])
        assert revenue == D(body["summary"]["gross_sales"])

    def test_excluded_orders_do_not_appear_in_the_breakdown(self, admin_client, scenario):
        coupon, _orders = scenario
        rows = detail(admin_client, coupon)["products"]
        # O3 O4 O5 would have added 1 + 2 P1 and 2 P2
        assert sum(row["units"] for row in rows) == 8

    def test_a_scoped_coupon_discounts_only_its_own_products(self, admin_client, p1, p2):
        """
        ⚠️  A coupon restricted to P1 never "discounts" P2: the whole 10.00 lands on P1
            even though P2 sits in the same order at the same value.
        """
        coupon = make_coupon("SCOPED")
        coupon.products.add(p1)
        make_order(
            coupon,
            make_user("s@test.local"),
            [(p1, 1, "100", "0"), (p2, 2, "50", "0")],
            coupon_discount="10.00",
        )

        rows = {row["sku"]: row for row in detail(admin_client, coupon)["products"]}

        assert rows["AN-1"]["discount"] == "10.00"
        assert rows["AN-2"]["discount"] == "0.00"

    def test_a_category_scope_is_respected_too(self, admin_client, p1, p2, other_category):
        coupon = make_coupon("CATSCOPE")
        coupon.categories.add(other_category)  # P2's category
        make_order(
            coupon,
            make_user("c@test.local"),
            [(p1, 1, "100", "0"), (p2, 2, "50", "0")],
            coupon_discount="8.00",
        )

        rows = {row["sku"]: row for row in detail(admin_client, coupon)["products"]}

        assert rows["AN-1"]["discount"] == "0.00"
        assert rows["AN-2"]["discount"] == "8.00"

    def test_a_scope_edited_after_the_sale_still_adds_up(self, admin_client, p1, p2):
        """No line matches the *current* scope: everything shares, and the sum still reconciles."""
        coupon = make_coupon("MOVED")
        make_order(
            coupon,
            make_user("m@test.local"),
            [(p1, 1, "100", "0"), (p2, 1, "100", "0")],
            coupon_discount="10.00",
        )
        unrelated = make_coupon("OTHERP").products
        unrelated.add(p2)  # a different coupon — the scope below is empty of matches
        coupon.products.add(
            p2.__class__.objects.create(
                sku="AN-9",
                name_ar="x",
                name_en="x",
                category=p1.category,
                base_price=D("1"),
            )
        )

        rows = detail(admin_client, coupon)["products"]
        assert sum(D(row["discount"]) for row in rows) == D("10.00")

    def test_largest_remainder_allocation_never_loses_a_cent(self):
        shares = analytics.allocate(D("10.00"), [D("1"), D("1"), D("1")])
        assert shares == [D("3.34"), D("3.33"), D("3.33")]
        assert sum(shares) == D("10.00")

        shares = analytics.allocate(D("0.01"), [D("5"), D("5")])
        assert sum(shares) == D("0.01")

        assert analytics.allocate(D("10"), [D("0"), D("0")]) == [D("0.00"), D("0.00")]
        assert analytics.allocate(D("0"), [D("5")]) == [D("0.00")]

    def test_odd_splits_across_many_orders_reconcile(self, admin_client, p1, p2):
        coupon = make_coupon("ODD")
        for index in range(7):
            make_order(
                coupon,
                make_user(f"odd{index}@test.local"),
                [(p1, 1, "33.33", "0"), (p2, 1, "33.33", "0"), (p1, 3, "7.77", "0")],
                coupon_discount="9.99",
            )
        body = detail(admin_client, coupon)
        assert sum(D(r["discount"]) for r in body["products"]) == D("69.93")
        assert body["summary"]["discount_given"] == "69.93"

    def test_variant_colour_is_carried_from_the_line_snapshot(self, admin_client, p1):
        from promotions.tests.conftest import line_model

        coupon = make_coupon("COLOUR")
        order = make_order(
            coupon, make_user("col@test.local"), [(p1, 2, "100", "0")], coupon_discount="10.00"
        )
        line_model().objects.filter(order=order).update(
            variant_sku="AN-1-RED", color_name_ar="أحمر", color_name_en="Red", color_hex="#ff0000"
        )

        row = detail(admin_client, coupon)["products"][0]

        assert row["sku"] == "AN-1-RED"
        assert row["product_sku"] == "AN-1"
        assert row["color_name_en"] == "Red"
        assert row["color_hex"] == "#ff0000"


# ═══════════════════════════════════════════════════════════
#  The series and the order list
# ═══════════════════════════════════════════════════════════


class TestSeriesAndOrders:
    def test_the_series_fills_quiet_days_with_zeros(self, admin_client, scenario):
        coupon, _orders = scenario
        since = (timezone.localdate() - timedelta(days=10)).isoformat()

        series = detail(admin_client, coupon, date_from=since)["series"]

        assert series["granularity"] == "day"
        assert len(series["points"]) == 11
        today = series["points"][-1]
        assert today["redemptions"] == 4  # O1 O2 O4 O5 (O3 cancelled)
        assert today["orders"] == 2
        assert today["net_sales"] == "306.00"
        assert series["points"][0]["redemptions"] == 0

    def test_a_long_range_is_bucketed_by_month(self, admin_client, scenario):
        coupon, _orders = scenario
        since = (timezone.localdate() - timedelta(days=200)).isoformat()

        series = detail(admin_client, coupon, date_from=since)["series"]

        assert series["granularity"] == "month"
        assert sum(point["orders"] for point in series["points"]) == 3
        assert sum(point["redemptions"] for point in series["points"]) == 5
        assert all(point["date"].endswith("-01") for point in series["points"])

    def test_the_orders_list_is_paginated_and_masked(self, admin_client, scenario):
        coupon, orders = scenario
        response = admin_client.get(url("coupon-orders", coupon.pk), {"limit": 5})

        assert response.status_code == 200
        assert response.data["count"] == 6
        assert len(response.data["results"]) == 5

        number = orders["O1"].number
        row = next(item for item in response.data["results"] if item["number"] == number)
        assert row["counted"] is True
        assert row["contact"] == "b***@test.local"
        assert row["customer_name"] == "Buyer1"
        assert row["gross_sales"] == "250.00"
        assert row["discount"] == "25.00"
        assert row["net_sales"] == "225.00"
        assert row["order_total"] == "245.00"
        assert "buyer1@test.local" not in str(response.data)

    def test_the_orders_list_can_show_only_sales_or_only_the_excluded(self, admin_client, scenario):
        coupon, _orders = scenario
        sales = admin_client.get(url("coupon-orders", coupon.pk), {"only": "sales"})
        excluded = admin_client.get(url("coupon-orders", coupon.pk), {"only": "excluded"})

        assert sales.data["count"] == 3
        assert excluded.data["count"] == 3
        assert all(not row["counted"] for row in excluded.data["results"])

    def test_a_bad_only_value_is_refused(self, admin_client, scenario):
        coupon, _orders = scenario
        response = admin_client.get(url("coupon-orders", coupon.pk), {"only": "x"})
        assert response.status_code == 400


# ═══════════════════════════════════════════════════════════
#  The overview
# ═══════════════════════════════════════════════════════════


class TestOverview:
    def test_totals_and_ranking(self, admin_client, scenario, p1):
        coupon, _orders = scenario
        small = make_coupon("SMALL5", value=D("5"))
        make_order(
            small, make_user("small@test.local"), [(p1, 1, "100", "0")], coupon_discount="5.00"
        )
        make_coupon("IDLE")

        response = admin_client.get(url("coupons-analytics"))
        assert response.status_code == 200

        totals = response.data["totals"]
        assert totals["orders"] == 4
        assert totals["net_sales"] == "581.00"  # 486 + 95
        assert totals["discount_given"] == "59.00"
        assert totals["times_used"] == 6
        assert totals["coupons_used"] == 2

        counts = response.data["counts"]
        assert counts["coupons"] == 3

        # ranked by net sales, the unused one last
        assert [row["code"] for row in response.data["results"]] == ["DRX10", "SMALL5", "IDLE"]
        assert response.data["results"][0]["holder_name"] == "Dr. Test"

    def test_the_overview_respects_the_period(self, admin_client, scenario):
        since = (timezone.localdate() - timedelta(days=30)).isoformat()
        response = admin_client.get(url("coupons-analytics"), {"date_from": since})
        assert response.data["totals"]["net_sales"] == "306.00"
        assert response.data["results"][0]["net_sales"] == "306.00"

    def test_totals_do_not_move_when_searching(self, admin_client, scenario):
        make_coupon("OTHER7")
        everything = admin_client.get(url("coupons-analytics")).data["totals"]
        searched = admin_client.get(url("coupons-analytics"), {"search": "OTHER"})

        assert [row["code"] for row in searched.data["results"]] == ["OTHER7"]
        assert searched.data["totals"] == everything

    def test_ordering_and_a_bad_key(self, admin_client, scenario):
        make_coupon("AAA1")
        response = admin_client.get(url("coupons-analytics"), {"ordering": "code"})
        assert [row["code"] for row in response.data["results"]] == ["AAA1", "DRX10"]

        assert admin_client.get(url("coupons-analytics"), {"ordering": "bogus"}).status_code == 400

    def test_distinct_customers_across_coupons_are_not_double_counted(self, admin_client, p1):
        buyer = make_user("twice@test.local")
        for code in ("TWA", "TWB"):
            coupon = make_coupon(code)
            make_order(coupon, buyer, [(p1, 1, "100", "0")], coupon_discount="10.00")

        assert admin_client.get(url("coupons-analytics")).data["totals"]["customers"] == 1


# ═══════════════════════════════════════════════════════════
#  Holder fields and the coupon list
# ═══════════════════════════════════════════════════════════


class TestHolder:
    def draft(self, **overrides):
        body = {
            "code": "HOLD10",
            "name_ar": "حامل",
            "name_en": "Holder",
            "kind": "FIXED",
            "value": "5",
        }
        body.update(overrides)
        return body

    def test_holder_fields_are_created_edited_and_returned(self, admin_client):
        created = admin_client.post(
            url("coupons"),
            self.draft(holder_name="  Dr.   Sara  ", holder_note="partner"),
            format="json",
        )
        assert created.status_code == 201
        assert created.data["holder_name"] == "Dr. Sara"  # whitespace collapsed
        assert created.data["holder_note"] == "partner"

        edited = admin_client.patch(
            url("coupon-detail", created.data["id"]), {"holder_name": "Dr. Mona"}, format="json"
        )
        assert edited.status_code == 200
        assert Coupon.objects.get(pk=created.data["id"]).holder_name == "Dr. Mona"

    def test_the_holder_is_searchable(self, admin_client):
        make_coupon("AAA", holder_name="Sara Ahmed")
        make_coupon("BBB", holder_name="Omar")
        make_coupon("CCC", holder_note="introduced by sara")

        found = admin_client.get(url("coupons"), {"search": "sara"})
        assert sorted(row["code"] for row in found.data["results"]) == ["AAA", "CCC"]

        with_holder = admin_client.get(url("coupons"), {"has_holder": "true"})
        assert sorted(row["code"] for row in with_holder.data["results"]) == ["AAA", "BBB"]

    def test_the_list_carries_times_used_and_net_sales(self, admin_client, scenario):
        coupon, _orders = scenario
        row = admin_client.get(url("coupons")).data["results"][0]

        assert row["code"] == coupon.code
        assert row["times_used"] == 5
        assert row["net_sales"] == "486.00"

        since = (timezone.localdate() - timedelta(days=30)).isoformat()
        narrowed = admin_client.get(url("coupons"), {"date_from": since}).data["results"][0]
        assert narrowed["net_sales"] == "306.00"

    def test_a_single_coupon_response_also_carries_them(self, admin_client, scenario):
        coupon, _orders = scenario
        body = admin_client.get(url("coupon-detail", coupon.pk)).data
        assert body["net_sales"] == "486.00"
        assert body["times_used"] == 5


# ═══════════════════════════════════════════════════════════
#  Bulk creation
# ═══════════════════════════════════════════════════════════


class TestBulkCreate:
    def body(self, **overrides):
        body = {
            "holders": ["Dr. Sara", "Omar", "Mona"],
            "prefix": "dr-",
            "kind": "PERCENTAGE",
            "value": "15",
            "max_discount_amount": "200",
            "usage_limit": 100,
            "usage_limit_per_user": 2,
            "min_order_amount": "50",
        }
        body.update(overrides)
        return body

    def test_one_unique_code_per_holder(self, admin_client):
        response = admin_client.post(url("coupons-bulk"), self.body(), format="json")

        assert response.status_code == 201, response.data
        assert response.data["count"] == 3

        by_name = {row["holder_name"]: row["code"] for row in response.data["results"]}
        assert set(by_name) == {"Dr. Sara", "Omar", "Mona"}
        assert len(set(by_name.values())) == 3
        assert all(code.startswith("DR-") for code in by_name.values())
        assert all(len(code) == 3 + 6 for code in by_name.values())

        coupon = Coupon.objects.get(code=by_name["Omar"])
        assert coupon.holder_name == "Omar"
        assert coupon.name_ar == "Omar"
        assert coupon.value == D("15")
        assert coupon.usage_limit == 100
        assert coupon.usage_limit_per_user == 2
        assert coupon.min_order_amount == D("50")

    def test_codes_use_the_readable_alphabet(self, admin_client):
        response = admin_client.post(
            url("coupons-bulk"),
            self.body(holders=[f"P{i}" for i in range(60)], prefix=""),
            format="json",
        )
        assert response.status_code == 201
        for row in response.data["results"]:
            assert not set(row["code"]) & set("01OIL"), row["code"]

    def test_the_scope_is_copied_to_every_coupon(self, admin_client, p1, category):
        response = admin_client.post(
            url("coupons-bulk"),
            self.body(products=[str(p1.pk)], categories=[str(category.pk)]),
            format="json",
        )
        assert response.status_code == 201
        for row in response.data["results"]:
            coupon = Coupon.objects.get(pk=row["id"])
            assert list(coupon.products.all()) == [p1]
            assert list(coupon.categories.all()) == [category]

    def test_an_invalid_template_creates_nothing(self, admin_client):
        response = admin_client.post(url("coupons-bulk"), self.body(value="150"), format="json")
        assert response.status_code == 400
        assert Coupon.objects.count() == 0

    def test_duplicate_names_are_refused(self, admin_client):
        response = admin_client.post(
            url("coupons-bulk"), self.body(holders=["Sara", "sara", "Omar"]), format="json"
        )
        assert response.status_code == 400
        assert "holders" in response.data["fields"]
        assert Coupon.objects.count() == 0

    def test_blank_names_are_ignored_and_an_empty_list_is_refused(self, admin_client):
        ok = admin_client.post(
            url("coupons-bulk"), self.body(holders=["A", "", "  ", "B"]), format="json"
        )
        assert ok.status_code == 201
        assert ok.data["count"] == 2

        empty = admin_client.post(url("coupons-bulk"), self.body(holders=["", " "]), format="json")
        assert empty.status_code == 400

    def test_a_bad_prefix_is_refused(self, admin_client):
        response = admin_client.post(url("coupons-bulk"), self.body(prefix="مرحبا"), format="json")
        assert response.status_code == 400

    def test_a_collision_with_an_existing_code_is_drawn_again(self, admin_client, monkeypatch):
        from promotions import services

        make_coupon("DR-AAAAAA")
        draws = iter(["AAAAAA", "BBBBBB", "CCCCCC", "DDDDDD", "EEEEEE", "FFFFFF"])
        monkeypatch.setattr(services, "_random_suffix", lambda length=6: next(draws))

        response = admin_client.post(
            url("coupons-bulk"), self.body(holders=["A", "B"], prefix="DR-"), format="json"
        )

        assert response.status_code == 201
        codes = {row["code"] for row in response.data["results"]}
        assert "DR-AAAAAA" not in codes
        assert len(codes) == 2

    def test_the_batch_is_all_or_none(self, monkeypatch):
        """
        ⚠️  If the insert fails half way, nobody gets a code: re-running a half-done
            batch would mint a second code for the people already served.
        """
        from django.db import IntegrityError

        from promotions import services

        monkeypatch.setattr(
            services, "_fresh_codes", lambda count, prefix, length: ["SAME"] * count
        )

        with pytest.raises(IntegrityError):
            services.create_for_holders(
                ["A", "B", "C"],
                template={"kind": "FIXED", "value": D("5"), "usage_limit_per_user": 1},
            )

        assert Coupon.objects.count() == 0

    def test_it_is_audited_without_the_codes(self, admin_client):
        from core.models.audit import AuditAction, AuditLog

        response = admin_client.post(url("coupons-bulk"), self.body(), format="json")
        entry = AuditLog.objects.filter(action=AuditAction.CREATE).latest("created_at")

        assert entry.changes["count"] == 3
        for row in response.data["results"]:
            assert row["code"] not in str(entry.changes)
            assert row["code"] not in entry.object_repr


# ═══════════════════════════════════════════════════════════
#  Permissions and query counts
# ═══════════════════════════════════════════════════════════


class TestAccess:
    @pytest.mark.parametrize(
        "name, needs_coupon, method",
        [
            ("coupons-analytics", False, "get"),
            ("coupon-analytics", True, "get"),
            ("coupon-orders", True, "get"),
            ("coupons-bulk", False, "post"),
        ],
    )
    def test_a_customer_gets_403(self, customer_client, name, needs_coupon, method):
        args = (make_coupon("LOCKED").pk,) if needs_coupon else ()
        response = getattr(customer_client, method)(url(name, *args))
        assert response.status_code == 403

    def test_anonymous_is_refused(self):
        from rest_framework.test import APIClient

        assert APIClient().get(url("coupons-analytics")).status_code in (401, 403)

    def test_an_unknown_coupon_is_404(self, admin_client):
        import uuid

        assert admin_client.get(url("coupon-analytics", uuid.uuid4())).status_code == 404
        assert admin_client.get(url("coupon-orders", uuid.uuid4())).status_code == 404


def count_queries(client, path, params=None) -> int:
    # ⚠️  One warm-up call: the first request pays for caches (permissions, content
    #     types) that every later one reads for free, which would read as "fewer
    #     queries with more rows".
    client.get(path, params or {})
    with CaptureQueriesContext(connection) as captured:
        response = client.get(path, params or {})
    assert response.status_code == 200
    return len(captured)


class TestNoNPlusOne:
    def populate(self, coupons: int, p1, start: int = 0):
        for index in range(start, start + coupons):
            coupon = make_coupon(f"BULK{index}")
            make_order(
                coupon,
                make_user(f"bulk{index}@test.local"),
                [(p1, 1, "100", "0")],
                coupon_discount="10.00",
            )

    def test_the_coupon_list_costs_the_same_for_any_page_size(self, admin_client, p1):
        self.populate(2, p1)
        few = count_queries(admin_client, url("coupons"))

        self.populate(10, p1, start=2)
        many = count_queries(admin_client, url("coupons"))

        assert many == few

    def test_the_overview_costs_the_same_for_any_number_of_coupons(self, admin_client, p1):
        for index in range(2):
            coupon = make_coupon(f"OVA{index}")
            make_order(
                coupon,
                make_user(f"ova{index}@test.local"),
                [(p1, 1, "100", "0")],
                coupon_discount="10.00",
            )
        few = count_queries(admin_client, url("coupons-analytics"))

        for index in range(10):
            coupon = make_coupon(f"OVB{index}")
            make_order(
                coupon,
                make_user(f"ovb{index}@test.local"),
                [(p1, 1, "100", "0")],
                coupon_discount="10.00",
            )
        many = count_queries(admin_client, url("coupons-analytics"))

        assert many == few

    def test_the_drawer_does_not_grow_with_the_orders(self, admin_client, p1, p2):
        coupon = make_coupon("DRAWER")
        for index in range(2):
            make_order(
                coupon,
                make_user(f"d{index}@test.local"),
                [(p1, 1, "100", "0"), (p2, 1, "50", "0")],
                coupon_discount="10.00",
            )
        path = url("coupon-analytics", coupon.pk)
        few = count_queries(admin_client, path)

        for index in range(2, 12):
            make_order(
                coupon,
                make_user(f"d{index}@test.local"),
                [(p1, 1, "100", "0"), (p2, 1, "50", "0")],
                coupon_discount="10.00",
            )

        assert count_queries(admin_client, path) == few

    def test_the_orders_page_does_not_grow_with_the_orders(self, admin_client, p1):
        coupon = make_coupon("PAGE")
        for index in range(2):
            make_order(
                coupon,
                make_user(f"pg{index}@test.local"),
                [(p1, 1, "100", "0")],
                coupon_discount="10.00",
            )
        path = url("coupon-orders", coupon.pk)
        few = count_queries(admin_client, path)

        for index in range(2, 15):
            make_order(
                coupon,
                make_user(f"pg{index}@test.local"),
                [(p1, 1, "100", "0")],
                coupon_discount="10.00",
            )

        assert count_queries(admin_client, path) == few


class TestBackfillAndLink:
    def test_the_link_is_derived_from_the_reference(self, scenario):
        _coupon, orders = scenario
        redemption = CouponRedemption.objects.get(reference_id=str(orders["O1"].pk))
        assert redemption.order_ref == orders["O1"].pk

    def test_a_non_order_reference_leaves_the_link_empty(self):
        coupon = make_coupon("REFS")
        redemption = CouponRedemption.objects.create(
            coupon=coupon,
            user=make_user("r@test.local"),
            discount_amount=D("1"),
            reference_type="order",
            reference_id="not-a-uuid",
        )
        assert redemption.order_ref is None

        loyalty = CouponRedemption.objects.create(
            coupon=coupon,
            user=make_user("r2@test.local"),
            discount_amount=D("1"),
            reference_type="loyalty",
            reference_id="123e4567-e89b-12d3-a456-426614174000",
        )
        assert loyalty.order_ref is None

    def test_a_redemption_without_an_order_counts_as_used_but_not_as_a_sale(self, admin_client):
        coupon = make_coupon("ORPHAN")
        CouponRedemption.objects.create(
            coupon=coupon,
            user=make_user("o@test.local"),
            discount_amount=D("1"),
        )
        summary = detail(admin_client, coupon)["summary"]
        assert summary["times_used"] == 1
        assert summary["orders"] == 0
