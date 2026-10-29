"""
The referral MEMBERS report — "who invited the new customers, and what did they bring?"

⚠️  One hand-built shop whose numbers are worked out here:

        Mona   A  REWARDED  now          orders 180 (200−20) + 100; cancelled 500, refunded 80
                                         and payment-failed 60 are not sales    → 100 points
               B  PENDING   now          —
               C  REJECTED  now          —
               D  REWARDED  60 days ago  order 50                                → 100 points
        Omar   E  PENDING   now          order 80                                → 0 points

        all time : Mona invited 4, qualified 2 (50.0%), orders 3, net 330.00, points 200
                   Omar invited 1, qualified 0, orders 1, net 80.00, points 0
        last 30d : Mona invited 3, qualified 1 (33.33%), orders 2, net 280.00, points 100

    The referee of A also received an entry with the same `referral:A` reference — it must
    not be counted as the member's.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from administration.models import AdminProfile
from core.testing import grant_all_domains
from customers.models import CustomerProfile
from loyalty.models import (
    LoyaltyProgram,
    PointsEntry,
    PointsKind,
    Referral,
    ReferralCode,
    ReferralProgram,
    ReferralStatus,
)
from orders.models import Order, OrderChannel, OrderStatus

pytestmark = pytest.mark.django_db

PASSWORD = "Str0ng-Test-Pass!23"
D = Decimal


def url(name, *args):
    return reverse(f"v1:loyalty:{name}", args=args)


def make_member(email, name="", code=None):
    user = User.objects.create_user(
        email=email,
        password=PASSWORD,
        first_name=name,
        account_type=AccountType.DOCTOR,
    )
    profile = CustomerProfile.objects.create(user=user, display_name_ar=name or email)
    if code:
        ReferralCode.objects.create(user=user, code=code)
    return user, profile


def make_order(profile, subtotal, *, discount="0", status=OrderStatus.DELIVERED, payment="PAID"):
    return Order.objects.create(
        customer=profile,
        channel=OrderChannel.ONLINE,
        status=status,
        payment_status=payment,
        subtotal=D(subtotal),
        discount_total=D(discount),
        grand_total=D(subtotal) - D(discount),
    )


def refer(program, referrer, referee, status, *, days_ago=0, order=None, reason=""):
    referral = Referral.objects.create(
        program=program,
        referrer=referrer,
        referee=referee,
        status=status,
        qualifying_order=order,
        rejection_reason=reason,
        rewarded_at=timezone.now() if status == ReferralStatus.REWARDED else None,
    )
    if days_ago:
        Referral.objects.filter(pk=referral.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )
    return referral


def reward_points(loyalty_program, profile, referral, points):
    return PointsEntry.objects.create(
        customer=profile,
        program=loyalty_program,
        kind=PointsKind.REFERRAL,
        points=points,
        points_remaining=points,
        reference=f"referral:{referral.pk}",
    )


@pytest.fixture
def admin_client(db):
    user = User.objects.create_user(
        email="referral-admin@test.local",
        password=PASSWORD,
        account_type=AccountType.ADMIN,
        is_staff=True,
        is_superuser=True,
    )
    AdminProfile.objects.get_or_create(user=user)
    grant_all_domains(user)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def world(db):
    referral_program = ReferralProgram.objects.create(
        code="ref", name_ar="إحالة", name_en="Refer", is_active=True
    )
    points_program = LoyaltyProgram.objects.create(
        code="pts",
        name_ar="نقاط",
        name_en="Points",
        is_active=True,
        currency_per_point=D("10.00"),
        point_value=D("0.0100"),
    )
    mona, mona_profile = make_member("mona@test.local", "منى", code="MONA10")
    omar, _omar_profile = make_member("omar@test.local", "عمر", code="OMAR10")
    a, a_profile = make_member("a@test.local", "أ")
    b, _ = make_member("b@test.local", "ب")
    c, _ = make_member("c@test.local", "ج")
    d, d_profile = make_member("d@test.local", "د")
    e, e_profile = make_member("e@test.local", "هـ")

    o_a1 = make_order(a_profile, "200", discount="20")
    make_order(a_profile, "100")
    make_order(a_profile, "500", status=OrderStatus.CANCELLED, payment="UNPAID")
    make_order(a_profile, "80", status=OrderStatus.REFUNDED)
    make_order(a_profile, "60", payment="FAILED", status=OrderStatus.PENDING)
    o_d = make_order(d_profile, "50")
    make_order(e_profile, "80")

    ref_a = refer(referral_program, mona, a, ReferralStatus.REWARDED, order=o_a1)
    refer(referral_program, mona, b, ReferralStatus.PENDING)
    refer(
        referral_program,
        mona,
        c,
        ReferralStatus.REJECTED,
        reason="عنوان IP مكرر",
    )
    ref_d = refer(referral_program, mona, d, ReferralStatus.REWARDED, days_ago=60, order=o_d)
    refer(referral_program, omar, e, ReferralStatus.PENDING)

    reward_points(points_program, mona_profile, ref_a, 100)
    reward_points(points_program, a_profile, ref_a, 50)  # the referee's own entry
    reward_points(points_program, mona_profile, ref_d, 100)

    return {"mona": mona, "omar": omar, "ref_a": ref_a, "ref_d": ref_d, "points": points_program}


def members(client, **params):
    response = client.get(url("referral-members"), params)
    assert response.status_code == 200, response.data
    return response.data


def by_email(body):
    return {row["referrer"]["email"]: row for row in body["results"]}


# ═══════════════════════════════════════════════════════════
#  The ranking
# ═══════════════════════════════════════════════════════════


class TestRanking:
    def test_the_figures_match_the_hand_worked_numbers(self, admin_client, world):
        rows = by_email(members(admin_client))

        mona = rows["mona@test.local"]
        assert mona["invited"] == 4
        assert mona["qualified"] == 2
        assert mona["pending"] == 1
        assert mona["rejected"] == 1
        assert mona["referee_orders"] == 3
        assert mona["referee_net_sales"] == "330.00"
        assert mona["points_awarded"] == 200
        assert mona["conversion_rate"] == 50.0
        assert mona["code"] == "MONA10"

        omar = rows["omar@test.local"]
        assert (omar["invited"], omar["qualified"], omar["pending"]) == (1, 0, 1)
        assert omar["referee_orders"] == 1
        assert omar["referee_net_sales"] == "80.00"
        assert omar["points_awarded"] == 0
        assert omar["conversion_rate"] == 0.0

    def test_row_shape(self, admin_client, world):
        row = members(admin_client)["results"][0]

        assert set(row) == {
            "rank",
            "referrer",
            "code",
            "invited",
            "qualified",
            "pending",
            "rejected",
            "referee_orders",
            "referee_net_sales",
            "points_awarded",
            "last_invited_at",
            "conversion_rate",
        }
        assert set(row["referrer"]) == {"id", "name", "email", "account_type"}
        assert row["referrer"]["name"] == "منى"
        assert row["referrer"]["account_type"] == "DOCTOR"

    def test_totals_block(self, admin_client, world):
        totals = members(admin_client)["totals"]

        assert totals == {
            "members": 2,
            "invited": 5,
            "qualified": 2,
            "pending": 2,
            "rejected": 1,
            "referee_orders": 4,
            "referee_net_sales": "410.00",
            "points_awarded": 200,
            "conversion_rate": 40.0,
        }

    def test_ranked_by_qualified_by_default(self, admin_client, world):
        body = members(admin_client)

        assert [row["rank"] for row in body["results"]] == [1, 2]
        assert body["results"][0]["referrer"]["email"] == "mona@test.local"

    def test_the_only_the_referrers_own_points_count(self, admin_client, world):
        """The referee's entry carries the same `referral:A` reference."""
        mona = by_email(members(admin_client))["mona@test.local"]
        assert mona["points_awarded"] == 200  # not 250

    def test_excluded_orders_are_not_sales(self, admin_client, world):
        """Cancelled 500, refunded 80 and payment-failed 60 would add 640 if counted."""
        mona = by_email(members(admin_client))["mona@test.local"]
        assert D(mona["referee_net_sales"]) == D("330.00")

    def test_the_period_is_the_invitation_date(self, admin_client, world):
        since = (timezone.localdate() - timedelta(days=30)).isoformat()
        body = members(admin_client, date_from=since)
        mona = by_email(body)["mona@test.local"]

        assert mona["invited"] == 3
        assert mona["qualified"] == 1
        assert mona["referee_orders"] == 2
        assert mona["referee_net_sales"] == "280.00"
        assert mona["points_awarded"] == 100
        assert mona["conversion_rate"] == 33.33
        assert body["period"]["date_from"] == timezone.localdate() - timedelta(days=30)

        old = members(admin_client, date_to=(timezone.localdate() - timedelta(days=31)).isoformat())
        assert [row["referrer"]["email"] for row in old["results"]] == ["mona@test.local"]
        assert old["results"][0]["invited"] == 1
        assert old["totals"]["members"] == 1

    def test_an_inverted_period_is_refused(self, admin_client, world):
        response = admin_client.get(
            url("referral-members"), {"date_from": "2026-10-10", "date_to": "2026-10-01"}
        )
        assert response.status_code == 400

    def test_search_by_name_email_and_code_leaves_the_totals_alone(self, admin_client, world):
        for term in ("منى", "mona@", "mona10"):
            body = members(admin_client, search=term)
            assert [row["referrer"]["email"] for row in body["results"]] == ["mona@test.local"]
            assert body["totals"]["members"] == 2

        assert members(admin_client, search="nobody")["count"] == 0

    def test_ordering(self, admin_client, world):
        asc = members(admin_client, ordering="referee_net_sales")["results"]
        assert [row["referrer"]["email"] for row in asc] == ["omar@test.local", "mona@test.local"]

        desc = members(admin_client, ordering="-referee_net_sales")["results"]
        assert desc[0]["referrer"]["email"] == "mona@test.local"

        assert (
            admin_client.get(url("referral-members"), {"ordering": "password"}).status_code == 400
        )

    def test_paging_keeps_the_rank(self, admin_client, world):
        first = members(admin_client, limit=1)
        second = members(admin_client, limit=1, page=2)

        assert first["count"] == 2 and first["pages"] == 2
        assert first["results"][0]["rank"] == 1
        assert second["results"][0]["rank"] == 2
        assert second["results"][0]["referrer"]["email"] == "omar@test.local"

    def test_no_referrals_at_all_is_an_empty_report_not_an_error(self, admin_client, db):
        body = members(admin_client)

        assert body["results"] == []
        assert body["totals"]["members"] == 0
        assert body["totals"]["conversion_rate"] == 0.0


