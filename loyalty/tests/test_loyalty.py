"""
Loyalty and referral tests.

⚠️  The exit gate for phase 12:

        the switch genuinely stops earning · targeting confines who earns ·
        a return withdraws · redemption does not exceed the cap · points are
        not awarded twice for one order.

    And the greatest dangers it guards: earning continuing after the switch is
    off · someone outside the targeted segment earning · a customer redeeming
    what they do not have · a points coupon being spent by someone who did not
    pay for it.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from administration.models import AdminProfile
from core.testing import grant_all_domains
from core.errors import BusinessError
from customers.models import CustomerProfile, CustomerSegment
from inventory.models import LocationKind, StockLocation
from loyalty import services
from loyalty.models import (
    LoyaltyProgram,
    PointsEntry,
    PointsKind,
    Referral,
    ReferralProgram,
    ReferralStatus,
    TierLevel,
)
from orders.models import Order, OrderChannel, OrderStatus, PaymentStatus

PASSWORD = "Str0ng-Test-Pass!23"


# ═══════════════════════════════════════════════════════════
#  Setup
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def location(db):
    return StockLocation.objects.create(
        code="loy-loc",
        name_ar="مخزن",
        name_en="Store",
        kind=LocationKind.WAREHOUSE,
        is_default=True,
        is_sellable=True,
    )


def make_customer(email: str, account_type=AccountType.STUDENT, segment=CustomerSegment.NEW):
    user = User.objects.create_user(email=email, password=PASSWORD, account_type=account_type)
    return CustomerProfile.objects.create(
        user=user,
        display_name_ar="عميل",
        display_name_en="Customer",
        segment=segment,
    )


@pytest.fixture
def customer(db):
    return make_customer("loyal@example.com")


@pytest.fixture
def program(db):
    return LoyaltyProgram.objects.create(
        code="main",
        name_ar="برنامج النقاط",
        name_en="Points",
        is_active=True,
        currency_per_point=Decimal("10.00"),
        point_value=Decimal("0.0100"),
    )


def make_order(customer, location, total="200.00", tax="0.00", shipping="0.00", **kwargs):
    grand = Decimal(total)
    return Order.objects.create(
        customer=customer,
        channel=kwargs.pop("channel", OrderChannel.ONLINE),
        location=location,
        status=kwargs.pop("status", OrderStatus.PENDING),
        payment_status=PaymentStatus.PAID,
        subtotal=grand - Decimal(tax) - Decimal(shipping),
        tax_total=Decimal(tax),
        shipping_total=Decimal(shipping),
        grand_total=grand,
        completed_at=timezone.now(),
        **kwargs,
    )


# ═══════════════════════════════════════════════════════════
#  The switch — the most dangerous thing in the system
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestTheSwitch:
    """
    ⚠️  A switch checked on one path and forgotten on another is not a switch.

        This class checks all four paths together: earning · pricing ·
        redemption · the referral reward.
    """

    def test_no_program_means_no_points(self, customer, location):
        assert services.award_for_order(make_order(customer, location)) is None
        assert services.balance(customer) == 0

    def test_deactivating_the_program_stops_earning(self, customer, location, program):
        services.award_for_order(make_order(customer, location))
        assert services.balance(customer) == 20

        program.is_active = False
        program.save()

        services.award_for_order(make_order(customer, location))

        # ⚠️  The balance is **not erased** by disabling: points were earned and shown
        #     to the customer, and erasing them makes their balance vanish for no reason.
        assert services.balance(customer) == 20

    def test_deactivating_blocks_redemption_too(self, customer, location, program):
        services.award_for_order(make_order(customer, location, total="1000.00"))
        program.is_active = False
        program.save()

        quote = services.quote_redemption(customer, 10, Decimal("500.00"))
        assert not quote.allowed

        with pytest.raises(BusinessError):
            services.redeem(customer, 10, Decimal("500.00"))

    def test_redemption_can_be_paused_without_stopping_earning(
        self, customer, location, program
    ):
        """
        ⚠️  Two switches, not one: stopping redemption while earning continues
            is a real operational position (reviewing the liability) — and
            merging them would have forced the admin to disable the whole system.
        """
        program.redemption_enabled = False
        program.save()

        services.award_for_order(make_order(customer, location, total="1000.00"))
        assert services.balance(customer) == 100

        assert not services.quote_redemption(customer, 10, Decimal("500.00")).allowed


@pytest.mark.django_db
class TestTargeting:
    """⚠️  Targeting is what the admin asked for: a specific segment or everyone."""

    def test_empty_targeting_covers_everyone(self, location, program):
        for account_type in (AccountType.STUDENT, AccountType.PHARMACY, AccountType.DOCTOR):
            customer = make_customer(f"{account_type}@example.com", account_type)
            services.award_for_order(make_order(customer, location))
            assert services.balance(customer) == 20

    def test_account_type_targeting_excludes_others(self, location, program):
        program.account_types = [AccountType.PHARMACY]
        program.save()

        pharmacy = make_customer("ph@example.com", AccountType.PHARMACY)
        student = make_customer("st@example.com", AccountType.STUDENT)

        services.award_for_order(make_order(pharmacy, location))
        services.award_for_order(make_order(student, location))

        assert services.balance(pharmacy) == 20
        assert services.balance(student) == 0

    def test_targeting_may_list_several_types(self, location, program):
        program.account_types = [AccountType.STUDENT, AccountType.DOCTOR]
        program.save()

        student = make_customer("s2@example.com", AccountType.STUDENT)
        doctor = make_customer("d2@example.com", AccountType.DOCTOR)
        pharmacy = make_customer("p2@example.com", AccountType.PHARMACY)

        for row in (student, doctor, pharmacy):
            services.award_for_order(make_order(row, location))

        assert services.balance(student) == 20
        assert services.balance(doctor) == 20
        assert services.balance(pharmacy) == 0

    def test_segment_and_account_type_apply_together(self, location, program):
        """⚠️  Both conditions **together**, not either: "featured pharmacies", not
            "every pharmacy or every featured customer"."""
        program.account_types = [AccountType.PHARMACY]
        program.customer_segments = [CustomerSegment.VIP]
        program.save()

        vip = make_customer("vip@example.com", AccountType.PHARMACY, CustomerSegment.VIP)
        plain = make_customer("new@example.com", AccountType.PHARMACY, CustomerSegment.NEW)

        services.award_for_order(make_order(vip, location))
        services.award_for_order(make_order(plain, location))

        assert services.balance(vip) == 20
        assert services.balance(plain) == 0

    def test_two_programs_pick_the_covering_one(self, location, program):
        program.account_types = [AccountType.STUDENT]
        program.currency_per_point = Decimal("10.00")
        program.save()

        LoyaltyProgram.objects.create(
            code="pharmacy",
            name_ar="برنامج الصيدليات",
            name_en="Pharmacies",
            is_active=True,
            account_types=[AccountType.PHARMACY],
            currency_per_point=Decimal("5.00"),
        )

        pharmacy = make_customer("ph3@example.com", AccountType.PHARMACY)
        services.award_for_order(make_order(pharmacy, location))

        # 200 ÷ 5 = 40 — from the pharmacies programme, not the students one
        assert services.balance(pharmacy) == 40


# ═══════════════════════════════════════════════════════════
#  Earning
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEarning:
    def test_tax_and_shipping_are_excluded_by_default(self, customer, location, program):
        """⚠️  Tax is collected for the state and shipping is paid to the carrier —
            and the customer is not rewarded on what we did not profit from."""
        services.award_for_order(
            make_order(customer, location, total="200.00", tax="28.00", shipping="22.00")
        )

        # (200 − 28 − 22) ÷ 10 = 15
        assert services.balance(customer) == 15

    def test_tax_can_be_included_by_configuration(self, customer, location, program):
        program.earns_on_tax = True
        program.earns_on_shipping = True
        program.save()

        services.award_for_order(
            make_order(customer, location, total="200.00", tax="28.00", shipping="22.00")
        )
        assert services.balance(customer) == 20

    def test_minimum_order_amount_blocks_small_orders(self, customer, location, program):
        program.min_order_amount = Decimal("300.00")
        program.save()

        assert services.award_for_order(make_order(customer, location, total="200.00")) is None
        assert services.balance(customer) == 0

    def test_the_same_order_never_earns_twice(self, customer, location, program):
        order = make_order(customer, location)

        services.award_for_order(order)
        services.award_for_order(order)
        services.award_for_order(order)

        assert PointsEntry.objects.filter(order=order, kind=PointsKind.EARN).count() == 1
        assert services.balance(customer) == 20

    def test_tier_multiplier_raises_the_award(self, customer, location, program):
        TierLevel.objects.create(
            program=program,
            code="gold",
            name_ar="ذهبي",
            name_en="Gold",
            threshold=Decimal("1000.00"),
            multiplier=Decimal("2.00"),
        )
        customer.total_spent = Decimal("5000.00")
        customer.save(update_fields=["total_spent"])

        services.award_for_order(make_order(customer, location))
        assert services.balance(customer) == 40

    def test_a_counter_sale_without_a_customer_is_ignored(self, location, program):
        order = Order.objects.create(
            channel=OrderChannel.POS,
            location=location,
            status=OrderStatus.DELIVERED,
            payment_status=PaymentStatus.PAID,
            subtotal=Decimal("100.00"),
            grand_total=Decimal("100.00"),
            completed_at=timezone.now(),
        )
        assert services.award_for_order(order) is None


@pytest.mark.django_db
class TestRefundReversal:
    def test_a_refund_pulls_the_points_back(self, customer, location, program):
        """⚠️  Without it: buy · earn · return · and keep the points."""
        order = make_order(customer, location)
        services.award_for_order(order)
        assert services.balance(customer) == 20

        services.reverse_for_order(order)
        assert services.balance(customer) == 0

    def test_reversal_never_drives_the_balance_negative(self, customer, location, program):
        order = make_order(customer, location, total="1000.00")
        services.award_for_order(order)

        services.redeem(customer, 80, Decimal("1000.00"))
        assert services.balance(customer) == 20

        services.reverse_for_order(order)

        # ⚠️  80 points already redeemed: the withdrawal stops at the balance and
        #     does not invent a debt in points.
        assert services.balance(customer) == 0

    def test_reversal_can_be_switched_off(self, customer, location, program):
        program.reverse_on_refund = False
        program.save()

        order = make_order(customer, location)
        services.award_for_order(order)
        services.reverse_for_order(order)

        assert services.balance(customer) == 20

    def test_reversal_is_recorded_once(self, customer, location, program):
        order = make_order(customer, location)
        services.award_for_order(order)

        services.reverse_for_order(order)
        services.reverse_for_order(order)

        assert PointsEntry.objects.filter(order=order, kind=PointsKind.REVERSE).count() == 1


# ═══════════════════════════════════════════════════════════
#  Redemption
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRedemption:
    def test_redeeming_produces_a_personal_coupon(self, customer, location, program):
        services.award_for_order(make_order(customer, location, total="1000.00"))

        result = services.redeem(customer, 50, Decimal("1000.00"))
        coupon = result["coupon"]

        assert coupon.value == Decimal("0.50")
        assert coupon.owner_id == customer.user_id
        assert services.balance(customer) == 50

    def test_a_redeemed_coupon_is_useless_to_anyone_else(self, customer, location, program):
        """
        ⚠️  `usage_limit=1` limits the count, not the person.

            With no owner it is enough to photograph the code and send it for
            someone else to spend it — on points that were its owner's.
        """
        from promotions import services as promo

        services.award_for_order(make_order(customer, location, total="1000.00"))
        coupon = services.redeem(customer, 50, Decimal("1000.00"))["coupon"]

        stranger = make_customer("thief@example.com")

        stranger_result = promo.validate(
            coupon.code, stranger.user, [], subtotal=Decimal("100.00")
        )
        owner_result = promo.validate(
            coupon.code, customer.user, [], subtotal=Decimal("100.00")
        )

        # ⚠️  A stranger is answered with "not found", not "not yours": distinguishing
        #     the two responses turns the field into a discovery tool.
        assert stranger_result.reason is promo.RejectionReason.NOT_FOUND

        # And the owner passes the ownership gate — stopping only at an empty cart
        assert owner_result.reason is promo.RejectionReason.NO_ELIGIBLE_ITEMS

    def test_redemption_is_capped_by_a_percentage_of_the_order(
        self, customer, location, program
    ):
        """⚠️  Without a cap a whole order is paid in points — and points do not
            pay suppliers' invoices."""
        program.max_redemption_percent = Decimal("50.00")
        program.point_value = Decimal("1.0000")
        program.save()

        services.adjust_points(customer, 500, reason="اختبار")

        quote = services.quote_redemption(customer, 300, Decimal("400.00"))
        assert not quote.allowed
        assert quote.max_points == 200

    def test_you_cannot_redeem_more_than_you_have(self, customer, location, program):
        services.award_for_order(make_order(customer, location))

        with pytest.raises(BusinessError):
            services.redeem(customer, 500, Decimal("10000.00"))

        assert services.balance(customer) == 20

    def test_oldest_expiring_batch_is_consumed_first(self, customer, location, program):
        """⚠️  Consuming the newest first makes the oldest always expire unused —
            which reads as cheating rather than policy."""
        old = PointsEntry.objects.create(
            customer=customer,
            program=program,
            kind=PointsKind.EARN,
            points=30,
            points_remaining=30,
            expires_on=timezone.localdate() + timedelta(days=5),
        )
        new = PointsEntry.objects.create(
            customer=customer,
            program=program,
            kind=PointsKind.EARN,
            points=30,
            points_remaining=30,
            expires_on=timezone.localdate() + timedelta(days=300),
        )

        services.redeem(customer, 20, Decimal("10000.00"))

        old.refresh_from_db()
        new.refresh_from_db()
        assert old.points_remaining == 10
        assert new.points_remaining == 30


