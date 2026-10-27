"""
The life of a guest order after it is placed.

    * unconfirmed orders are cancelled automatically, stock released
    * an order shipped after its stock reservation lapsed still deducts stock
    * after the owner *verifies* their email, earlier guest orders are claimed
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.apps import apps
from django.core.management import call_command
from django.db.models.signals import post_save
from django.utils import timezone

from accounts import services as account_services
from accounts.models import AccountType, TokenPurpose, User
from core.errors import BusinessError
from core.models.audit import AuditLog
from customers.models import CustomerProfile
from inventory import services as inventory_services
from orders import guest, services
from orders.models import Order, OrderChannel, OrderStatus
from orders.tests.test_guest_checkout import (  # noqa: F401  (fixtures)
    FORM,
    SESSION,
    available,
    category,
    cod,
    location,
    place,
    policies,
    product,
    shipping,
    tax_class,
    world,
)

PASSWORD = "Str0ng-Test-Pass!23"


def guest_order(world, n=0, **overrides):
    session = f"ee1c2b0e-8a52-4a0e-9f43-5b2e0c6a{n:04d}"
    overrides.setdefault("email", f"buyer{n}@example.com")
    overrides.setdefault("phone", f"010123456{n:02d}")
    _, response = place(world, session=session, **overrides)
    assert response.status_code == 201, response.data
    return Order.objects.get(number=response.data["order_number"])


def age(order, hours):
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(hours=hours))


# ═══════════════════════════════════════════════════════════
#  Auto-cancelling unconfirmed orders
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAutoCancel:
    def test_a_stale_unconfirmed_guest_order_is_cancelled_and_its_stock_released(
        self, world, settings
    ):
        settings.GUEST_ORDER_AUTO_CANCEL_HOURS = 48
        before = available(world)
        order = guest_order(world)
        assert available(world) == before - 1
        age(order, 49)

        assert guest.cancel_unconfirmed() == 1

        order.refresh_from_db()
        assert order.status == OrderStatus.CANCELLED
        assert "48" in order.cancellation_reason
        assert available(world) == before
        assert not inventory_services.active_reservations_for("order", order.pk)
        assert order.status_history.filter(to_status="CANCELLED").exists()

    def test_a_recent_order_is_left_alone(self, world):
        order = guest_order(world)
        age(order, 47)

        assert guest.cancel_unconfirmed() == 0
        order.refresh_from_db()
        assert order.status == OrderStatus.PENDING

    def test_a_confirmed_order_is_never_auto_cancelled(self, world):
        """The owner phoned and confirmed it — however old, it is theirs to manage."""
        order = guest_order(world)
        services.transition(order, OrderStatus.CONFIRMED)
        age(order, 500)

        assert guest.cancel_unconfirmed() == 0

    def test_only_guest_orders_are_touched(self, world, location):
        """A member's pending order and a counter sale are not this job's business."""
        member = User.objects.create_user(email="m@test.local", password=PASSWORD)
        profile = CustomerProfile.objects.create(user=member)
        member_order = Order.objects.create(customer=profile, channel=OrderChannel.ONLINE)
        counter = Order.objects.create(customer=None, channel=OrderChannel.PHONE)
        for stale in (member_order, counter):
            age(stale, 500)

        assert guest.cancel_unconfirmed() == 0
        member_order.refresh_from_db()
        counter.refresh_from_db()
        assert member_order.status == counter.status == OrderStatus.PENDING

    def test_zero_turns_it_off(self, world, settings):
        settings.GUEST_ORDER_AUTO_CANCEL_HOURS = 0
        order = guest_order(world)
        age(order, 10_000)

        assert guest.cancel_unconfirmed() == 0
        order.refresh_from_db()
        assert order.status == OrderStatus.PENDING

    def test_the_window_is_configurable(self, world, settings):
        settings.GUEST_ORDER_AUTO_CANCEL_HOURS = 6
        order = guest_order(world)
        age(order, 7)

        assert guest.cancel_unconfirmed() == 1

    def test_the_caller_can_override_the_window(self, world, settings):
        settings.GUEST_ORDER_AUTO_CANCEL_HOURS = 0
        order = guest_order(world)
        age(order, 5)

        assert guest.cancel_unconfirmed(hours=4) == 1

    def test_one_failing_order_does_not_stop_the_rest(self, world):
        first = guest_order(world, 0)
        second = guest_order(world, 1)
        for order in (first, second):
            age(order, 100)

        real_cancel = services.cancel

        def flaky(order, **kwargs):
            if order.pk == first.pk:
                raise BusinessError("CONFLICT")
            return real_cancel(order, **kwargs)

        with patch.object(services, "cancel", flaky):
            assert guest.cancel_unconfirmed() == 1

        first.refresh_from_db()
        second.refresh_from_db()
        assert first.status == OrderStatus.PENDING
        assert second.status == OrderStatus.CANCELLED

    def test_it_is_scheduled_in_the_periodic_runner(self, world, capsys):
        from ops.management.commands.run_periodic import JOBS

        group, _label, function = JOBS["cancel_unconfirmed_guest_orders"]
        assert group == "orders"
        assert function is guest.cancel_unconfirmed

        order = guest_order(world)
        age(order, 100)
        call_command("run_periodic", "--job", "cancel_unconfirmed_guest_orders")

        order.refresh_from_db()
        assert order.status == OrderStatus.CANCELLED

    def test_the_orders_group_selects_the_job(self):
        from ops.management.commands.run_periodic import Command

        selected = Command()._select("orders")
        assert list(selected) == ["cancel_unconfirmed_guest_orders"]


# ═══════════════════════════════════════════════════════════
#  Shipping after the reservation lapsed
# ═══════════════════════════════════════════════════════════


def lapse(order):
    """Make the order's reservations expire and let the periodic job release them."""
    reservation_model = apps.get_model("inventory", "StockReservation")
    reservation_model.objects.filter(reference_id=str(order.pk)).update(
        expires_at=timezone.now() - timedelta(minutes=1)
    )
    return inventory_services.release_expired_reservations()


