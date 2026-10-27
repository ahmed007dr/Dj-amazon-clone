"""
Mail and alerts for guest orders — a buyer with no account.

⚠️  The member listeners return silently when `order.customer` is null (a counter
    sale has nobody to tell). A guest order is also customer-null, so without the
    guest branch the buyer would receive nothing at all — no confirmation, no
    tracking link — and the owner would not know a call was waiting.
"""

from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.utils import timezone

from accounts.models import AccountType, User
from mailing import templates as mail_templates
from mailing.models import OutboundMessage
from notifications.models import Notification
from orders import guest, services
from orders.models import Order, OrderChannel, OrderStatus
from orders.tests.guest_support import place

pytest_plugins = ["orders.tests.guest_support"]

PASSWORD = "Str0ng-Test-Pass!23"


def staff_user(email="staff@test.local", *, permission=True, superuser=False):
    user = User.objects.create_user(email=email, password=PASSWORD, account_type=AccountType.GUEST)
    user.is_active = True
    user.is_superuser = superuser
    user.save()
    if permission:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="orders", codename="change_order")
        )
    return user


def place_order(world, **overrides):
    _, response = place(world, **overrides)
    assert response.status_code == 201, response.data
    return response.data, Order.objects.get(number=response.data["order_number"])


def mails(order=None, template=None, to=None):
    queryset = OutboundMessage.objects.all()
    if template:
        queryset = queryset.filter(template_key=template)
    if to:
        queryset = queryset.filter(to_email=to)
    return queryset


class TestTemplates:
    def test_the_guest_templates_exist_in_both_languages(self):
        for key in ("guest_order_confirmation", "guest_order_admin_alert"):
            template = mail_templates.TEMPLATES[key]
            assert template.subject_ar and template.subject_en, key
            assert template.body_ar and template.body_en, key

    def test_the_order_number_is_in_both_subjects(self):
        for key in ("guest_order_confirmation", "guest_order_admin_alert"):
            template = mail_templates.TEMPLATES[key]
            assert "{number}" in template.subject_ar and "{number}" in template.subject_en

    def test_the_confirmation_carries_what_a_buyer_with_no_account_needs(self):
        template = mail_templates.GUEST_ORDER_CONFIRMATION
        assert {"number", "items", "total", "address", "phone", "link", "name"} <= set(
            template.variables
        )
        # Cash on delivery and the confirmation call are stated, in both languages
        assert "نقدًا عند الاستلام" in template.body_ar
        assert "cash on delivery" in template.body_en

    def test_the_templates_are_orders_purpose(self):
        assert mail_templates.GUEST_ORDER_CONFIRMATION.purpose == "ORDERS"
        assert mail_templates.GUEST_ORDER_ADMIN_ALERT.purpose == "ORDERS"


@pytest.mark.django_db
class TestConfirmation:
    def test_the_buyer_gets_a_confirmation_with_items_total_and_a_working_link(self, world):
        data, order = place_order(world, quantity=2, language="en")

        message = mails(template="guest_order_confirmation", to="ahmed.buyer@example.com").get()
        assert order.number in message.subject
        assert "We received your order" in message.subject  # the language chosen at checkout
        assert "• Product G-001 × 2" in message.body
        assert "258.00 EGP" in message.body
        assert "cash on delivery" in message.body

        link = re.search(r"https?://\S+/order/guest/(\S+)", message.body)
        assert link, message.body
        assert link.group(1).strip() == data["tracking_token"]
        # …and that link really opens the order
        assert guest.read_token(link.group(1)).pk == order.pk

    def test_an_arabic_buyer_gets_arabic(self, world):
        place_order(world, language="ar")
        message = mails(template="guest_order_confirmation").get()
        assert "استلمنا طلبك" in message.subject
        assert "• منتج G-001 × 1" in message.body

    def test_the_colour_chosen_is_in_the_item_line(self, world):
        from orders.models import OrderLine

        _, order = place_order(world, language="en")
        OrderLine.objects.filter(order=order).update(color_name_en="Navy", color_name_ar="كحلي")

        items = guest.mail_context(Order.objects.get(pk=order.pk), "t")["items"]
        assert items == "• Product G-001 (Navy) × 1"

    def test_exactly_one_confirmation_per_order(self, world):
        place_order(world)
        assert mails(template="guest_order_confirmation").count() == 1

    def test_a_replayed_checkout_does_not_mail_again(self, world):
        from orders.tests.guest_support import FORM, add_to_cart, guest_client

        client = guest_client()
        add_to_cart(client, world)
        for _ in range(2):
            client.post(
                "/api/v1/orders/guest-checkout/",
                FORM,
                format="json",
                HTTP_IDEMPOTENCY_KEY="k-12345678",
            )

        assert mails(template="guest_order_confirmation").count() == 1

    def test_a_refused_checkout_sends_nothing(self, world, settings):
        place_order(world)  # one order exists
        baseline = OutboundMessage.objects.count()

        settings.GUEST_CHECKOUT_MAX_OPEN_ORDERS = 1
        _, refused = place(world, session="12345678-8a52-4a0e-9f43-5b2e0c6a0001")

        assert refused.status_code == 429
        assert OutboundMessage.objects.count() == baseline

    def test_no_account_notification_is_created_for_the_buyer(self, world):
        place_order(world)
        # Staff may be alerted; no *buyer* exists to hold a notification
        assert not Notification.objects.filter(user__email="ahmed.buyer@example.com").exists()


