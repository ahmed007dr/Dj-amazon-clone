"""
اختبارات بريد الطلبات.

⚠️  المستمعون كانوا يُنشئون إشعارًا داخل التطبيق **بلا بريد**.

    فالعميل الذي لا يفتح الموقع لا يعرف أن طلبه شُحن. و`notify`
    ترسل البريد حين يُمرَّر قالب — والغياب كان يُقرأ كأنه اختيار.
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
#  القوالب
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
        ⚠️  قالب بلغة واحدة يعني مستخدمًا يتلقى رسالة لا يفهمها.
        """
        for key in self.ORDER_KEYS:
            template = mail_templates.TEMPLATES[key]
            assert template.subject_ar and template.subject_en, key
            assert template.body_ar and template.body_en, key

    def test_order_number_appears_in_every_subject(self):
        """
        ⚠️  العميل يبحث في بريده **برقم الطلب**.

            دفنه في منتصف فقرة يجعل البحث يفشل ويصير السؤال مكالمةً
            للدعم.
        """
        for key in self.ORDER_KEYS:
            template = mail_templates.TEMPLATES[key]
            assert "{number}" in template.subject_ar, key
            assert "{number}" in template.subject_en, key

    def test_rendering_fills_every_placeholder(self):
        """
        ⚠️  حقل ناقص يرفع `KeyError` **وقت الإرسال** لا وقت الكتابة —
            أي بريد لا يصل وطلب يبدو كأنه لم يُسجَّل.
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
#  الإرسال الفعلي عبر المستمعين
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestOrderMailDelivery:
    def test_new_order_sends_confirmation(self, customer, django_capture_on_commit_callbacks):
        """
        ⚠️  التسليم على `on_commit`: المعاملة التي تُلغى بعد إنشاء
            الطلب كانت تترك العميل ومعه رسالة عن طلب لا وجود له.
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
        ⚠️  إشعار عند كل حفظ يغرق العميل برسائل لا تخصّه.

            «قيد التجهيز» تعنيه؛ أما تعديل ملاحظة داخلية فلا.
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
        ⚠️  الأدمن ينقل الحالة بواجهة إنجليزية — والعميل العربي يجب
            أن يتلقّى رسالته بالعربية.
        """
        customer.user.preferred_language = "en"
        customer.user.save()

        with django_capture_on_commit_callbacks(execute=True):
            make_order(customer)

        assert len(django_mail.outbox) == 1
        assert "We received your order" in django_mail.outbox[0].subject