# ═══════════════════════════════════════════════════════════
#  One member
# ═══════════════════════════════════════════════════════════


class TestMemberDetail:
    def detail(self, client, user, **params):
        response = client.get(url("referral-member-detail", user.pk), params)
        assert response.status_code == 200, response.data
        return response.data

    def test_summary_and_the_invited_customers(self, admin_client, world):
        body = self.detail(admin_client, world["mona"])

        assert body["referrer"]["email"] == "mona@test.local"
        assert body["code"] == "MONA10"
        assert body["summary"]["invited"] == 4
        assert body["summary"]["points_awarded"] == 200
        assert body["summary"]["referee_net_sales"] == "330.00"
        assert body["count"] == 4

        rows = {row["referee"]["email"]: row for row in body["results"]}
        a = rows["a@test.local"]
        assert a["status"] == "REWARDED"
        assert a["orders"] == 2
        assert a["net_sales"] == "280.00"
        assert a["qualifying_order_number"] == world["ref_a"].qualifying_order.number
        assert a["rewarded_at"] is not None
        assert set(a) == {
            "id",
            "referee",
            "status",
            "invited_at",
            "qualifying_order_number",
            "orders",
            "net_sales",
            "rewarded_at",
            "rejection_reason",
        }
        assert set(a["referee"]) == {"id", "name", "email"}

        assert rows["b@test.local"]["status"] == "PENDING"
        assert rows["b@test.local"]["orders"] == 0
        assert rows["b@test.local"]["net_sales"] == "0.00"
        assert rows["b@test.local"]["qualifying_order_number"] is None
        assert rows["c@test.local"]["status"] == "REJECTED"
        assert rows["c@test.local"]["rejection_reason"] == "عنوان IP مكرر"

    def test_newest_first_and_paginated(self, admin_client, world):
        first = self.detail(admin_client, world["mona"], limit=3)
        second = self.detail(admin_client, world["mona"], limit=3, page=2)

        assert len(first["results"]) == 3 and len(second["results"]) == 1
        assert second["results"][0]["referee"]["email"] == "d@test.local"  # the oldest

    def test_the_period_applies_to_the_invitations(self, admin_client, world):
        since = (timezone.localdate() - timedelta(days=30)).isoformat()
        body = self.detail(admin_client, world["mona"], date_from=since)

        assert body["count"] == 3
        assert body["summary"]["invited"] == 3

    def test_a_member_with_no_invitations_is_zeros(self, admin_client, world):
        stranger, _ = make_member("stranger@test.local")
        body = self.detail(admin_client, stranger)

        assert body["count"] == 0
        assert body["summary"]["invited"] == 0
        assert body["summary"]["conversion_rate"] == 0.0

    def test_unknown_member_is_404(self, admin_client, world):
        import uuid

        assert admin_client.get(url("referral-member-detail", uuid.uuid4())).status_code == 404