@pytest.mark.django_db
class TestOwnerAlert:
    def test_every_order_manager_is_notified_in_app(self, world):
        manager = staff_user("manager@test.local")
        owner = staff_user("owner@test.local", permission=False, superuser=True)
        data, order = place_order(world)

        for who in (manager, owner):
            note = Notification.objects.get(user=who, reference_id=str(order.pk))
            assert order.number in note.title
            assert "01001234567" in note.body or "+201001234567" in note.body
            assert note.action_url == f"/admin/orders/{order.pk}"
            assert note.priority == "HIGH"

    def test_people_who_cannot_manage_orders_are_not_told(self, world):
        bystander = staff_user("bystander@test.local", permission=False)
        place_order(world)
        assert not Notification.objects.filter(user=bystander).exists()

    def test_inactive_managers_are_skipped(self, world):
        manager = staff_user("gone@test.local")
        manager.is_active = False
        manager.save()
        place_order(world)
        assert not Notification.objects.filter(user=manager).exists()

    def test_the_alert_is_in_app_only_not_a_second_email_to_staff(self, world):
        manager = staff_user("manager@test.local")
        place_order(world)
        assert not mails(to=manager.email).exists()

    def test_an_optional_address_gets_the_detailed_email(self, world, settings):
        settings.GUEST_ORDER_ALERT_EMAIL = "shop@test.local"
        _, order = place_order(world)

        message = mails(template="guest_order_admin_alert", to="shop@test.local").get()
        assert order.number in message.subject
        assert "+201001234567" in message.body
        assert f"/admin/orders/{order.pk}" in message.body
        assert message.language == "ar"

    def test_without_the_setting_no_store_email_is_sent(self, world, settings):
        settings.GUEST_ORDER_ALERT_EMAIL = ""
        place_order(world)
        assert not mails(template="guest_order_admin_alert").exists()


@pytest.mark.django_db
class TestStatusMail:
    @pytest.mark.parametrize(
        ("status", "template"),
        [
            (OrderStatus.CONFIRMED, "order_confirmed"),
            (OrderStatus.CANCELLED, "order_cancelled"),
        ],
    )
    def test_the_buyer_hears_about_the_changes_that_matter(self, world, status, template):
        _, order = place_order(world)

        if status == OrderStatus.CANCELLED:
            services.cancel(order, reason="نفد الصنف")
        else:
            services.transition(order, status)

        message = mails(template=template, to="ahmed.buyer@example.com").get()
        assert order.number in message.subject
        assert "/order/guest/" in message.body

    def test_shipped_and_delivered(self, world):
        _, order = place_order(world)
        for status in (OrderStatus.CONFIRMED, OrderStatus.PROCESSING, OrderStatus.SHIPPED):
            services.transition(order, status)
        services.transition(order, OrderStatus.DELIVERED)

        assert mails(template="order_shipped").count() == 1
        assert mails(template="order_delivered").count() == 1
        # PROCESSING means nothing to the buyer
        assert OutboundMessage.objects.filter(template_key__in=["order_processing"]).count() == 0

    def test_the_cancellation_reason_is_in_the_mail(self, world):
        _, order = place_order(world)
        services.cancel(order, reason="لم يرد على الهاتف")
        assert "لم يرد على الهاتف" in mails(template="order_cancelled").get().body

    def test_an_auto_cancellation_tells_the_buyer_why(self, world):
        _, order = place_order(world)
        Order.objects.filter(pk=order.pk).update(created_at=timezone.now() - timedelta(hours=60))
        guest.cancel_unconfirmed()
        assert "48" in mails(template="order_cancelled").get().body

    def test_a_later_save_does_not_repeat_the_message(self, world):
        """
        ⚠️  `post_save` fires on every save — recording a payment, editing an
            internal note. One mail per status per order.
        """
        _, order = place_order(world)
        services.transition(order, OrderStatus.CONFIRMED)

        order.refresh_from_db()
        order.internal_note = "ring twice"
        order.save()  # a plain, full save in the Django panel
        order.payment_status = "PENDING"
        order.save(update_fields=["payment_status"])

        assert mails(template="order_confirmed").count() == 1

    def test_the_link_in_each_message_is_fresh_and_valid(self, world):
        _, order = place_order(world)
        services.transition(order, OrderStatus.CONFIRMED)

        body = mails(template="order_confirmed").get().body
        token = re.search(r"/order/guest/(\S+)", body).group(1)
        assert guest.read_token(token).pk == order.pk

    def test_a_counter_sale_is_still_ignored(self, world, location):
        order = Order.objects.create(
            customer=None, channel=OrderChannel.POS, grand_total=Decimal("10.00")
        )
        order.status = OrderStatus.CANCELLED
        order.save()

        assert OutboundMessage.objects.count() == 0

    def test_a_claimed_order_is_mailed_through_the_member_path(self, world):
        """Once claimed it has an account, so the member listener takes over (one path, not two)."""
        from customers.models import CustomerProfile

        _, order = place_order(world)
        user = User.objects.create_user(email="ahmed.buyer@example.com", password=PASSWORD)
        user.email_verified_at = timezone.now()
        user.save()
        guest.claim_orders(user)
        order.refresh_from_db()
        assert order.customer == CustomerProfile.objects.get(user=user)

        OutboundMessage.objects.all().delete()
        services.transition(order, OrderStatus.CONFIRMED)

        sent = list(OutboundMessage.objects.values_list("template_key", "body"))
        assert [key for key, _body in sent] == ["order_confirmed"]
        assert "/order/guest/" not in sent[0][1]