@pytest.mark.django_db
class TestShippingAfterTheReservationLapsed:
    """
    ⚠️  The gap guest COD exposes: `commit_for_reference` only commits ACTIVE
        reservations, so an order the owner confirms the next day used to ship
        without a stock deduction (and its units had been resold meanwhile).
    """

    def test_shipping_deducts_stock_even_if_the_hold_expired(self, world):
        start = available(world)
        order = guest_order(world)
        assert available(world) == start - 1

        assert lapse(order) == 1
        assert available(world) == start, "the hold really was released"

        services.transition(order, OrderStatus.CONFIRMED)
        services.transition(order, OrderStatus.PROCESSING)
        services.transition(order, OrderStatus.SHIPPED)

        assert available(world) == start - 1, "the parcel left, so the stock must have moved"
        assert not inventory_services.active_reservations_for("order", order.pk)
        reservation_model = apps.get_model("inventory", "StockReservation")
        assert reservation_model.objects.filter(
            reference_id=str(order.pk), status="COMMITTED"
        ).exists()

    def test_shipping_is_refused_if_the_goods_were_sold_meanwhile(self, world, location):
        start = available(world)
        order = guest_order(world)
        lapse(order)
        services.transition(order, OrderStatus.CONFIRMED)
        services.transition(order, OrderStatus.PROCESSING)

        # Someone else takes everything that is left
        inventory_services.sell_immediately(world, available(world), location=location)

        with pytest.raises(BusinessError) as caught:
            services.transition(order, OrderStatus.SHIPPED)

        assert caught.value.code == "INSUFFICIENT_STOCK"
        order.refresh_from_db()
        assert order.status == OrderStatus.PROCESSING, "refused: the transition rolled back"
        assert start >= 1

    def test_a_normal_shipment_is_unchanged(self, world):
        start = available(world)
        order = guest_order(world)
        services.transition(order, OrderStatus.CONFIRMED)
        services.transition(order, OrderStatus.PROCESSING)
        services.transition(order, OrderStatus.SHIPPED)

        assert available(world) == start - 1

    def test_only_the_shortfall_is_reserved_again(self, world):
        """A partly lapsed order must not be double-reserved."""
        start = available(world)
        _, response = place(world, quantity=3, session="ff1c2b0e-8a52-4a0e-9f43-5b2e0c6a0001")
        order = Order.objects.get(number=response.data["order_number"])

        assert services._restore_lapsed_reservations(order) == 0  # nothing missing
        assert available(world) == start - 3


