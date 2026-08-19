"""
Order mail tests.

⚠️  The listeners used to create an in-app notification **with no email**.

    So a customer who does not open the website never knew their order had
    shipped. And `notify` sends the email when a template is passed — the
    absence was read as though it were a choice.
"""

from decimal import Decimal

import pytest
from django.core import mail as django_mail

from mailing import templates as mail_templates
from orders.models import Order, OrderStatus


@pytest.fixture(autouse=True)
def clear_outbox():
    django_mail.outbox.clear()
    yield


@pytest.fixture
def customer(db):
    from accounts.models import User
    from customers.models import CustomerProfile

    user = User.objects.create_user(email="buyer@test.local", password="Str0ng-Pass!23")
    user.is_active = True
    user.first_name = "نور"
    user.save()
    return CustomerProfile.objects.create(user=user)


def make_order(customer, **overrides):
    return Order.objects.create(
        customer=customer,
        grand_total=Decimal("250.00"),
        recipient_name="نور",
        governorate="القاهرة",
        city="مدينة نصر",
        street="١٢ شارع مصطفى النحاس",
        **overrides,
    )


# ═══════════════════════════════════════════════════════════
#  Templates
# ═══════════════════════════════════════════════════════════


class TestTemplates:
    ORDER_KEYS = [
        "order_placed",
        "order_confirmed",
        "order_shipped",
        "order_delivered",
        "order_cancelled",
        "payment_received",
    ]

    def test_all_order_templates_exist(self):
        for key in self.ORDER_KEYS:
            assert key in mail_templates.TEMPLATES, key

    def test_both_languages_are_filled(self):
        """
        ⚠️  A template in one language means a user receiving a message they cannot read.
        """
        for key in self.ORDER_KEYS:
            template = mail_templates.TEMPLATES[key]
            assert template.subject_ar and template.subject_en, key
            assert template.body_ar and template.body_en, key

    def test_order_number_appears_in_every_subject(self):
        """
        ⚠️  The customer searches their mail **by order number**.

            Burying it mid-paragraph makes the search fail and turns the
            question into a support call.
        """
        for key in self.ORDER_KEYS:
            template = mail_templates.TEMPLATES[key]
            assert "{number}" in template.subject_ar, key
            assert "{number}" in template.subject_en, key

    def test_rendering_fills_every_placeholder(self):
        """
        ⚠️  A missing field raises `KeyError` **at send time**, not at write
            time — that is, an email that never arrives and an order that looks unrecorded.
        """
        context = {
            "name": "نور",
            "number": "ORD-2026-TEST",
            "total": "250.00 EGP",
            "address": "القاهرة",
            "reason": "—",
            "link": "https://example.test/orders/1",
            "method": "COD",
            "reference": "PAY-1",
        }

        for key in self.ORDER_KEYS:
            for language in ("ar", "en"):
                subject, body = mail_templates.TEMPLATES[key].render(language, context)
                assert "{" not in subject, f"{key}/{language}"
                assert "{" not in body, f"{key}/{language}"


# ═══════════════════════════════════════════════════════════
#  Actual sending through the listeners
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestOrderMailDelivery:
    def test_new_order_sends_confirmation(self, customer, django_capture_on_commit_callbacks):
        """
        ⚠️  Delivery on `on_commit`: a transaction rolled back after the order
            was created used to leave the customer holding a message about an
            order that does not exist.
        """
        with django_capture_on_commit_callbacks(execute=True):
            make_order(customer)

        assert len(django_mail.outbox) == 1
        assert "ORD-" in django_mail.outbox[0].subject

    def test_shipping_sends_mail_with_the_address(
        self, customer, django_capture_on_commit_callbacks
    ):
        order = make_order(customer, status=OrderStatus.CONFIRMED)
        django_mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            order.status = OrderStatus.SHIPPED
            order.save()

        assert len(django_mail.outbox) == 1
        assert "مدينة نصر" in django_mail.outbox[0].body

    def test_cancellation_includes_the_reason(self, customer, django_capture_on_commit_callbacks):
        order = make_order(customer)
        django_mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            order.status = OrderStatus.CANCELLED
            order.cancellation_reason = "نفد المخزون"
            order.save()

        assert len(django_mail.outbox) == 1
        assert "نفد المخزون" in django_mail.outbox[0].body

    def test_internal_edits_send_nothing(self, customer, django_capture_on_commit_callbacks):
        """
        ⚠️  A notification on every save floods the customer with messages that do not concern them.

            "Processing" concerns them; editing an internal note does not.
        """
        order = make_order(customer)
        django_mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            order.internal_note = "راجعه محمود"
            order.save()

        assert django_mail.outbox == []

    def test_language_follows_the_recipient_not_the_actor(
        self, customer, django_capture_on_commit_callbacks
    ):
        """
        ⚠️  The admin moves the status through an English interface — and the
            Arabic-speaking customer must receive their message in Arabic.
        """
        customer.user.preferred_language = "en"
        customer.user.save()

        with django_capture_on_commit_callbacks(execute=True):
            make_order(customer)

        assert len(django_mail.outbox) == 1
        assert "We received your order" in django_mail.outbox[0].subject