@pytest.mark.django_db
class TestExpiry:
    def test_expired_points_leave_the_usable_balance(self, customer, program):
        PointsEntry.objects.create(
            customer=customer,
            program=program,
            kind=PointsKind.EARN,
            points=40,
            points_remaining=40,
            expires_on=timezone.localdate() - timedelta(days=1),
        )

        assert services.usable_points(customer) == 0

    def test_expiry_is_recorded_not_deleted(self, customer, program):
        PointsEntry.objects.create(
            customer=customer,
            program=program,
            kind=PointsKind.EARN,
            points=40,
            points_remaining=40,
            expires_on=timezone.localdate() - timedelta(days=1),
        )

        result = services.expire_points()

        assert result == {"batches": 1, "points": 40}
        assert PointsEntry.objects.filter(kind=PointsKind.EXPIRE).count() == 1
        assert services.balance(customer) == 0

    def test_points_without_expiry_survive(self, customer, program):
        program.expiry_months = 0
        program.save()

        services.adjust_points(customer, 40, reason="بلا انتهاء")
        services.expire_points()

        assert services.usable_points(customer) == 40


# ═══════════════════════════════════════════════════════════
#  Manual adjustment
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAdjustment:
    def test_a_reason_is_required(self, customer, program):
        with pytest.raises(BusinessError):
            services.adjust_points(customer, 50, reason="  ")

    def test_a_deduction_stops_at_zero(self, customer, program):
        services.adjust_points(customer, 30, reason="هدية")
        entry = services.adjust_points(customer, -100, reason="تصحيح")

        assert entry.points == 30
        assert services.balance(customer) == 0

    def test_entries_are_append_only(self, customer, program):
        entry = services.adjust_points(customer, 30, reason="هدية")
        entry.points = 500

        with pytest.raises(ValueError):
            entry.save()


