"""
Coupon report — "registered or guest? how much discount? who is new?"

⚠️  One hand-built shop (`buyers`) whose every number is worked out below, so a change
    to the classification rules fails here with a figure the owner can verify:

        registered   O1 r_new      200 −20      first ever order        → NEW
                     O2 r_ret      100 −10      has an older plain order → RETURNING
                     O7 claimed    100 −10      guest order, claimed     → counts REGISTERED, NEW
        guest        O3 + O6 newguest  (100 −10) + (50 −5)   one person (case/space differ) → NEW
                     O4 ret@…      100 −10      earlier order as a REGISTERED account with that
                                                e-mail                   → RETURNING
                     O5 again@…    100 −10      earlier GUEST order      → RETURNING
        excluded     cancelled · refunded · payment-failed — reported apart, never counted

        registered : 3 orders · 3 customers · gross 400 · discount 40 · net 360
        guest      : 4 orders · 3 customers · gross 350 · discount 35 · net 315
        all        : 7 orders · 6 customers · gross 750 · discount 75 · net 675
        new        : 3 customers · net 405 · discount 45      returning: 3 · net 270 · discount 30
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.apps import apps
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from promotions.models import CouponRedemption
from promotions.tests.conftest import (
    line_model,
    make_coupon,
    make_order,
    make_user,
    order_model,
)

pytestmark = pytest.mark.django_db

D = Decimal


def url(name, *args):
    return reverse(f"v1:promotions:{name}", args=args)


# ═══════════════════════════════════════════════════════════
#  Builders (the shared `make_order` only builds registered orders)
# ═══════════════════════════════════════════════════════════


def _stamp(order, redemption, days_ago):
    if days_ago:
        moment = timezone.now() - timedelta(days=days_ago)
        order_model().objects.filter(pk=order.pk).update(created_at=moment)
        if redemption is not None:
            CouponRedemption.objects.filter(pk=redemption.pk).update(created_at=moment)


def _lines(order, lines):
    for product, quantity, price, discount in lines:
        line_model().objects.create(
            order=order,
            product=product,
            product_sku=product.sku,
            product_name_ar=product.name_ar,
            product_name_en=product.name_en,
            quantity=quantity,
            unit_price=D(price),
            discount_amount=D(discount),
        )


def guest_order(
    coupon,
    email,
    lines,
    *,
    coupon_discount,
    name="ضيف",
    phone="+201001234567",
    status="DELIVERED",
    payment_status="PAID",
    days_ago=0,
    redemption_cancelled=False,
):
    """A coupon order placed with no account: customer NULL, e-mail on the order."""
    subtotal = sum((D(price) * qty for _p, qty, price, _d in lines), D("0"))
    order = order_model().objects.create(
        customer=None,
        channel="ONLINE",
        contact_email=email,
        recipient_name=name,
        recipient_phone=phone,
        status=status,
        payment_status=payment_status,
        subtotal=subtotal,
        discount_total=D(coupon_discount),
        coupon_discount=D(coupon_discount),
        grand_total=subtotal - D(coupon_discount),
        coupon_code=coupon.code,
    )
    _lines(order, lines)
    redemption = CouponRedemption.objects.create(
        coupon=coupon,
        user=None,
        is_guest=True,
        guest_email=email,
        discount_amount=D(coupon_discount),
        order_amount=order.grand_total,
        reference_type="order",
        reference_id=str(order.pk),
        is_cancelled=redemption_cancelled,
    )
    _stamp(order, redemption, days_ago)
    return order


def plain_order(buyer, lines, *, email="", days_ago=10, status="DELIVERED", payment="PAID"):
    """An earlier order that used NO coupon — a registered `buyer` (User) or a guest (None)."""
    from customers.models import CustomerProfile

    profile = None
    if buyer is not None:
        profile, _ = CustomerProfile.objects.get_or_create(
            user=buyer, defaults={"display_name_ar": buyer.first_name}
        )
    subtotal = sum((D(price) * qty for _p, qty, price, _d in lines), D("0"))
    order = order_model().objects.create(
        customer=profile,
        channel="ONLINE",
        contact_email=email,
        status=status,
        payment_status=payment,
        subtotal=subtotal,
        grand_total=subtotal,
    )
    _lines(order, lines)
    _stamp(order, None, days_ago)
    return order


def claim(order, user, days_ago=0):
    """What `orders.guest.claim_orders` does to an order: attach the account, stamp the time."""
    from customers.models import CustomerProfile

    profile, _ = CustomerProfile.objects.get_or_create(
        user=user, defaults={"display_name_ar": user.first_name}
    )
    order_model().objects.filter(pk=order.pk).update(customer=profile, claimed_at=timezone.now())
    CouponRedemption.objects.filter(order_ref=order.pk).update(user=user)


@pytest.fixture
def buyers(db, p1, p2):
    coupon = make_coupon("REPORT", holder_name="Dr. Report")

    r_new = make_user("rnew@test.local", name="جديد")
    r_ret = make_user("ret@test.local", name="عائد")
    r_claimed = make_user("claimed@test.local", name="مربوط")
    r_other = make_user("other@test.local", name="آخر")

    plain_order(r_ret, [(p1, 1, "100", "0")], days_ago=10)

    o = {}
    o["O1"] = make_order(coupon, r_new, [(p1, 2, "100", "0")], coupon_discount="20.00")
    o["O2"] = make_order(coupon, r_ret, [(p1, 1, "100", "0")], coupon_discount="10.00")

    # a guest order, later claimed by an account
    o["O7"] = guest_order(
        coupon, "claimed@test.local", [(p2, 2, "50", "0")], coupon_discount="10.00", name="مربوط"
    )
    claim(o["O7"], r_claimed)

    o["O3"] = guest_order(
        coupon, "newguest@x.com", [(p2, 2, "50", "0")], coupon_discount="10.00", name="ضيف جديد"
    )
    o["O6"] = guest_order(
        coupon, " NewGuest@X.com", [(p2, 1, "50", "0")], coupon_discount="5.00", name="ضيف جديد"
    )
    o["O4"] = guest_order(
        coupon, "RET@test.local", [(p1, 1, "100", "0")], coupon_discount="10.00", name="عائد ضيف"
    )
    plain_order(None, [(p1, 1, "100", "0")], email="AGAIN@x.com", days_ago=20)
    o["O5"] = guest_order(
        coupon, "again@x.com", [(p1, 1, "100", "0")], coupon_discount="10.00", name="مكرر"
    )

    # ── never counted ──
    o["X_cancel"] = guest_order(
        coupon,
        "cancel@x.com",
        [(p1, 1, "100", "0")],
        coupon_discount="10.00",
        status="CANCELLED",
        payment_status="UNPAID",
        redemption_cancelled=True,
    )
    o["X_refund"] = make_order(
        coupon, r_other, [(p1, 2, "100", "0")], coupon_discount="20.00", status="REFUNDED"
    )
    o["X_failed"] = guest_order(
        coupon,
        "failed@x.com",
        [(p2, 2, "50", "0")],
        coupon_discount="10.00",
        status="PENDING",
        payment_status="FAILED",
    )
    return coupon, o


def summary(client, coupon, **params):
    response = client.get(url("coupon-analytics", coupon.pk), params)
    assert response.status_code == 200, response.data
    return response.data


def customers(client, coupon, **params):
    response = client.get(url("coupon-customers", coupon.pk), params)
    assert response.status_code == 200, response.data
    return response.data


# ═══════════════════════════════════════════════════════════
#  Registered vs guest
# ═══════════════════════════════════════════════════════════


class TestCustomerType:
    def test_the_split_matches_the_hand_worked_numbers(self, admin_client, buyers):
        coupon, _o = buyers
        split = summary(admin_client, coupon)["summary"]["by_customer_type"]

        assert split["registered"] == {
            "orders": 3,
            "customers": 3,
            "gross": "400.00",
            "discount": "40.00",
            "net": "360.00",
            "order_total": "360.00",
        }
        assert split["guest"] == {
            "orders": 4,
            "customers": 3,
            "gross": "350.00",
            "discount": "35.00",
            "net": "315.00",
            "order_total": "315.00",
        }

    def test_the_two_halves_add_up_to_the_totals(self, admin_client, buyers):
        coupon, _o = buyers
        body = summary(admin_client, coupon)["summary"]
        split = body["by_customer_type"]

        assert body["orders"] == split["registered"]["orders"] + split["guest"]["orders"] == 7
        assert body["customers"] == 6
        assert D(body["gross_sales"]) == D(split["registered"]["gross"]) + D(
            split["guest"]["gross"]
        )
        assert D(body["discount_given"]) == D("75.00")
        assert D(body["net_sales"]) == D("675.00")

    def test_a_claimed_guest_order_counts_as_registered(self, admin_client, buyers):
        """The account owns it now — but the customers list still says it was bought as a guest."""
        coupon, _o = buyers
        rows = {row["email"]: row for row in customers(admin_client, coupon)["results"]}

        claimed = rows["claimed@test.local"]
        assert claimed["customer_type"] == "REGISTERED"
        assert claimed["purchased_as"] == "GUEST"
        assert claimed["has_account_now"] is True
        assert claimed["customer_id"] is not None

    def test_excluded_orders_are_reported_apart_not_counted(self, admin_client, buyers):
        coupon, _o = buyers
        body = summary(admin_client, coupon)["summary"]

        assert body["cancelled_orders"] == 1
        assert body["refunded_orders"] == 1
        assert body["failed_orders"] == 1
        # none of them is a buyer of the code
        emails = {row["email"] for row in customers(admin_client, coupon)["results"]}
        assert not emails & {"cancel@x.com", "failed@x.com", "other@test.local"}

    def test_discount_share_of_gross(self, admin_client, buyers):
        coupon, _o = buyers
        body = summary(admin_client, coupon)["summary"]

        assert body["discount_share_of_gross"] == 10.0  # 75 / 750
        assert body["discount_by_customer_type"] == {"registered": "40.00", "guest": "35.00"}

    def test_an_unused_coupon_is_all_zeros(self, admin_client):
        body = summary(admin_client, make_coupon("IDLE"))["summary"]

        assert body["by_customer_type"]["guest"]["orders"] == 0
        assert body["new_customers"] == {
            "count": 0,
            "orders": 0,
            "net_sales": "0.00",
            "discount": "0.00",
        }
        assert body["new_customer_rate"] == 0.0
        assert body["discount_share_of_gross"] == 0.0


# ═══════════════════════════════════════════════════════════
#  New vs returning
# ═══════════════════════════════════════════════════════════


class TestNewVsReturning:
    def test_new_and_returning_totals(self, admin_client, buyers):
        coupon, _o = buyers
        body = summary(admin_client, coupon)["summary"]

        assert body["new_customers"]["count"] == 3
        assert body["new_customers"]["net_sales"] == "405.00"
        assert body["new_customers"]["discount"] == "45.00"
        assert body["returning_customers"]["count"] == 3
        assert body["returning_customers"]["net_sales"] == "270.00"
        assert body["returning_customers"]["discount"] == "30.00"
        assert body["new_customer_rate"] == 50.0

    def test_the_same_guest_with_a_different_spelling_is_one_new_customer(
        self, admin_client, buyers
    ):
        coupon, _o = buyers
        rows = customers(admin_client, coupon, search="newguest")["results"]

        assert len(rows) == 1
        assert rows[0]["orders"] == 2
        assert rows[0]["net_sales"] == "135.00"
        assert rows[0]["is_new_customer"] is True

    def test_a_guest_with_an_earlier_registered_order_is_returning(self, admin_client, buyers):
        """`RET@test.local` bought as a guest, but the account `ret@test.local` ordered before."""
        coupon, _o = buyers
        guests = customers(admin_client, coupon, customer_type="GUEST")["results"]
        by_email = {row["email"].lower(): row for row in guests}

        assert by_email["ret@test.local"]["is_new_customer"] is False
        assert by_email["newguest@x.com"]["is_new_customer"] is True

    def test_a_guest_with_an_earlier_guest_order_is_returning(self, admin_client, buyers):
        coupon, _o = buyers
        rows = customers(admin_client, coupon, search="again@x.com")["results"]
        assert rows[0]["is_new_customer"] is False

    def test_a_registered_customer_with_an_earlier_order_is_returning(self, admin_client, buyers):
        coupon, _o = buyers
        rows = customers(admin_client, coupon, customer_type="REGISTERED")["results"]
        new_flags = {row["email"]: row["is_new_customer"] for row in rows}

        assert new_flags["rnew@test.local"] is True
        assert new_flags["ret@test.local"] is False

    def test_an_earlier_cancelled_order_does_not_make_a_customer_returning(
        self, admin_client, buyers, p1
    ):
        coupon = make_coupon("FRESH")
        user = make_user("fresh@test.local")
        plain_order(user, [(p1, 1, "100", "0")], days_ago=5, status="CANCELLED", payment="UNPAID")
        make_order(coupon, user, [(p1, 1, "100", "0")], coupon_discount="10.00")

        body = summary(admin_client, coupon)["summary"]
        assert body["new_customers"]["count"] == 1
        assert body["returning_customers"]["count"] == 0

    def test_new_means_new_to_the_shop_not_to_the_period(self, admin_client, p1):
        """First ever order 40 days ago on this code: a customer who only ordered again today
        is RETURNING in a window that does not contain their first order."""
        coupon = make_coupon("PERIOD")
        user = make_user("period@test.local")
        make_order(coupon, user, [(p1, 1, "100", "0")], coupon_discount="10.00", days_ago=40)
        make_order(coupon, user, [(p1, 1, "100", "0")], coupon_discount="10.00")

        since = (timezone.localdate() - timedelta(days=30)).isoformat()
        windowed = summary(admin_client, coupon, date_from=since)["summary"]
        assert windowed["new_customers"]["count"] == 0
        assert windowed["returning_customers"]["count"] == 1

        whole = summary(admin_client, coupon)["summary"]
        assert whole["new_customers"]["count"] == 1  # one buyer, new as a whole
        assert whole["new_customers"]["orders"] == 2
        assert whole["returning_customers"]["count"] == 0


# ═══════════════════════════════════════════════════════════
#  The period
# ═══════════════════════════════════════════════════════════


class TestPeriod:
    def test_the_date_filter_applies_to_every_new_figure(self, admin_client, p1):
        coupon = make_coupon("DATES")
        old_user, new_user = make_user("old@test.local"), make_user("recent@test.local")
        make_order(coupon, old_user, [(p1, 1, "100", "0")], coupon_discount="10.00", days_ago=40)
        guest_order(coupon, "g@x.com", [(p1, 1, "100", "0")], coupon_discount="10.00", days_ago=40)
        make_order(coupon, new_user, [(p1, 2, "100", "0")], coupon_discount="20.00")
        guest_order(coupon, "g2@x.com", [(p1, 3, "100", "0")], coupon_discount="30.00")

        since = (timezone.localdate() - timedelta(days=30)).isoformat()
        body = summary(admin_client, coupon, date_from=since)["summary"]

        assert body["by_customer_type"]["registered"]["orders"] == 1
        assert body["by_customer_type"]["registered"]["discount"] == "20.00"
        assert body["by_customer_type"]["guest"]["orders"] == 1
        assert body["by_customer_type"]["guest"]["net"] == "270.00"
        assert body["new_customers"]["count"] == 2
        assert body["discount_by_customer_type"] == {"registered": "20.00", "guest": "30.00"}

        before = (timezone.localdate() - timedelta(days=31)).isoformat()
        old = summary(admin_client, coupon, date_to=before)["summary"]
        assert old["by_customer_type"]["registered"]["orders"] == 1
        assert old["by_customer_type"]["guest"]["orders"] == 1

        listed = customers(admin_client, coupon, date_from=since)
        assert listed["count"] == 2


# ═══════════════════════════════════════════════════════════
#  The customers list
# ═══════════════════════════════════════════════════════════


class TestCustomersList:
    def test_every_row_has_the_documented_keys(self, admin_client, buyers):
        coupon, _o = buyers
        row = customers(admin_client, coupon)["results"][0]

        assert set(row) == {
            "customer_key",
            "customer_type",
            "purchased_as",
            "has_account_now",
            "customer_id",
            "customer_number",
            "name",
            "email",
            "phone",
            "orders",
            "gross_sales",
            "net_sales",
            "discount",
            "first_used_at",
            "last_used_at",
            "is_new_customer",
        }

    def test_the_default_order_is_net_sales_descending(self, admin_client, buyers):
        coupon, _o = buyers
        body = customers(admin_client, coupon)

        assert body["count"] == 6
        nets = [D(row["net_sales"]) for row in body["results"]]
        assert nets == sorted(nets, reverse=True)
        assert body["results"][0]["email"] == "rnew@test.local"

    def test_ordering_and_paging(self, admin_client, buyers):
        coupon, _o = buyers

        first = customers(admin_client, coupon, ordering="orders", limit=4)
        second = customers(admin_client, coupon, ordering="orders", limit=4, page=2)

        assert len(first["results"]) == 4
        assert len(second["results"]) == 2
        assert first["pages"] == 2
        keys = [row["customer_key"] for row in first["results"] + second["results"]]
        assert len(set(keys)) == 6  # nothing repeated, nothing skipped
        counts = [row["orders"] for row in first["results"] + second["results"]]
        assert counts == sorted(counts)

    def test_an_unknown_ordering_is_refused(self, admin_client, buyers):
        coupon, _o = buyers
        response = admin_client.get(url("coupon-customers", coupon.pk), {"ordering": "password"})
        assert response.status_code == 400

    def test_search_by_name_email_and_phone(self, admin_client, buyers):
        coupon, _o = buyers

        assert customers(admin_client, coupon, search="مكرر")["count"] == 1
        assert customers(admin_client, coupon, search="AGAIN@X")["count"] == 1
        assert customers(admin_client, coupon, search="1234567")["count"] == 4  # the guests' phone
        assert customers(admin_client, coupon, search="nobody-by-this-name")["count"] == 0

    def test_the_type_and_newness_filters(self, admin_client, buyers):
        coupon, _o = buyers

        assert customers(admin_client, coupon, customer_type="GUEST")["count"] == 3
        assert customers(admin_client, coupon, customer_type="REGISTERED")["count"] == 3
        assert customers(admin_client, coupon, new="true")["count"] == 3
        assert customers(admin_client, coupon, new="false")["count"] == 3

    def test_contact_details_are_complete_for_the_pricing_admin(self, admin_client, buyers):
        """The report of who bought is unmasked; the orders list keeps masking."""
        coupon, _o = buyers
        guest = customers(admin_client, coupon, search="again@x.com")["results"][0]
        assert guest["email"] == "again@x.com"
        assert guest["phone"] == "+201001234567"
        assert guest["has_account_now"] is False
        assert guest["purchased_as"] == "GUEST"

        orders = admin_client.get(url("coupon-orders", coupon.pk)).data["results"]
        assert all("***" in row["contact"] or "*" in row["contact"] for row in orders)

    def test_a_guest_whose_email_has_an_account_today_is_flagged(self, admin_client, buyers):
        coupon, _o = buyers
        row = customers(admin_client, coupon, search="RET@test.local", customer_type="GUEST")[
            "results"
        ][0]
        assert row["customer_type"] == "GUEST"
        assert row["has_account_now"] is True  # ret@test.local registered, order never claimed

    def test_not_for_customers_or_anonymous(self, customer_client, buyers):
        coupon, _o = buyers
        assert customer_client.get(url("coupon-customers", coupon.pk)).status_code == 403

    def test_unknown_coupon_is_404(self, admin_client):
        import uuid

        assert admin_client.get(url("coupon-customers", uuid.uuid4())).status_code == 404


# ═══════════════════════════════════════════════════════════
#  The overview, the holder roll-up and the series
# ═══════════════════════════════════════════════════════════


class TestOverview:
    def overview(self, client, **params):
        response = client.get(url("coupons-analytics"), params)
        assert response.status_code == 200, response.data
        return response.data

    def test_totals_carry_the_buyer_split(self, admin_client, buyers):
        body = self.overview(admin_client)

        assert body["totals"]["by_customer_type"]["registered"]["orders"] == 3
        assert body["totals"]["by_customer_type"]["guest"]["orders"] == 4
        assert body["totals"]["customers"] == 6
        assert body["totals"]["new_customers"]["count"] == 3
        assert body["totals"]["discount_share_of_gross"] == 10.0
        assert body["group_by"] == "coupon"

    def test_a_person_who_used_two_codes_is_one_customer_overall(self, admin_client, p1):
        first, second = make_coupon("ONE"), make_coupon("TWO")
        user = make_user("both@test.local")
        make_order(first, user, [(p1, 1, "100", "0")], coupon_discount="10.00", days_ago=3)
        make_order(second, user, [(p1, 1, "100", "0")], coupon_discount="10.00")
        guest_order(first, "same@x.com", [(p1, 1, "100", "0")], coupon_discount="10.00")
        guest_order(second, "SAME@x.com", [(p1, 1, "100", "0")], coupon_discount="10.00")

        body = self.overview(admin_client)["totals"]
        assert body["customers"] == 2
        assert body["by_customer_type"]["registered"]["customers"] == 1
        assert body["by_customer_type"]["guest"]["customers"] == 1
        # first order of `both` carried code ONE, so they are new overall
        assert body["new_customers"]["count"] == 2

    def test_per_coupon_rows_carry_the_split_and_the_owner(self, admin_client, buyers, p1):
        owner = make_user("owner@test.local", name="المالك")
        personal = make_coupon("PERSONAL", owner=owner)
        make_order(personal, owner, [(p1, 1, "100", "0")], coupon_discount="10.00")

        rows = {row["code"]: row for row in self.overview(admin_client)["results"]}

        assert rows["REPORT"]["by_customer_type"]["guest"]["orders"] == 4
        assert rows["REPORT"]["owner"] is None
        assert rows["PERSONAL"]["owner"]["email"] == "owner@test.local"
        assert rows["PERSONAL"]["owner"]["name"] == "المالك"
        assert rows["PERSONAL"]["new_customers"]["count"] == 1

    def test_group_by_holder_combines_a_holders_codes(self, admin_client, p1):
        a1 = make_coupon("DRA1", holder_name="Dr. A")
        a2 = make_coupon("DRA2", holder_name="  dr. a ")
        b1 = make_coupon("DRB1", holder_name="Dr. B")
        make_coupon("NOHOLDER")
        user = make_user("shared@test.local")
        make_order(a1, user, [(p1, 1, "100", "0")], coupon_discount="10.00", days_ago=2)
        make_order(a2, user, [(p1, 1, "100", "0")], coupon_discount="10.00")
        guest_order(a2, "ga@x.com", [(p1, 2, "100", "0")], coupon_discount="20.00")
        guest_order(b1, "gb@x.com", [(p1, 1, "100", "0")], coupon_discount="10.00")

        body = self.overview(admin_client, group_by="holder", ordering="-orders")
        rows = {row["holder_name"].strip().lower(): row for row in body["results"]}

        assert body["group_by"] == "holder"
        assert body["results"][0]["holder_name"] == "Dr. A"  # most orders first
        dr_a = rows["dr. a"]
        assert [c["code"] for c in dr_a["codes"]] == ["DRA1", "DRA2"] or {
            c["code"] for c in dr_a["codes"]
        } == {"DRA1", "DRA2"}
        assert dr_a["coupons"] == 2
        assert dr_a["orders"] == 3
        assert dr_a["customers"] == 2  # `shared` used both codes: one customer
        assert dr_a["registered_orders"] == 2
        assert dr_a["guest_orders"] == 1
        assert dr_a["discount_given"] == "40.00"
        assert dr_a["net_sales"] == "360.00"
        assert dr_a["new_customers"]["count"] == 2
        assert rows["dr. b"]["customers"] == 1
        # the coupon with no holder is its own row, flagged
        unassigned = [row for row in body["results"] if row["unassigned"]]
        assert len(unassigned) == 1 and unassigned[0]["coupons"] == 1
        # and the rows add back to the totals
        assert sum(row["orders"] for row in body["results"]) == body["totals"]["orders"]

    def test_group_by_holder_lists_the_owning_members(self, admin_client, p1):
        owner = make_user("member@test.local", name="عضو")
        make_coupon("MEM1", holder_name="Dr. M", owner=owner)
        make_coupon("MEM2", holder_name="Dr. M", owner=owner)

        rows = self.overview(admin_client, group_by="holder")["results"]
        assert rows[0]["members"][0]["email"] == "member@test.local"
        assert rows[0]["members"][0]["codes"] == ["MEM1", "MEM2"] or set(
            rows[0]["members"][0]["codes"]
        ) == {"MEM1", "MEM2"}

    def test_a_bad_group_by_or_ordering_is_refused(self, admin_client):
        assert admin_client.get(url("coupons-analytics"), {"group_by": "x"}).status_code == 400
        assert (
            admin_client.get(
                url("coupons-analytics"), {"group_by": "holder", "ordering": "code"}
            ).status_code
            == 400
        )

    def test_the_discount_series_splits_registered_and_guest(self, admin_client, p1):
        coupon = make_coupon("SERIES")
        make_order(
            coupon,
            make_user("s1@test.local"),
            [(p1, 1, "100", "0")],
            coupon_discount="10.00",
            days_ago=2,
        )
        guest_order(coupon, "sg@x.com", [(p1, 1, "100", "0")], coupon_discount="25.00", days_ago=2)
        guest_order(coupon, "sg2@x.com", [(p1, 1, "100", "0")], coupon_discount="5.00")

        series = self.overview(admin_client)["discount_series"]

        assert series["granularity"] == "day"
        assert len(series["points"]) == 3  # two days ago, yesterday (a zero), today
        first, middle, last = series["points"]
        assert first["registered"]["discount"] == "10.00"
        assert first["guest"]["discount"] == "25.00"
        assert first["discount"] == "35.00"
        assert middle["discount"] == "0.00" and middle["orders"] == 0
        assert last["guest"]["orders"] == 1

    def test_the_detail_carries_the_same_series(self, admin_client, buyers):
        coupon, _o = buyers
        body = summary(admin_client, coupon)

        assert body["discount_series"]["points"]
        assert sum(D(p["discount"]) for p in body["discount_series"]["points"]) == D("75.00")


# ═══════════════════════════════════════════════════════════
#  Cost: flat query counts
# ═══════════════════════════════════════════════════════════


def _queries(client, name, *args, **params):
    # ⚠️  Once to warm the per-user permission cache: the first request of a session pays
    #     for loading the admin's permissions, which is not what is being measured.
    client.get(url(name, *args), params)
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url(name, *args), params)
    assert response.status_code == 200, getattr(response, "data", response)
    return len(ctx)


class TestQueryCount:
    """
    ⚠️  The baseline already has one registered and one guest buyer: an empty shop
        legitimately skips the lookups (series, account e-mails), which would make
        "the same cost" a comparison between two different code paths.
    """

    def _seed(self, coupon, p1, index):
        make_order(
            coupon,
            make_user(f"q{coupon.code}{index}@test.local"),
            [(p1, 1, "100", "0")],
            coupon_discount="1.00",
        )
        guest_order(
            coupon, f"g{coupon.code}{index}@x.com", [(p1, 1, "100", "0")], coupon_discount="1.00"
        )

    def test_the_overview_costs_the_same_for_one_coupon_or_many(self, admin_client, p1):
        first = make_coupon("Q0", holder_name="H0")
        self._seed(first, p1, 0)
        baseline = _queries(admin_client, "coupons-analytics")
        baseline_holder = _queries(admin_client, "coupons-analytics", group_by="holder")

        for index in range(1, 7):
            coupon = make_coupon(f"Q{index}", holder_name=f"H{index}")
            self._seed(coupon, p1, index)

        assert _queries(admin_client, "coupons-analytics") == baseline
        assert _queries(admin_client, "coupons-analytics", group_by="holder") == baseline_holder

    def test_the_customers_list_costs_the_same_for_any_number_of_buyers(self, admin_client, p1):
        coupon = make_coupon("QC")
        self._seed(coupon, p1, 0)
        small = _queries(admin_client, "coupon-customers", coupon.pk)

        for index in range(1, 12):
            self._seed(coupon, p1, index)

        assert _queries(admin_client, "coupon-customers", coupon.pk) == small

    def test_the_detail_costs_the_same_for_a_busy_coupon(self, admin_client, p1):
        coupon = make_coupon("QD")
        self._seed(coupon, p1, 0)
        small = _queries(admin_client, "coupon-analytics", coupon.pk)

        for index in range(1, 10):
            self._seed(coupon, p1, index)

        assert _queries(admin_client, "coupon-analytics", coupon.pk) == small


def test_the_orders_model_is_the_real_one():
    """Sanity: the registry lookup used by the analytics resolves."""
    assert apps.get_model("orders", "Order") is order_model()