# ═══════════════════════════════════════════════════════════
#  Who may read it
# ═══════════════════════════════════════════════════════════


class TestPermissions:
    def test_a_customer_is_refused(self, world):
        client = APIClient()
        client.force_authenticate(user=world["omar"])

        assert client.get(url("referral-members")).status_code == 403
        assert client.get(url("referral-member-detail", world["mona"].pk)).status_code == 403

    def test_staff_without_the_loyalty_permission_is_refused(self, world):
        staff = User.objects.create_user(
            email="plain-staff@test.local",
            password=PASSWORD,
            account_type=AccountType.ADMIN,
            is_staff=True,
        )
        AdminProfile.objects.get_or_create(user=staff)
        grant_all_domains(staff)
        client = APIClient()
        client.force_authenticate(user=staff)

        assert client.get(url("referral-members")).status_code == 403

    def test_anonymous_is_refused(self, world):
        assert APIClient().get(url("referral-members")).status_code in (401, 403)


# ═══════════════════════════════════════════════════════════
#  Cost
# ═══════════════════════════════════════════════════════════


def _count(client, name, *args, **params):
    client.get(url(name, *args), params)  # warm the permission cache
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url(name, *args), params)
    assert response.status_code == 200
    return len(ctx)


class TestQueryCount:
    def test_the_ranking_costs_the_same_for_any_number_of_members(self, admin_client, world):
        referral_program = ReferralProgram.objects.get(code="ref")
        baseline = _count(admin_client, "referral-members")

        for index in range(6):
            member, member_profile = make_member(f"m{index}@test.local", f"عضو{index}", f"M{index}")
            friend, friend_profile = make_member(f"f{index}@test.local")
            order = make_order(friend_profile, "100")
            referral = refer(referral_program, member, friend, ReferralStatus.REWARDED, order=order)
            reward_points(world["points"], member_profile, referral, 10)

        assert _count(admin_client, "referral-members") == baseline

    def test_the_detail_costs_the_same_for_any_number_of_invitees(self, admin_client, world):
        referral_program = ReferralProgram.objects.get(code="ref")
        baseline = _count(admin_client, "referral-member-detail", world["omar"].pk)

        for index in range(6):
            friend, friend_profile = make_member(f"of{index}@test.local")
            make_order(friend_profile, "100")
            refer(referral_program, world["omar"], friend, ReferralStatus.PENDING)

        assert _count(admin_client, "referral-member-detail", world["omar"].pk) == baseline