# ═══════════════════════════════════════════════════════════
#  Claiming guest orders after email verification
# ═══════════════════════════════════════════════════════════


def make_user(email, *, verified=False, account_type=AccountType.STUDENT):
    user = User.objects.create_user(email=email, password=PASSWORD, account_type=account_type)
    user.is_active = True
    if verified:
        user.email_verified_at = timezone.now()
    user.save()
    return user


def verify(user, django_capture_on_commit_callbacks):
    """Run the real verification flow, with its `on_commit` announcement."""
    _record, raw = account_services.issue_token(user, TokenPurpose.EMAIL_VERIFICATION)
    with django_capture_on_commit_callbacks(execute=True):
        account_services.verify_email(raw)
    user.refresh_from_db()


@pytest.mark.django_db
class TestClaimAfterVerification:
    def test_verifying_the_email_claims_the_guest_orders_ignoring_case(
        self, world, django_capture_on_commit_callbacks
    ):
        first = guest_order(world, 0, email="Buyer.One@Example.com")
        second = guest_order(world, 1, email="buyer.one@EXAMPLE.COM")
        user = make_user("buyer.one@example.com")

        verify(user, django_capture_on_commit_callbacks)

        first.refresh_from_db()
        second.refresh_from_db()
        profile = CustomerProfile.objects.get(user=user)
        assert first.customer == second.customer == profile
        # The contact email stays: the emailed tracking link keeps working
        assert first.contact_email == "buyer.one@example.com"
        assert not first.is_guest, "claimed, so no longer a guest order"

    def test_nothing_is_claimed_before_verification(self, world):
        order = guest_order(world, 0, email="early@example.com")
        user = make_user("early@example.com", verified=False)

        assert guest.claim_orders(user) == 0

        order.refresh_from_db()
        assert order.customer is None

    def test_registering_alone_claims_nothing(self, world):
        """An unverified address proves nothing — anyone can register with someone else's email."""
        order = guest_order(world, 0, email="victim@example.com")
        make_user("victim@example.com")  # the "attacker" registers; never verifies

        order.refresh_from_db()
        assert order.customer is None

    def test_only_guest_orders_with_a_matching_email_are_claimed(
        self, world, django_capture_on_commit_callbacks
    ):
        mine = guest_order(world, 0, email="me@example.com")
        someone_elses = guest_order(world, 1, email="other@example.com")

        owner = make_user("owner@example.com")
        owned = Order.objects.create(
            customer=CustomerProfile.objects.create(user=owner),
            channel=OrderChannel.ONLINE,
            contact_email="me@example.com",
        )
        # A non-ONLINE channel with the same email must not be claimed either
        phone_order = Order.objects.create(
            customer=None, channel=OrderChannel.PHONE, contact_email="me@example.com"
        )
        counter_sale = Order.objects.create(customer=None, channel=OrderChannel.POS)

        user = make_user("me@example.com")
        verify(user, django_capture_on_commit_callbacks)

        for untouched in (someone_elses, phone_order, counter_sale):
            untouched.refresh_from_db()
            assert untouched.customer is None
        owned.refresh_from_db()
        assert owned.customer.user == owner, "an order that already has an owner is never reassigned"
        mine.refresh_from_db()
        assert mine.customer.user == user

    def test_a_phone_number_never_links_an_order(self, world, django_capture_on_commit_callbacks):
        """Same phone, different email: not the same person as far as we can prove."""
        order = guest_order(world, 0, email="a@example.com", phone="01001234567")
        user = make_user("b@example.com")

        verify(user, django_capture_on_commit_callbacks)

        order.refresh_from_db()
        assert order.customer is None

    def test_claiming_sends_no_order_signals(self, world, django_capture_on_commit_callbacks):
        """
        ⚠️  `queryset.update`, not `save()`: a `post_save` on an order is what
            makes loyalty pay points for COMPLETED/DELIVERED orders — retroactively,
            for every old guest order at once.
        """
        guest_order(world, 0, email="quiet@example.com")
        user = make_user("quiet@example.com")
        seen = []

        def spy(sender, instance, **kwargs):
            seen.append(instance.pk)

        post_save.connect(spy, sender=Order, weak=False, dispatch_uid="claim-spy")
        try:
            verify(user, django_capture_on_commit_callbacks)
        finally:
            post_save.disconnect(sender=Order, dispatch_uid="claim-spy")

        assert seen == []

    def test_customer_statistics_are_not_retroactively_changed(
        self, world, django_capture_on_commit_callbacks
    ):
        order = guest_order(world, 0, email="stats@example.com")
        Order.objects.filter(pk=order.pk).update(status=OrderStatus.COMPLETED)
        user = make_user("stats@example.com")

        verify(user, django_capture_on_commit_callbacks)

        profile = CustomerProfile.objects.get(user=user)
        assert profile.total_orders == 0
        assert profile.total_spent == Decimal("0")

    def test_a_profile_is_created_only_for_an_account_that_has_orders(
        self, django_capture_on_commit_callbacks
    ):
        """Staff and admins verify their email too — they must not get orphan customer rows."""
        user = make_user("staff@example.com")

        verify(user, django_capture_on_commit_callbacks)

        assert not CustomerProfile.objects.filter(user=user).exists()

    def test_the_claim_is_audited(self, world, django_capture_on_commit_callbacks):
        order = guest_order(world, 0, email="audit@example.com")
        user = make_user("audit@example.com")

        verify(user, django_capture_on_commit_callbacks)

        entry = AuditLog.objects.filter(actor=user, changes__has_key="guest_orders_claimed").first()
        assert entry is not None
        assert entry.changes["guest_orders_claimed"]["new"] == [order.number]

    def test_a_failing_claim_cannot_undo_the_verification(
        self, world, django_capture_on_commit_callbacks
    ):
        guest_order(world, 0, email="resilient@example.com")
        user = make_user("resilient@example.com")

        with patch.object(guest, "claim_orders", side_effect=RuntimeError("boom")):
            verify(user, django_capture_on_commit_callbacks)

        assert user.email_verified_at is not None

    def test_confirming_an_email_change_claims_too(self, world, django_capture_on_commit_callbacks):
        order = guest_order(world, 0, email="new.address@example.com")
        user = make_user("old.address@example.com", verified=True)
        _record, raw = account_services.issue_token(
            user, TokenPurpose.EMAIL_CHANGE, new_email="new.address@example.com"
        )

        with django_capture_on_commit_callbacks(execute=True):
            account_services.confirm_email_change(raw)

        order.refresh_from_db()
        assert order.customer is not None and order.customer.user == user

    def test_a_second_run_changes_nothing(self, world, django_capture_on_commit_callbacks):
        guest_order(world, 0, email="twice@example.com")
        user = make_user("twice@example.com")
        verify(user, django_capture_on_commit_callbacks)

        assert guest.claim_orders(user) == 0