# ═══════════════════════════════════════════════════════════
#  Referrals
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def referral_program(db):
    return ReferralProgram.objects.create(
        code="ref",
        name_ar="أحضر صديقًا",
        name_en="Refer a friend",
        is_active=True,
        referrer_points=100,
        referee_points=50,
    )


@pytest.mark.django_db
class TestReferral:
    def test_you_cannot_refer_yourself(self, customer, referral_program):
        code = services.ensure_referral_code(customer.user)

        with pytest.raises(BusinessError):
            services.register_referral(customer.user, code.code)

    def test_an_account_is_referred_only_once(self, customer, referral_program):
        code = services.ensure_referral_code(customer.user)
        friend = make_customer("friend@example.com")

        services.register_referral(friend.user, code.code)

        with pytest.raises(BusinessError):
            services.register_referral(friend.user, code.code)

    def test_the_reward_waits_for_the_first_completed_order(
        self, customer, location, program, referral_program
    ):
        """⚠️  Paying at registration turns the system into a farm of fake
            accounts: every new email is points."""
        code = services.ensure_referral_code(customer.user)
        friend = make_customer("buyer@example.com")

        services.register_referral(friend.user, code.code)

        assert services.balance(customer) == 0
        assert services.balance(friend) == 0

        services.reward_referral(make_order(friend, location))

        assert services.balance(customer) == 100
        assert services.balance(friend) == 50

    def test_the_reward_is_paid_once(self, customer, location, program, referral_program):
        code = services.ensure_referral_code(customer.user)
        friend = make_customer("twice@example.com")
        services.register_referral(friend.user, code.code)

        services.reward_referral(make_order(friend, location))
        services.reward_referral(make_order(friend, location))

        assert services.balance(customer) == 100

    def test_each_side_is_checked_against_its_own_program(
        self, customer, location, referral_program
    ):
        """
        ⚠️  Awarding both sides from the referrer's programme punched a hole in
            the targeting: a pharmacy inside the programme refers a student
            outside it, so they earn from a programme that does not cover them.
        """
        LoyaltyProgram.objects.create(
            code="pharmacies-only",
            name_ar="الصيدليات",
            name_en="Pharmacies",
            is_active=True,
            account_types=[AccountType.PHARMACY],
        )

        referrer = make_customer("pharm@example.com", AccountType.PHARMACY)
        code = services.ensure_referral_code(referrer.user)

        student = make_customer("out@example.com", AccountType.STUDENT)
        services.register_referral(student.user, code.code)
        services.reward_referral(make_order(student, location))

        assert services.balance(referrer) == 100
        assert services.balance(student) == 0

    def test_the_referrer_cap_is_enforced(self, customer, location, program, referral_program):
        referral_program.max_referrals_per_user = 1
        referral_program.save()

        code = services.ensure_referral_code(customer.user)

        first = make_customer("one@example.com")
        services.register_referral(first.user, code.code)
        services.reward_referral(make_order(first, location))

        second = make_customer("two@example.com")
        with pytest.raises(BusinessError):
            services.register_referral(second.user, code.code)

    def test_a_referral_below_the_minimum_stays_pending(
        self, customer, location, program, referral_program
    ):
        referral_program.min_order_amount = Decimal("500.00")
        referral_program.save()

        code = services.ensure_referral_code(customer.user)
        friend = make_customer("small@example.com")
        services.register_referral(friend.user, code.code)

        services.reward_referral(make_order(friend, location, total="100.00"))

        assert Referral.objects.get(referee=friend.user).status == ReferralStatus.PENDING
        assert services.balance(customer) == 0

    def test_the_code_is_stable(self, customer, referral_program):
        assert services.ensure_referral_code(customer.user).code == (
            services.ensure_referral_code(customer.user).code
        )


