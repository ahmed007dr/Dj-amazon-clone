"""
Claiming a guest order must not pay points for a purchase made as a guest.

⚠️  The loyalty listener awards on *any* `post_save` of an order that is
    DELIVERED or COMPLETED and has a customer. Attaching the owner with
    `order.save()` would therefore credit every old guest order at once, the
    moment the email is verified. `orders.guest.claim_orders` uses
    `queryset.update()` for exactly this reason.
"""

from decimal import Decimal

import pytest
from django.utils import timezone

from accounts import services as account_services
from accounts.models import AccountType, TokenPurpose, User
from customers.models import CustomerProfile
from loyalty import services
from loyalty.models import LoyaltyProgram, PointsEntry
from orders import guest
from orders.models import Order, OrderStatus, PaymentStatus
from orders.tests.guest_support import place

pytest_plugins = ["orders.tests.guest_support"]

PASSWORD = "Str0ng-Test-Pass!23"


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


def delivered_guest_order(world):
    _, response = place(world, quantity=2)
    order = Order.objects.get(number=response.data["order_number"])
    # Set without signals — the history of a purchase already completed as a guest
    Order.objects.filter(pk=order.pk).update(
        status=OrderStatus.DELIVERED, payment_status=PaymentStatus.PAID
    )
    return Order.objects.get(pk=order.pk)


@pytest.mark.django_db
def test_a_guest_order_earns_nothing_while_it_is_a_guest_order(world, program):
    order = delivered_guest_order(world)

    assert services.award_for_order(order) is None  # no customer, so nobody to credit
    assert PointsEntry.objects.count() == 0


@pytest.mark.django_db
def test_claiming_a_delivered_order_awards_no_points(
    world, program, django_capture_on_commit_callbacks
):
    order = delivered_guest_order(world)
    user = User.objects.create_user(
        email="ahmed.buyer@example.com", password=PASSWORD, account_type=AccountType.STUDENT
    )
    user.is_active = True
    user.save()
    _record, raw = account_services.issue_token(user, TokenPurpose.EMAIL_VERIFICATION)

    with django_capture_on_commit_callbacks(execute=True):
        account_services.verify_email(raw)

    order.refresh_from_db()
    profile = CustomerProfile.objects.get(user=user)
    assert order.customer == profile, "the order really was claimed"
    assert PointsEntry.objects.count() == 0, "…and the claim paid no points"
    assert services.balance(profile) == 0


@pytest.mark.django_db
def test_claimed_orders_carry_the_marker_loyalty_needs_to_skip_them(
    world, program, django_capture_on_commit_callbacks
):
    order = delivered_guest_order(world)
    user = User.objects.create_user(email="ahmed.buyer@example.com", password=PASSWORD)
    user.email_verified_at = timezone.now()
    user.save()

    assert guest.claim_orders(user) == 1

    order.refresh_from_db()
    assert order.claimed_at is not None

    # A later save (completion, a panel edit) reaches the loyalty listener with the
    # customer now attached — the claim marker is what keeps the old purchase unpaid.
    with django_capture_on_commit_callbacks(execute=True):
        order.save()

    assert PointsEntry.objects.count() == 0
    assert services.award_for_order(order) is None
