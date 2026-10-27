"""
Guest orders in the admin API.

⚠️  Before this, `customer_email` was a `source="customer.user.email"` field. For
    an order with no customer DRF drops a failed read-only source *silently*, so
    the admin screens — which print that key — showed nothing for guest orders
    and counter sales, and the search ignored the only contact the guest left.
"""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from core.testing import grant_all_domains
from customers.models import CustomerProfile
from orders import guest, services
from orders.models import Order, OrderChannel, OrderStatus
from orders.tests.guest_support import add_to_cart, checkout, guest_client, place

pytest_plugins = ["orders.tests.guest_support"]

PASSWORD = "Str0ng-Test-Pass!23"


@pytest.fixture
def admin_client(db):
    from administration.models import AdminProfile

    user = User.objects.create_user(
        email="admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    user.is_active = True
    user.save()
    AdminProfile.objects.create(user=user)
    grant_all_domains(user)
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def listing(client, **params):
    response = client.get(reverse("v1:orders:admin-orders"), params)
    assert response.status_code == 200, response.data
    return response.data["results"]


def numbers(rows):
    return {row["number"] for row in rows}


@pytest.fixture
def mixed_orders(world, db):
    """One guest order, one member order, one counter sale."""
    _, response = place(world)
    guest_order = Order.objects.get(number=response.data["order_number"])

    member = User.objects.create_user(email="member@test.local", password=PASSWORD)
    profile = CustomerProfile.objects.create(user=member)
    member_order = Order.objects.create(
        customer=profile, channel=OrderChannel.ONLINE, recipient_phone="+201155556666"
    )
    counter = Order.objects.create(customer=None, channel=OrderChannel.POS)
    return guest_order, member_order, counter


@pytest.mark.django_db
class TestAdminSerializer:
    def test_a_guest_order_shows_its_contact_instead_of_a_blank(self, admin_client, mixed_orders):
        guest_order, _, _ = mixed_orders

        row = next(r for r in listing(admin_client) if r["number"] == guest_order.number)

        assert row["is_guest"] is True
        assert row["contact_email"] == "ahmed.buyer@example.com"
        assert row["customer_email"] == "ahmed.buyer@example.com"  # falls back to the contact
        assert row["customer_number"] == ""
        assert row["customer"] is None
        assert row["contact_language"] == "en"
        assert row["claimed_at"] is None
        assert row["recipient_phone"] == "+201001234567"

    def test_a_member_order_is_unchanged(self, admin_client, mixed_orders):
        _, member_order, _ = mixed_orders

        row = next(r for r in listing(admin_client) if r["number"] == member_order.number)

        assert row["is_guest"] is False
        assert row["customer_email"] == "member@test.local"
        assert row["customer_number"].startswith("CUS-")
        assert row["contact_email"] == ""

    def test_a_counter_sale_has_keys_not_holes(self, admin_client, mixed_orders):
        _, _, counter = mixed_orders

        row = next(r for r in listing(admin_client) if r["number"] == counter.number)

        assert row["is_guest"] is False
        assert row["customer_email"] == ""
        assert row["customer_number"] == ""

    def test_the_detail_endpoint_carries_the_same_fields(self, admin_client, mixed_orders):
        guest_order, _, _ = mixed_orders
        response = admin_client.get(reverse("v1:orders:admin-detail", args=[guest_order.pk]))

        assert response.status_code == 200
        assert response.data["is_guest"] is True
        assert response.data["contact_email"] == "ahmed.buyer@example.com"
        assert response.data["lines"]

    def test_a_claimed_order_reads_as_a_member_order_with_its_history(self, admin_client, world):
        _, response = place(world)
        order = Order.objects.get(number=response.data["order_number"])
        user = User.objects.create_user(email="ahmed.buyer@example.com", password=PASSWORD)
        user.email_verified_at = timezone.now()
        user.save()

        guest.claim_orders(user)

        row = admin_client.get(reverse("v1:orders:admin-detail", args=[order.pk])).data
        assert row["is_guest"] is False
        assert row["customer_email"] == "ahmed.buyer@example.com"
        assert row["contact_email"] == "ahmed.buyer@example.com"
        assert row["claimed_at"] is not None

    def test_the_admin_can_move_a_guest_order_through_its_states(self, admin_client, mixed_orders):
        guest_order, _, _ = mixed_orders

        response = admin_client.post(
            reverse("v1:orders:admin-transition", args=[guest_order.pk]),
            {"status": "CONFIRMED", "note": "اتصلنا بالعميل وأكّد"},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["status"] == "CONFIRMED"
        assert response.data["is_guest"] is True


@pytest.mark.django_db
class TestAdminSearch:
    def test_by_the_guests_email(self, admin_client, mixed_orders):
        guest_order, _, _ = mixed_orders
        assert numbers(listing(admin_client, search="ahmed.buyer")) == {guest_order.number}
        assert numbers(listing(admin_client, search="AHMED.BUYER@EXAMPLE")) == {guest_order.number}

    def test_by_the_guests_name(self, admin_client, mixed_orders):
        guest_order, _, _ = mixed_orders
        assert numbers(listing(admin_client, search="أحمد محمود")) == {guest_order.number}

    @pytest.mark.parametrize(
        "typed", ["01001234567", "+201001234567", "1001234567", "0100", "100123"]
    )
    def test_by_phone_however_it_is_typed(self, admin_client, mixed_orders, typed):
        """Phones are stored canonical (`+20…`) — a local-format search must still find them."""
        guest_order, _, _ = mixed_orders
        assert guest_order.number in numbers(listing(admin_client, search=typed))

    def test_a_phone_search_does_not_match_everything(self, admin_client, mixed_orders):
        _, member_order, _ = mixed_orders
        assert numbers(listing(admin_client, search="01155556666")) == {member_order.number}

    def test_an_order_number_still_works_and_is_not_read_as_a_phone(
        self, admin_client, mixed_orders
    ):
        guest_order, _, _ = mixed_orders
        assert numbers(listing(admin_client, search=guest_order.number)) == {guest_order.number}

    def test_by_member_email_as_before(self, admin_client, mixed_orders):
        _, member_order, _ = mixed_orders
        assert numbers(listing(admin_client, search="member@test")) == {member_order.number}


@pytest.mark.django_db
class TestGuestFilter:
    def test_guest_only(self, admin_client, mixed_orders):
        guest_order, _, _ = mixed_orders
        assert numbers(listing(admin_client, guest="true")) == {guest_order.number}

    def test_not_guest(self, admin_client, mixed_orders):
        _, member_order, counter = mixed_orders
        assert numbers(listing(admin_client, guest="false")) == {
            member_order.number,
            counter.number,
        }

    def test_any_other_value_means_no_filter(self, admin_client, mixed_orders):
        assert len(listing(admin_client, guest="maybe")) == 3

    def test_it_composes_with_the_status_tab(self, admin_client, mixed_orders):
        guest_order, _, _ = mixed_orders
        services.transition(guest_order, OrderStatus.CONFIRMED)
        assert numbers(listing(admin_client, guest="true", status="PENDING")) == set()
        assert numbers(listing(admin_client, guest="true", status="CONFIRMED")) == {
            guest_order.number
        }

    def test_the_endpoint_is_still_admin_only(self, world):
        client = guest_client()
        add_to_cart(client, world)
        checkout(client)
        assert client.get(reverse("v1:orders:admin-orders")).status_code in (401, 403)


@pytest.mark.django_db
class TestDjangoAdmin:
    @staticmethod
    def _client():
        superuser = User.objects.create_superuser(email="root@test.local", password=PASSWORD)
        client = Client()
        client.force_login(superuser)
        return client

    def test_the_change_list_and_form_render_for_guest_orders(self, mixed_orders):
        client = self._client()
        guest_order, _, _ = mixed_orders

        changelist = client.get(f"/{settings.ADMIN_URL}/orders/order/")
        assert changelist.status_code == 200
        assert "زائر" in changelist.content.decode()

        form = client.get(ff"/{settings.ADMIN_URL}/orders/order/{guest_order.pk}/change/")
        assert form.status_code == 200
        assert "ahmed.buyer@example.com" in form.content.decode()

    def test_the_buyer_filter_splits_guests_from_members(self, mixed_orders):
        client = self._client()
        guest_order, member_order, _ = mixed_orders

        guests = client.get(f"/{settings.ADMIN_URL}/orders/order/?buyer=guest").content.decode()
        assert guest_order.number in guests
        assert member_order.number not in guests

    def test_search_finds_the_guest_by_email(self, mixed_orders):
        client = self._client()
        guest_order, _, _ = mixed_orders

        page = client.get(f"/{settings.ADMIN_URL}/orders/order/?q=ahmed.buyer").content.decode()
        assert guest_order.number in page
