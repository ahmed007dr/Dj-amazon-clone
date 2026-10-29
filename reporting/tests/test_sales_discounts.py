"""
The sales-and-discounts report.

⚠️  What these tests guard is that the report **meets the Sales tab**, not that
    it is internally tidy:

        · the same orders — a sale is whatever `_sold_orders` says, nothing more
        · `invoiced_total` is the Sales tab's `gross_sales`, to the piaster
        · the discount, split by source, adds back up to the discount
        · a code stamped on an order is not a coupon order unless it was redeemed

    Every number below is worked out by hand in `shop` — a test that recomputes
    the expected value with the same query it is testing only proves it agrees
    with itself.
"""

from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from administration.models import AdminProfile
from catalog.models import Category, Product
from core.errors import BusinessError
from core.testing import grant_all_domains
from orders.models import Order, OrderChannel, OrderLine, OrderStatus, PaymentStatus
from promotions.models import Coupon, CouponRedemption
from promotions.tests.conftest import make_coupon, make_user
from reporting import services

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


# ═══════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def product(db):
    category = Category.objects.create(slug="disc-cat", name_ar="فئة", name_en="Cat")
    return Product.objects.create(
        sku="DISC-1", name_ar="صنف", name_en="Item", category=category, base_price=Decimal("100")
    )