# ═══════════════════════════════════════════════════════════
#  The listeners — the actual wiring to orders
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestListeners:
    def test_a_counter_sale_earns_without_the_completion_event(
        self, customer, location, program
    ):
        """
        ⚠️  Point of sale creates the order in its final state with no state
            machine, so no `order_completed` is emitted. Relying on the signal
            means the branch's customer earns nothing.
        """
        make_order(customer, location, channel=OrderChannel.POS, status=OrderStatus.DELIVERED)

        assert services.balance(customer) == 20

    def test_marking_an_order_refunded_pulls_the_points(self, customer, location, program):
        order = make_order(
            customer, location, channel=OrderChannel.POS, status=OrderStatus.DELIVERED
        )
        assert services.balance(customer) == 20

        order.status = OrderStatus.REFUNDED
        order.save()

        assert services.balance(customer) == 0


# ═══════════════════════════════════════════════════════════
#  Endpoints
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def admin_client(db):
    user = User.objects.create_user(
        email="loyalty-admin@example.com",
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


@pytest.mark.django_db
class TestAPI:
    def test_a_customer_outside_the_program_gets_a_calm_disabled(self, customer, program):
        program.account_types = [AccountType.PHARMACY]
        program.save()

        client = APIClient()
        client.force_authenticate(user=customer.user)

        response = client.get(reverse("v1:loyalty:me"))

        assert response.status_code == 200
        assert response.data == {"enabled": False}

    def test_the_summary_exposes_the_balance_and_tier(self, customer, location, program):
        TierLevel.objects.create(
            program=program,
            code="silver",
            name_ar="فضي",
            name_en="Silver",
            threshold=Decimal("500.00"),
        )
        services.award_for_order(make_order(customer, location))

        client = APIClient()
        client.force_authenticate(user=customer.user)

        data = client.get(reverse("v1:loyalty:me")).data

        assert data["enabled"] is True
        assert data["balance"] == 20
        assert data["next_tier"]["name_ar"] == "فضي"
        # ⚠️  Amounts as strings (ADR-31)
        assert isinstance(data["program"]["point_value"], str)

    def test_a_customer_never_sees_another_ledger(self, customer, location, program):
        other = make_customer("other@example.com")
        services.award_for_order(make_order(other, location))
        services.award_for_order(make_order(customer, location))

        client = APIClient()
        client.force_authenticate(user=customer.user)

        data = client.get(reverse("v1:loyalty:my-points")).data
        assert data["count"] == 1

    def test_configuring_the_switch_from_the_admin(self, admin_client, program):
        url = reverse("v1:loyalty:program-detail", args=[program.pk])

        response = admin_client.patch(
            url,
            {"is_active": False, "account_types": [AccountType.PHARMACY]},
            format="json",
        )

        assert response.status_code == 200
        program.refresh_from_db()
        assert program.is_active is False
        assert program.account_types == [AccountType.PHARMACY]

    def test_an_unknown_account_type_is_rejected(self, admin_client, program):
        """⚠️  A mistyped value matches nobody: the programme looks enabled and
            nobody earns from it — a silent fault."""
        response = admin_client.patch(
            reverse("v1:loyalty:program-detail", args=[program.pk]),
            {"account_types": ["طالب"]},
            format="json",
        )

        assert response.status_code == 400

    def test_a_plain_customer_cannot_touch_the_settings(self, customer, program):
        client = APIClient()
        client.force_authenticate(user=customer.user)

        response = client.patch(
            reverse("v1:loyalty:program-detail", args=[program.pk]),
            {"is_active": False},
            format="json",
        )

        assert response.status_code in (403, 404)
        program.refresh_from_db()
        assert program.is_active is True

    def test_the_overview_prices_the_liability(self, admin_client, customer, location, program):
        services.award_for_order(make_order(customer, location, total="1000.00"))

        data = admin_client.get(reverse("v1:loyalty:overview")).data

        assert data["liability"]["points"] == 100
        assert data["liability"]["value"] == "1.00"

    def test_everything_the_admin_needs_is_creatable_from_the_api(self, admin_client):
        """
        ⚠️  **What cannot be created from the frontend is created from
            `manage.py` — that is, not created at all.**

            A screen that edits and does not create makes the first second
            programme need a developer. This test covers the path end to end.
        """
        created = admin_client.post(
            reverse("v1:loyalty:programs"),
            {
                "code": "vip-only",
                "name_ar": "برنامج المميّزين",
                "name_en": "VIP",
                "is_active": True,
                "customer_segments": [CustomerSegment.VIP],
                "currency_per_point": "20.00",
                "point_value": "0.2000",
                "max_redemption_percent": "25.00",
            },
            format="json",
        )
        assert created.status_code == 201, created.data
        program_id = created.data["id"]

        tier = admin_client.post(
            reverse("v1:loyalty:tiers"),
            {
                "program": program_id,
                "code": "platinum",
                "name_ar": "بلاتيني",
                "name_en": "Platinum",
                "threshold": "50000.00",
                "multiplier": "2.00",
            },
            format="json",
        )
        assert tier.status_code == 201, tier.data

        referral = admin_client.post(
            reverse("v1:loyalty:referral-programs"),
            {
                "code": "launch",
                "name_ar": "حملة الإطلاق",
                "name_en": "Launch",
                "is_active": True,
                "referrer_points": 500,
                "referee_points": 250,
                "max_referrals_per_user": 5,
                "min_order_amount": "200.00",
            },
            format="json",
        )
        assert referral.status_code == 201, referral.data

        # And deletion is available while the programme has no history
        assert (
            admin_client.delete(
                reverse("v1:loyalty:tier-detail", args=[tier.data["id"]])
            ).status_code
            == 204
        )
        assert (
            admin_client.delete(
                reverse("v1:loyalty:program-detail", args=[program_id])
            ).status_code
            == 204
        )

    def test_a_program_with_history_refuses_deletion(
        self, admin_client, customer, location, program
    ):
        """
        ⚠️  Deletion leaves movements pointing at a programme that does not
            exist, so an old customer's statement cannot be read. Disabling does
            what the admin actually wants.
        """
        services.award_for_order(make_order(customer, location))

        response = admin_client.delete(reverse("v1:loyalty:program-detail", args=[program.pk]))

        assert response.status_code == 409
        assert LoyaltyProgram.objects.filter(pk=program.pk).exists()

    def test_customer_lookup_shows_the_balance_before_adjusting(
        self, admin_client, customer, location, program
    ):
        """⚠️  Withdrawing 100 from a balance of 30 is silently clamped: the balance
            must be seen before the number is written, not after it is sent."""
        services.award_for_order(make_order(customer, location))

        data = admin_client.get(
            reverse("v1:loyalty:customer-lookup"), {"search": customer.customer_number}
        ).data

        assert len(data) == 1
        assert data[0]["balance"] == 20
        assert data[0]["covered"] is True

    def test_a_one_letter_search_returns_nothing(self, admin_client, customer):
        """⚠️  A single character returns every customer — a list leak, not a search."""
        assert admin_client.get(reverse("v1:loyalty:customer-lookup"), {"search": "ع"}).data == []

    def test_adjusting_points_from_the_admin(self, admin_client, customer, program):
        response = admin_client.post(
            reverse("v1:loyalty:adjust-points", args=[customer.pk]),
            {"points": 75, "reason": "تعويض شكوى"},
            format="json",
        )

        assert response.status_code == 201
        assert response.data["balance"] == 75
        assert response.data["entry"]["note"] == "تعويض شكوى"

    def test_an_adjustment_without_a_reason_is_refused(self, admin_client, customer, program):
        response = admin_client.post(
            reverse("v1:loyalty:adjust-points", args=[customer.pk]),
            {"points": 75, "reason": ""},
            format="json",
        )

        assert response.status_code == 400
        assert services.balance(customer) == 0

    def test_expiring_points_on_demand(self, admin_client, customer, program):
        PointsEntry.objects.create(
            customer=customer,
            program=program,
            kind=PointsKind.EARN,
            points=40,
            points_remaining=40,
            expires_on=timezone.localdate() - timedelta(days=1),
        )

        response = admin_client.post(reverse("v1:loyalty:expire"))

        assert response.status_code == 200
        assert response.data == {"batches": 1, "points": 40}
        assert services.usable_points(customer) == 0

    def test_the_ledger_filters_by_kind_and_customer(
        self, admin_client, customer, location, program
    ):
        other = make_customer("ledger-other@example.com")
        services.award_for_order(make_order(customer, location))
        services.award_for_order(make_order(other, location))
        services.adjust_points(customer, 10, reason="هدية")

        by_customer = admin_client.get(
            reverse("v1:loyalty:admin-points"), {"customer": str(customer.pk)}
        ).data
        assert by_customer["count"] == 2

        by_kind = admin_client.get(
            reverse("v1:loyalty:admin-points"),
            {"customer": str(customer.pk), "kind": PointsKind.ADJUSTMENT},
        ).data
        assert by_kind["count"] == 1

    def test_targeting_options_come_from_the_source(self, admin_client):
        data = admin_client.get(reverse("v1:loyalty:targeting")).data

        values = [row["value"] for row in data["account_types"]]
        assert AccountType.PHARMACY in values
        assert data["customer_segments"]
