"""
The guest-order job in the periodic runner.

⚠️  Lives in `ops/tests`, not `orders/tests`: `ops` sits above `orders` in the
    layer diagram, so a test that touches the runner belongs here.
"""

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from ops.management.commands.run_periodic import JOBS, Command
from orders import guest
from orders.models import Order, OrderStatus
from orders.tests.guest_support import place

pytest_plugins = ["orders.tests.guest_support"]


def test_the_job_is_registered_in_the_orders_group():
    group, label, function = JOBS["cancel_unconfirmed_guest_orders"]
    assert group == "orders"
    assert label
    assert function is guest.cancel_unconfirmed


def test_the_orders_group_selects_only_that_job():
    assert list(Command()._select("orders")) == ["cancel_unconfirmed_guest_orders"]


@pytest.mark.django_db
def test_running_the_job_cancels_a_stale_unconfirmed_guest_order(world):
    _, response = place(world)
    order = Order.objects.get(number=response.data["order_number"])
    Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(hours=100))

    call_command("run_periodic", "--job", "cancel_unconfirmed_guest_orders")

    order.refresh_from_db()
    assert order.status == OrderStatus.CANCELLED


@pytest.mark.django_db
def test_a_fresh_order_survives_the_run(world):
    _, response = place(world)

    call_command("run_periodic", "--job", "cancel_unconfirmed_guest_orders")

    assert Order.objects.get(number=response.data["order_number"]).status == OrderStatus.PENDING