@pytest.fixture
def viewer(db):
    from django.contrib.auth.models import Permission

    user = User.objects.create_user(
        email="disc-reports@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    user.is_active = True
    user.save()
    AdminProfile.objects.create(user=user)
    grant_all_domains(user)
    user.user_permissions.add(Permission.objects.get(codename="view_revenueentry"))
    return User.objects.get(pk=user.pk)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def at(day, hour=12):
    """
    A local moment on `day`.

    ⚠️  Built from the date, not as `now() - timedelta(days=n)`: across a DST change
        that is 23 or 25 hours, and near midnight it lands on the neighbouring day.
    """
    return timezone.make_aware(datetime.combine(day, time(hour)))


def make_sale(
    product,
    *,
    subtotal,
    coupon=None,
    coupon_discount="0",
    line_discount="0",
    manual_discount="0",
    tax="0",
    shipping="0",
    shipping_discount="0",
    status=OrderStatus.DELIVERED,
    channel=OrderChannel.ONLINE,
    day=None,
    redeem=True,
    redemption_cancelled=False,
    stamp_code="",
    grand_total=None,
):
    """
    An order with the money invariants the online checkout writes:

        discount_total = line discounts + coupon discount (+ the cashier's, at the counter)
        grand_total    = subtotal − discount_total + tax + shipping
    """
    subtotal, coupon_discount = Decimal(subtotal), Decimal(coupon_discount)
    line_discount, manual_discount = Decimal(line_discount), Decimal(manual_discount)
    discount_total = line_discount + manual_discount + coupon_discount
    total = (
        Decimal(grand_total)
        if grand_total is not None
        else subtotal - discount_total + Decimal(tax) + Decimal(shipping)
    )

    order = Order.objects.create(
        customer=None,
        channel=channel,
        status=status,
        payment_status=PaymentStatus.PAID,
        subtotal=subtotal,
        discount_total=discount_total,
        coupon_discount=coupon_discount,
        tax_total=Decimal(tax),
        shipping_total=Decimal(shipping),
        shipping_discount=Decimal(shipping_discount),
        grand_total=total,
        coupon_code=(coupon.code if coupon else stamp_code),
    )
    OrderLine.objects.create(
        order=order,
        product=product,
        product_sku=product.sku,
        product_name_ar=product.name_ar,
        product_name_en=product.name_en,
        quantity=1,
        unit_price=subtotal,
        list_price=subtotal,
        discount_amount=line_discount,
    )

    if coupon is not None and redeem:
        CouponRedemption.objects.create(
            coupon=coupon,
            user=make_user(f"buyer-{order.pk}@test.local"),
            discount_amount=coupon_discount,
            order_amount=total,
            reference_type="order",
            reference_id=str(order.pk),
            is_cancelled=redemption_cancelled,
        )

    if day is not None:
        Order.objects.filter(pk=order.pk).update(created_at=at(day))

    return order


@pytest.fixture
def shop(product):
    """
    Seven sales in the period, three orders that must not count, one outside it.

        order  what                                            subtotal  discount  grand
        A      DELIVERED  SAVE10 + 50 item promo + 14% tax        1000.00   145.00  1018.00
        B      PENDING    SAVE10                                   400.00    40.00   390.00
        C      CONFIRMED  WELCOME (fixed) + free shipping rule     200.00    25.00   175.00
        D      DELIVERED  loyalty coupon (personal)                300.00    30.00   270.00
        E      POS        cashier's manual 5%                      400.00    20.00   380.00
        F      DELIVERED  no discount                              500.00     0.00   500.00
        J      DELIVERED  a stale code stamped, never redeemed     100.00     0.00   100.00
        G      CANCELLED  SAVE10                                   900.00    90.00      —
        H      REFUNDED   POS manual                               700.00    70.00      —
        I      40 days ago, SAVE10                                 600.00    60.00      —

    Totals of A–F + J:  gross 2900.00 · discount 260.00 · net 2640.00 · 7 orders.
    """
    save10 = make_coupon("SAVE10", name_ar="خصم ١٠", name_en="Save 10", holder_name="Dr. Sara")
    welcome = make_coupon("WELCOME", kind="FIXED", value=Decimal("25"), name_ar="ترحيب")
    loyal = make_coupon("PTS-ABC123", kind="FIXED", owner=make_user("points-owner@test.local"))

    today = timezone.localdate()
    orders = {
        "A": make_sale(
            product,
            subtotal="1000",
            coupon=save10,
            coupon_discount="95",
            line_discount="50",
            tax="133",
            shipping="30",
        ),
        "B": make_sale(
            product,
            subtotal="400",
            coupon=save10,
            coupon_discount="40",
            shipping="30",
            status=OrderStatus.PENDING,
        ),
        "C": make_sale(
            product,
            subtotal="200",
            coupon=welcome,
            coupon_discount="25",
            shipping_discount="20",
            status=OrderStatus.CONFIRMED,
        ),
        "D": make_sale(product, subtotal="300", coupon=loyal, coupon_discount="30"),
        "E": make_sale(product, subtotal="400", manual_discount="20", channel=OrderChannel.POS),
        "F": make_sale(product, subtotal="500"),
        "J": make_sale(product, subtotal="100", stamp_code="EXPIRED1"),
        "G": make_sale(
            product,
            subtotal="900",
            coupon=save10,
            coupon_discount="90",
            status=OrderStatus.CANCELLED,
            redemption_cancelled=True,
        ),
        "H": make_sale(
            product,
            subtotal="700",
            manual_discount="70",
            status=OrderStatus.REFUNDED,
            channel=OrderChannel.POS,
        ),
        "I": make_sale(
            product,
            subtotal="600",
            coupon=save10,
            coupon_discount="60",
            day=today - timedelta(days=40),
        ),
    }
    return orders


def today_range():
    today = timezone.localdate()
    return today, today


def money(value):
    return Decimal(value)


# ═══════════════════════════════════════════════════════════
#  Totals meet the Sales tab
# ═══════════════════════════════════════════════════════════


class TestTotals:
    def test_the_waterfall_figures(self, shop):
        report = services.sales_discounts(*today_range())

        assert report["orders_count"] == 7
        assert report["gross_before_discount"] == "2900.00"
        assert report["discount_total"] == "260.00"
        assert report["net_after_discount"] == "2640.00"
        # 260 / 2900 — of the products' value, never of tax and shipping
        assert report["discount_percent"] == "8.97"
        assert report["tax_total"] == "133.00"
        assert report["shipping_total"] == "60.00"

    def test_order_counts(self, shop):
        report = services.sales_discounts(*today_range())

        assert report["discounted_orders"] == 5  # A B C D E
        assert report["coupon_orders"] == 4  # A B C D — J's stale code is not a coupon order

    def test_it_meets_the_sales_tab(self, shop):
        """
        ⚠️  The point of the whole report: `invoiced_total` is the Sales tab's gross.

            Two screens in one panel that disagree about the same orders is the
            defect `_sold_orders` exists to prevent.
        """
        report = services.sales_discounts(*today_range())
        sales = services.sales_summary(*today_range())

        assert report["orders_count"] == sales.orders_count
        assert report["invoiced_total"] == str(sales.gross_sales) == "2833.00"

    def test_the_waterfall_closes_for_online_and_ordinary_counter_sales(self, shop):
        report = services.sales_discounts(*today_range())

        net, tax, shipping = (
            money(report[key]) for key in ("net_after_discount", "tax_total", "shipping_total")
        )
        assert net + tax + shipping == money(report["invoiced_total"])
        assert report["unreconciled"] == "0.00"

    def test_cancelled_refunded_and_out_of_period_orders_are_not_counted(self, shop):
        """G cancelled · H refunded · I forty days old — none of them is in 2900."""
        report = services.sales_discounts(*today_range())

        assert report["gross_before_discount"] == "2900.00"
        assert report["discount_total"] == "260.00"

    def test_a_counter_sale_with_a_promotional_price_is_flagged_not_absorbed(self, product):
        """
        ⚠️  `pos.services.quote` records the line discount but charges the full
            subtotal, so the till and the discount waterfall disagree. The report
            says so instead of agreeing with itself.
        """
        make_sale(
            product,
            subtotal="400",
            line_discount="40",
            channel=OrderChannel.POS,
            grand_total="400",  # what the till actually charged
        )

        report = services.sales_discounts(*today_range())

        assert report["discount_total"] == "40.00"
        assert report["net_after_discount"] == "360.00"
        assert report["invoiced_total"] == "400.00"
        assert report["unreconciled"] == "40.00"

    def test_the_free_shipping_waiver_is_a_memo_outside_the_discount(self, shop):
        report = services.sales_discounts(*today_range())

        assert report["shipping_waived"] == "20.00"
        # ⚠️  It is not in `subtotal`, so counting it would break the waterfall
        assert report["discount_total"] == "260.00"


# ═══════════════════════════════════════════════════════════
#  By source
# ═══════════════════════════════════════════════════════════


class TestBySource:
    def test_each_source_carries_what_the_order_recorded(self, shop):
        rows = {row["source"]: row for row in services.sales_discounts(*today_range())["by_source"]}

        assert rows["coupon"]["amount"] == "160.00"  # 95 + 40 + 25
        assert rows["loyalty_points"]["amount"] == "30.00"
        assert rows["item_promotion"]["amount"] == "50.00"
        assert rows["manual"]["amount"] == "20.00"

    def test_the_sources_add_up_to_the_total_discount(self, shop):
        """⚠️  `manual` is the remainder, so nothing can fall between the sources."""
        report = services.sales_discounts(*today_range())

        assert sum(money(row["amount"]) for row in report["by_source"]) == money(
            report["discount_total"]
        )
        assert sum(money(row["share"]) for row in report["by_source"]) == Decimal("100.00")

    def test_the_shape_is_stable_when_a_source_is_unused(self, product):
        make_sale(product, subtotal="100", manual_discount="10", channel=OrderChannel.POS)

        rows = services.sales_discounts(*today_range())["by_source"]

        assert [row["source"] for row in rows] == list(services.DISCOUNT_SOURCES)
        assert {row["source"]: row["amount"] for row in rows} == {
            "coupon": "0.00",
            "loyalty_points": "0.00",
            "item_promotion": "0.00",
            "manual": "10.00",
        }


# ═══════════════════════════════════════════════════════════
#  By coupon
# ═══════════════════════════════════════════════════════════


class TestByCoupon:
    def test_coupons_are_ranked_by_the_discount_they_gave(self, shop):
        rows = services.sales_discounts(*today_range())["by_coupon"]

        assert [row["code"] for row in rows] == ["SAVE10", "WELCOME"]

        save10 = rows[0]
        assert save10["orders"] == 2  # A and B — not G (cancelled) and not I (outside)
        assert save10["gross"] == "1400.00"
        assert save10["discount"] == "135.00"
        assert save10["discount_percent"] == "9.64"
        # (1000 − 145) + (400 − 40): after *every* discount on those orders, A's item promo too
        assert save10["net"] == "1215.00"
        assert save10["holder_name"] == "Dr. Sara"
        assert save10["name_ar"] == "خصم ١٠"

        assert rows[1]["orders"] == 1
        assert rows[1]["discount"] == "25.00"
        assert rows[1]["net"] == "175.00"

    def test_the_coupon_table_adds_up_to_the_coupon_source(self, shop):
        report = services.sales_discounts(*today_range())
        by_source = {row["source"]: money(row["amount"]) for row in report["by_source"]}

        assert sum(money(row["discount"]) for row in report["by_coupon"]) == by_source["coupon"]
        assert report["coupons_used"] == 2

    def test_loyalty_coupons_are_a_line_not_a_row_each(self, shop, product):
        """
        ⚠️  Each loyalty coupon is single-use; one table row per customer
            redeeming points would bury the campaigns the table is read for.
        """
        loyal_two = make_coupon("PTS-ZZZ999", kind="FIXED", owner=make_user("owner2@test.local"))
        make_sale(product, subtotal="200", coupon=loyal_two, coupon_discount="15")

        report = services.sales_discounts(*today_range())

        assert all(not row["code"].startswith("PTS-") for row in report["by_coupon"])
        assert {row["source"]: row["amount"] for row in report["by_source"]}[
            "loyalty_points"
        ] == "45.00"

    def test_an_order_with_a_stale_code_but_no_redemption_is_not_a_coupon_order(self, product):
        """
        ⚠️  The cart keeps its code after the coupon stops being valid, so the order
            carries the code and got no discount. The redemption is the proof.
        """
        make_sale(product, subtotal="100", stamp_code="STALE")

        report = services.sales_discounts(*today_range())

        assert report["coupon_orders"] == 0
        assert report["by_coupon"] == []

    def test_a_free_shipping_coupon_is_an_order_with_a_zero_discount(self, product):
        """The waived fee is not recorded anywhere, so the report cannot price it."""
        free = make_coupon("FREESHIP", kind="FREE_SHIPPING", value=Decimal("0"))
        make_sale(product, subtotal="300", coupon=free, coupon_discount="0")

        report = services.sales_discounts(*today_range())

        assert report["coupon_orders"] == 1
        assert report["discounted_orders"] == 0
        assert report["by_coupon"][0]["code"] == "FREESHIP"
        assert report["by_coupon"][0]["orders"] == 1
        assert report["by_coupon"][0]["discount"] == "0.00"

    def test_a_coupon_deleted_since_the_sale_still_names_itself(self, product):
        gone = make_coupon("GONE10")
        make_sale(product, subtotal="100", coupon=gone, coupon_discount="10")
        Coupon.objects.filter(pk=gone.pk).update(deleted_at=timezone.now())

        rows = services.sales_discounts(*today_range())["by_coupon"]

        assert [row["code"] for row in rows] == ["GONE10"]

    def test_the_limit_trims_the_rows_but_not_the_count(self, shop):
        report = services.sales_discounts(*today_range(), limit=1)

        assert [row["code"] for row in report["by_coupon"]] == ["SAVE10"]
        assert report["coupons_used"] == 2


# ═══════════════════════════════════════════════════════════
#  Period and series
# ═══════════════════════════════════════════════════════════


class TestPeriod:
    def test_both_ends_of_the_period_are_inclusive(self, product):
        today = timezone.localdate()
        make_sale(product, subtotal="100", manual_discount="10", day=today - timedelta(days=3))
        make_sale(product, subtotal="200", manual_discount="20", day=today)
        make_sale(product, subtotal="400", manual_discount="40", day=today - timedelta(days=4))
        make_sale(product, subtotal="800", manual_discount="80", day=today + timedelta(days=1))

        report = services.sales_discounts(today - timedelta(days=3), today)

        assert report["orders_count"] == 2
        assert report["gross_before_discount"] == "300.00"
        assert report["discount_total"] == "30.00"

    def test_the_period_moves_the_coupon_table_too(self, shop):
        today = timezone.localdate()

        wide = services.sales_discounts(today - timedelta(days=60), today)
        narrow = services.sales_discounts(*today_range())

        wide_save10 = next(row for row in wide["by_coupon"] if row["code"] == "SAVE10")
        narrow_save10 = next(row for row in narrow["by_coupon"] if row["code"] == "SAVE10")
        assert wide_save10["orders"] == 3  # A B + I
        assert narrow_save10["orders"] == 2

    def test_by_day_is_one_row_per_day_with_a_sale(self, product):
        today = timezone.localdate()
        two_ago = today - timedelta(days=2)
        make_sale(product, subtotal="100", manual_discount="10", day=two_ago)
        make_sale(product, subtotal="300", manual_discount="30", day=two_ago)
        make_sale(product, subtotal="500", manual_discount="0", day=today)

        rows = services.sales_discounts(two_ago, today)["by_day"]

        assert rows == [
            {
                "day": two_ago.isoformat(),
                "orders": 2,
                "gross": "400.00",
                "discount": "40.00",
                "net": "360.00",
            },
            {
                "day": today.isoformat(),
                "orders": 1,
                "gross": "500.00",
                "discount": "0.00",
                "net": "500.00",
            },
        ]

    def test_by_day_adds_up_to_the_totals(self, shop):
        report = services.sales_discounts(*today_range())

        assert sum(money(row["gross"]) for row in report["by_day"]) == money(
            report["gross_before_discount"]
        )
        assert sum(money(row["discount"]) for row in report["by_day"]) == money(
            report["discount_total"]
        )

    def test_an_inverted_range_is_refused(self, db):
        today = timezone.localdate()

        with pytest.raises(BusinessError):
            services.sales_discounts(today, today - timedelta(days=5))


class TestEmptyPeriod:
    def test_a_period_with_no_sales_is_zeros_not_an_error(self, db):
        report = services.sales_discounts(*today_range())

        assert report["orders_count"] == 0
        assert report["discounted_orders"] == 0
        assert report["coupon_orders"] == 0
        assert report["coupons_used"] == 0
        assert report["gross_before_discount"] == "0.00"
        assert report["discount_total"] == "0.00"
        # ⚠️  The division-by-zero guard: a quiet month is a normal state
        assert report["discount_percent"] == "0.00"
        assert report["net_after_discount"] == "0.00"
        assert report["unreconciled"] == "0.00"
        assert report["by_coupon"] == []
        assert report["by_day"] == []
        assert [row["amount"] for row in report["by_source"]] == ["0.00"] * 4
        assert [row["share"] for row in report["by_source"]] == ["0.00"] * 4


# ═══════════════════════════════════════════════════════════
#  The endpoint
# ═══════════════════════════════════════════════════════════


class TestEndpoint:
    url = "v1:reporting:sales-discounts"

    def test_the_finance_permission_opens_it(self, viewer, shop):
        today = timezone.localdate().isoformat()

        response = client_for(viewer).get(reverse(self.url), {"start": today, "end": today})

        assert response.status_code == 200
        assert response.data["discount_total"] == "260.00"

    def test_money_is_text_and_counts_are_numbers(self, viewer, shop):
        today = timezone.localdate().isoformat()

        data = client_for(viewer).get(reverse(self.url), {"start": today, "end": today}).data

        for key in (
            "gross_before_discount",
            "discount_total",
            "net_after_discount",
            "invoiced_total",
            "discount_percent",
        ):
            assert isinstance(data[key], str), key
        assert isinstance(data["orders_count"], int)
        assert isinstance(data["by_coupon"][0]["discount"], str)
        assert isinstance(data["by_coupon"][0]["orders"], int)

    def test_the_period_defaults_to_this_month(self, viewer, product):
        make_sale(product, subtotal="100", manual_discount="10", day=timezone.localdate())

        data = client_for(viewer).get(reverse(self.url)).data

        assert data["start"] == timezone.localdate().replace(day=1).isoformat()
        assert data["orders_count"] == 1

    def test_a_customer_is_refused(self, db):
        user = User.objects.create_user(email="nosy-disc@test.local", password=PASSWORD)
        user.is_active = True
        user.save()

        assert client_for(user).get(reverse(self.url)).status_code == 403

    def test_a_plain_admin_without_the_finance_permission_is_refused(self, db):
        """⚠️  Panel access is not enough: the table names the codes handed out and their cost."""
        staff = User.objects.create_user(
            email="plain-disc@test.local", password=PASSWORD, account_type=AccountType.ADMIN
        )
        staff.is_active = True
        staff.save()
        AdminProfile.objects.create(user=staff)
        grant_all_domains(staff)

        assert client_for(staff).get(reverse(self.url)).status_code == 403

    def test_an_anonymous_caller_is_refused(self, db):
        assert APIClient().get(reverse(self.url)).status_code in (401, 403)

    def test_an_inverted_range_is_a_400(self, viewer):
        response = client_for(viewer).get(
            reverse(self.url), {"start": "2026-02-10", "end": "2026-02-01"}
        )
        assert response.status_code == 400

    def test_a_negative_limit_is_a_400(self, viewer):
        assert client_for(viewer).get(reverse(self.url), {"limit": "-1"}).status_code == 400

    def test_an_empty_period_answers_200_with_zeros(self, viewer):
        response = client_for(viewer).get(
            reverse(self.url), {"start": "2000-01-01", "end": "2000-01-31"}
        )

        assert response.status_code == 200
        assert response.data["orders_count"] == 0
        assert response.data["by_coupon"] == []
