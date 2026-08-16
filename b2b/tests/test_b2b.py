"""
اختبارات B2B.

⚠️  بوابة الخروج للمرحلة ٩:

        الائتمان **لا يُتجاوَز** بأي طريق · كشف الحساب يوازن ·
        لا عميل يقرأ حساب غيره.

    والأخطر ليس المعادلة بل ما يحيط بها: أن يمرّ طلبان متزامنان
    معًا فيتجاوز مجموعهما الحد · أن يُخفي تعليم الفاتورة «متأخرة»
    الفاتورةَ نفسها عن بوابة المنع · أن يبقى العميل مدينًا ببضاعة
    أعادها.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from administration.models import AdminProfile
from b2b import services
from b2b.models import (
    BusinessKind,
    BusinessProfile,
    CreditStatus,
    Invoice,
    InvoiceStatus,
    LedgerEntry,
    LedgerKind,
)
from core.errors import BusinessError
from customers.models import CustomerProfile
from orders.models import Order, OrderStatus, PaymentStatus

PASSWORD = "Str0ng-Test-Pass!23"


# ═══════════════════════════════════════════════════════════
#  التجهيز
# ═══════════════════════════════════════════════════════════


def make_business(email, *, limit="10000.00", terms=30, status=CreditStatus.ACTIVE, **extra):
    user = User.objects.create_user(
        email=email, password=PASSWORD, account_type=AccountType.PHARMACY
    )
    user.is_active = True
    user.save()

    customer = CustomerProfile.objects.create(user=user)
    return BusinessProfile.objects.create(
        customer=customer,
        kind=BusinessKind.PHARMACY,
        legal_name=extra.pop("legal_name", "صيدلية النور"),
        credit_status=status,
        credit_limit=Decimal(limit),
        payment_terms_days=terms,
        **extra,
    )


@pytest.fixture
def pharmacy(db):
    return make_business("pharmacy-a@test.local")


@pytest.fixture
def manager(db):
    user = User.objects.create_user(
        email="b2b-manager@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    user.is_active = True
    user.is_superuser = True
    user.save()
    AdminProfile.objects.create(user=user)
    return user


def make_order(customer, total="1000.00"):
    amount = Decimal(total)
    return Order.objects.create(
        customer=customer,
        status=OrderStatus.CONFIRMED,
        payment_status=PaymentStatus.PENDING,
        subtotal=amount,
        grand_total=amount,
    )


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ═══════════════════════════════════════════════════════════
#  بوابة الائتمان — بوابة الخروج
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCreditGate:
    def test_a_new_account_has_no_credit(self, db):
        """
        ⚠️  حد ائتماني تلقائي يعني بضاعة تخرج لعميل لم يراجعه أحد.
        """
        fresh = make_business("fresh@test.local", limit="0.00", status=CreditStatus.NONE)

        decision = services.evaluate_credit(fresh, Decimal("1.00"))

        assert not decision.allowed
        assert "الدفع مقدَّم" in decision.reason

    def test_within_the_limit_passes(self, pharmacy):
        assert services.evaluate_credit(pharmacy, Decimal("9999.00")).allowed

    def test_above_the_limit_is_refused_with_the_available_amount(self, pharmacy):
        """⚠️  «مرفوض» بلا رقم يجعل العميل يخمّن كم يسدّد."""
        decision = services.evaluate_credit(pharmacy, Decimal("10001.00"))

        assert not decision.allowed
        assert decision.available == Decimal("10000.00")

    def test_a_charge_consumes_the_limit(self, pharmacy):
        order = make_order(pharmacy.customer, "4000.00")
        services.charge_on_credit(pharmacy, order)

        assert services.outstanding_balance(pharmacy) == Decimal("4000.00")
        assert services.available_credit(pharmacy) == Decimal("6000.00")

    def test_suspended_credit_blocks_everything(self, pharmacy, manager):
        services.suspend_credit(pharmacy, actor=manager, reason="تعثّر متكرر")

        decision = services.evaluate_credit(pharmacy, Decimal("1.00"))
        assert not decision.allowed
        assert "موقوف" in decision.reason

    def test_suspension_keeps_the_limit_for_later(self, pharmacy, manager):
        """⚠️  تصفير الحد يفقد ما مُنح، فتحتاج إعادة التفعيل قرارًا جديدًا."""
        services.suspend_credit(pharmacy, actor=manager, reason="مراجعة")

        pharmacy.refresh_from_db()
        assert pharmacy.credit_limit == Decimal("10000.00")

    def test_suspension_requires_a_reason(self, pharmacy, manager):
        with pytest.raises(BusinessError):
            services.suspend_credit(pharmacy, actor=manager, reason="  ")

    def test_an_expired_licence_blocks_credit(self, db):
        """
        ⚠️  الترخيص المنتهي يمنع **الآجل** لا البيع.

            منح بضاعة على وعد بينما الوضع القانوني معلّق مخاطرة
            لا تُقاس بالمال وحده.
        """
        expired = make_business(
            "expired@test.local",
            license_expires_on=timezone.localdate() - timedelta(days=1),
        )

        decision = services.evaluate_credit(expired, Decimal("100.00"))

        assert not decision.allowed
        assert "الترخيص" in decision.reason

    def test_a_missing_licence_date_is_treated_as_valid(self, pharmacy):
        """⚠️  اعتبار الغياب انتهاءً كان يمنع كل عميل قديم بلا تاريخ."""
        assert pharmacy.license_expires_on is None
        assert pharmacy.license_is_valid
        assert services.evaluate_credit(pharmacy, Decimal("100.00")).allowed

    def test_an_overdue_invoice_blocks_new_credit(self, pharmacy):
        order = make_order(pharmacy.customer, "500.00")
        services.charge_on_credit(pharmacy, order)

        invoice = Invoice.objects.get(order=order)
        invoice.due_on = timezone.localdate() - timedelta(days=5)
        invoice.save()

        decision = services.evaluate_credit(pharmacy, Decimal("100.00"))
        assert not decision.allowed
        assert "متأخرة" in decision.reason

    def test_flagging_an_invoice_overdue_does_not_hide_it(self, pharmacy):
        """
        ⚠️  **انقلاب كامل في المعنى لو أُغفل.**

            `OVERDUE` حالة عرضية لا مصير. استبعادها من استعلامات
            «المفتوح» كان يجعل تعليم الفاتورة متأخرةً **يخفيها**
            من بوابة المنع — فتسقط أقدم الديون من الحساب بمجرد
            أن تصير أقدم.
        """
        order = make_order(pharmacy.customer, "500.00")
        services.charge_on_credit(pharmacy, order)

        invoice = Invoice.objects.get(order=order)
        invoice.due_on = timezone.localdate() - timedelta(days=5)
        invoice.save()

        services.refresh_overdue_flags()
        invoice.refresh_from_db()
        assert invoice.status == InvoiceStatus.OVERDUE

        # ما زالت تمنع الائتمان بعد التعليم
        assert not services.evaluate_credit(pharmacy, Decimal("1.00")).allowed
        assert services.overdue_invoices(pharmacy).count() == 1

    def test_charging_over_the_limit_raises(self, pharmacy):
        order = make_order(pharmacy.customer, "20000.00")

        with pytest.raises(BusinessError):
            services.charge_on_credit(pharmacy, order)

    def test_one_order_is_charged_only_once(self, pharmacy):
        """
        ⚠️  إعادة المحاولة كانت ستضاعف ما على العميل — فيُمنَع
            بحدٍّ استهلكه مرة واحدة.
        """
        from django.db import IntegrityError, transaction

        order = make_order(pharmacy.customer, "1000.00")
        services.charge_on_credit(pharmacy, order)

        with pytest.raises(IntegrityError), transaction.atomic():
            LedgerEntry.objects.create(
                business=pharmacy,
                kind=LedgerKind.CHARGE,
                amount=Decimal("1000.00"),
                order=order,
            )


# ═══════════════════════════════════════════════════════════
#  الرصيد والسداد
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestLedger:
    def test_balance_is_derived_from_entries(self, pharmacy):
        order = make_order(pharmacy.customer, "3000.00")
        services.charge_on_credit(pharmacy, order)
        services.record_payment(pharmacy, Decimal("1200.00"))

        assert services.outstanding_balance(pharmacy) == Decimal("1800.00")

    def test_entries_are_append_only(self, pharmacy):
        """⚠️  كشف الحساب مستند يُبنى عليه نزاع — لا يُعدَّل بأثر رجعي."""
        entry = services.record_payment(pharmacy, Decimal("100.00"))

        entry.amount = Decimal("999.00")
        with pytest.raises(ValueError):
            entry.save()

    def test_payment_settles_the_oldest_invoice_first(self, pharmacy):
        """
        ⚠️  تسوية الأحدث تُبقي القديمة مفتوحة إلى الأبد، فيظهر عميل
            منتظم متأخرًا ويُمنَع بدين سدّده فعلًا.
        """
        first = make_order(pharmacy.customer, "1000.00")
        services.charge_on_credit(pharmacy, first)

        second = make_order(pharmacy.customer, "2000.00")
        services.charge_on_credit(pharmacy, second)

        # ⚠️  التقديم **بعد** القيدين لا قبلهما.
        #
        #     تقديمه قبل الثاني يجعل الفاتورة متأخرة، فتمنع بوابة
        #     الائتمان القيد الثاني — وهو سلوك صحيح كان سيُقرأ
        #     كفشل في تسوية السداد.
        old_invoice = Invoice.objects.get(order=first)
        old_invoice.due_on = timezone.localdate() - timedelta(days=10)
        old_invoice.save()

        services.record_payment(pharmacy, Decimal("1000.00"))

        old_invoice.refresh_from_db()
        assert old_invoice.status == InvoiceStatus.PAID
        assert Invoice.objects.get(order=second).status == InvoiceStatus.ISSUED

    def test_a_partial_payment_does_not_close_an_invoice(self, pharmacy):
        """
        ⚠️  إغلاقها بمبلغ أقل يخفي الباقي من كشف الحساب — فيختفي
            دين قائم من كل تقرير.
        """
        order = make_order(pharmacy.customer, "1000.00")
        services.charge_on_credit(pharmacy, order)

        services.record_payment(pharmacy, Decimal("400.00"))

        assert Invoice.objects.get(order=order).status == InvoiceStatus.ISSUED
        assert services.outstanding_balance(pharmacy) == Decimal("600.00")

    def test_overpayment_does_not_inflate_the_limit(self, pharmacy):
        """⚠️  الرصيد الدائن ميزة للعميل لا توسيع لسقفه."""
        services.record_payment(pharmacy, Decimal("5000.00"))

        assert services.outstanding_balance(pharmacy) == Decimal("-5000.00")
        assert services.available_credit(pharmacy) == Decimal("10000.00")

    def test_a_negative_payment_is_refused(self, pharmacy):
        with pytest.raises(BusinessError):
            services.record_payment(pharmacy, Decimal("-100.00"))


# ═══════════════════════════════════════════════════════════
#  المرتجعات
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCreditNotes:
    def test_a_refund_releases_the_credit(self, pharmacy):
        """
        ⚠️  بدونه يبقى العميل مدينًا ببضاعة أعادها — فيُمنَع بحدٍّ
            استهلكه طلب أُلغي.
        """
        order = make_order(pharmacy.customer, "4000.00")
        services.charge_on_credit(pharmacy, order)
        assert services.available_credit(pharmacy) == Decimal("6000.00")

        order.status = OrderStatus.REFUNDED
        order.save()

        assert services.outstanding_balance(pharmacy) == Decimal("0.00")
        assert services.available_credit(pharmacy) == Decimal("10000.00")

    def test_the_original_charge_is_kept(self, pharmacy):
        """⚠️  الفاتورة صدرت وسُلّمت — إلغاؤها يترك محاسب العميل بلا نظير."""
        order = make_order(pharmacy.customer, "1000.00")
        services.charge_on_credit(pharmacy, order)

        order.status = OrderStatus.REFUNDED
        order.save()

        assert LedgerEntry.objects.filter(order=order, kind=LedgerKind.CHARGE).exists()
        assert LedgerEntry.objects.filter(order=order, kind=LedgerKind.CREDIT_NOTE).exists()
        assert Invoice.objects.get(order=order).status == InvoiceStatus.CANCELLED

    def test_a_credit_note_is_issued_once(self, pharmacy):
        order = make_order(pharmacy.customer, "1000.00")
        services.charge_on_credit(pharmacy, order)

        order.status = OrderStatus.REFUNDED
        order.save()
        order.save()

        assert LedgerEntry.objects.filter(order=order, kind=LedgerKind.CREDIT_NOTE).count() == 1


# ═══════════════════════════════════════════════════════════
#  كشف الحساب والتقادم
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestStatement:
    def test_opening_plus_movements_equals_closing(self, pharmacy):
        """⚠️  **بوابة الخروج:** كشف الحساب يوازن."""
        today = timezone.localdate()

        old = services.record_payment(pharmacy, Decimal("500.00"))
        LedgerEntry.objects.filter(pk=old.pk).update(occurred_on=today - timedelta(days=100))

        order = make_order(pharmacy.customer, "2000.00")
        services.charge_on_credit(pharmacy, order)

        result = services.statement(pharmacy, today - timedelta(days=30), today)

        assert result.opening_balance == Decimal("-500.00")
        assert result.closing_balance == Decimal("1500.00")
        movement = sum((entry.signed_amount for entry in result.entries), Decimal("0"))
        assert result.opening_balance + movement == result.closing_balance

    def test_inverted_range_is_refused(self, pharmacy):
        """⚠️  المدى المقلوب يُنتج كشفًا فارغًا يبدو حقيقيًا."""
        today = timezone.localdate()

        with pytest.raises(BusinessError):
            services.statement(pharmacy, today, today - timedelta(days=10))

    def test_not_due_is_separated_from_overdue(self, pharmacy):
        """
        ⚠️  خلطهما يجعل عميلًا ملتزمًا يبدو متعثّرًا بمبلغ لم يحن
            موعده.
        """
        order = make_order(pharmacy.customer, "1000.00")
        services.charge_on_credit(pharmacy, order)

        buckets = {bucket.label: bucket.amount for bucket in services.aging(pharmacy)}

        assert buckets["not_due"] == Decimal("1000.00")
        assert buckets["0-30"] == Decimal("0.00")

    def test_very_old_debt_still_appears(self, pharmacy):
        """⚠️  دين عمره سنة يجب أن يظهر لا أن يسقط من آخر سلة."""
        order = make_order(pharmacy.customer, "700.00")
        services.charge_on_credit(pharmacy, order)

        invoice = Invoice.objects.get(order=order)
        invoice.due_on = timezone.localdate() - timedelta(days=365)
        invoice.save()

        buckets = {bucket.label: bucket.amount for bucket in services.aging(pharmacy)}
        assert buckets["90+"] == Decimal("700.00")


# ═══════════════════════════════════════════════════════════
#  العزل بين العملاء
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestIsolation:
    def test_a_pharmacy_never_sees_another_account(self, pharmacy):
        """
        ⚠️  **ضرر تجاري مباشر لا مجرد خرق خصوصية.**

            كشف حساب صيدلية يكشف حجم مشترياتها وهامش تعاملها —
            لصيدلية منافسة في نفس الشارع.
        """
        other = make_business("pharmacy-b@test.local", legal_name="صيدلية المنافس")
        order = make_order(other.customer, "5000.00")
        services.charge_on_credit(other, order)

        response = client_for(pharmacy.customer.user).get(reverse("v1:b2b:statement"))

        assert response.status_code == 200
        assert response.data["closing_balance"] == "0.00"
        assert response.data["entries"] == []

    def test_a_retail_customer_is_refused(self, db):
        customer = User.objects.create_user(email="retail@test.local", password=PASSWORD)
        customer.is_active = True
        customer.save()

        assert client_for(customer).get(reverse("v1:b2b:account")).status_code == 403

    def test_a_trade_account_without_a_profile_gets_a_clear_message(self, db):
        """⚠️  غيابه ليس خطأ خادم — الرسالة تقول ما يفعله."""
        user = User.objects.create_user(
            email="no-profile@test.local", password=PASSWORD, account_type=AccountType.PHARMACY
        )
        user.is_active = True
        user.save()

        response = client_for(user).get(reverse("v1:b2b:account"))

        assert response.status_code == 404
        assert "خدمة العملاء" in response.data["detail"]

    def test_a_pharmacy_cannot_raise_its_own_limit(self, pharmacy):
        """
        ⚠️  حقول الائتمان للقراءة فقط في ملف العميل — وإلا رفع
            حدّه بطلب واحد.
        """
        response = client_for(pharmacy.customer.user).patch(
            reverse("v1:b2b:profile"),
            {"credit_limit": "999999.00", "legal_name": "اسم جديد"},
            format="json",
        )

        assert response.status_code == 200
        pharmacy.refresh_from_db()
        assert pharmacy.credit_limit == Decimal("10000.00")
        assert pharmacy.legal_name == "اسم جديد"

    def test_a_pharmacy_cannot_grant_itself_credit(self, pharmacy):
        response = client_for(pharmacy.customer.user).post(
            reverse("v1:b2b:admin-grant-credit", args=[pharmacy.pk]),
            {"limit": "50000.00", "terms_days": 60},
            format="json",
        )

        assert response.status_code == 403


# ═══════════════════════════════════════════════════════════
#  الواجهات
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAPI:
    def test_the_account_screen_shows_what_is_owed(self, pharmacy):
        order = make_order(pharmacy.customer, "2500.00")
        services.charge_on_credit(pharmacy, order)

        response = client_for(pharmacy.customer.user).get(reverse("v1:b2b:account"))

        assert response.status_code == 200
        assert response.data["outstanding"] == "2500.00"
        assert response.data["available"] == "7500.00"
        assert response.data["overdue_count"] == 0

    def test_credit_check_answers_before_the_cart_is_built(self, pharmacy):
        response = client_for(pharmacy.customer.user).post(
            reverse("v1:b2b:credit-check"), {"amount": "20000.00"}, format="json"
        )

        assert response.status_code == 200
        assert response.data["allowed"] is False
        assert response.data["available"] == "10000.00"

    def test_granting_credit_is_audited(self, pharmacy, manager):
        from core.models.audit import AuditLog

        response = client_for(manager).post(
            reverse("v1:b2b:admin-grant-credit", args=[pharmacy.pk]),
            {"limit": "50000.00", "terms_days": 45, "note": "عميل منتظم"},
            format="json",
        )

        assert response.status_code == 200
        pharmacy.refresh_from_db()
        assert pharmacy.credit_limit == Decimal("50000.00")
        assert pharmacy.payment_terms_days == 45
        assert pharmacy.credit_approved_by == manager

        entry = AuditLog.objects.filter(object_repr__contains=pharmacy.legal_name).first()
        assert entry is not None
        assert entry.changes["limit"]["new"] == "50000.00"

    def test_recording_a_payment_updates_the_balance(self, pharmacy, manager):
        order = make_order(pharmacy.customer, "3000.00")
        services.charge_on_credit(pharmacy, order)

        response = client_for(manager).post(
            reverse("v1:b2b:admin-record-payment", args=[pharmacy.pk]),
            {"amount": "1000.00", "reference": "TRF-991"},
            format="json",
        )

        assert response.status_code == 201
        assert services.outstanding_balance(pharmacy) == Decimal("2000.00")

    def test_due_date_follows_the_agreed_terms(self, pharmacy):
        order = make_order(pharmacy.customer, "1000.00")
        entry = services.charge_on_credit(pharmacy, order)

        assert entry.due_on == timezone.localdate() + timedelta(days=30)
        assert Invoice.objects.get(order=order).due_on == entry.due_on


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_orders_cannot_both_pass_the_limit():
    """
    ⚠️  **السباق الذي يبرّر `select_for_update`.**

        بلا قفل يقرأ كل طلب رصيدًا قبل أن يكتب الآخر، فيمرّان معًا
        ويتجاوز مجموعهما الحد. وهذا **ليس نادرًا** في B2B: نقرة
        مزدوجة على زر الإتمام تكفي.

        الاختبار يشغّل خيطين حقيقيين بمعاملتين حقيقيتين — لا
        محاكاة — فحدّ ٥٠٠٠ وطلبان بـ٣٠٠٠ يجب أن يمرّ أحدهما فقط.
    """
    import threading

    from django.db import connections

    business = make_business("race@test.local", limit="5000.00")
    orders = [make_order(business.customer, "3000.00") for _ in range(2)]

    results: list[str] = []
    #: ⚠️  مهلة سخيّة عمدًا.
    #
    #     خمس ثوانٍ كانت تكفي وحده، وتنكسر حين تعمل المجموعة
    #     كاملةً على جهاز محمَّل: يتأخر إقلاع الخيط فينكسر الحاجز،
    #     فيُحسب الخطأ «رفضًا» ويسقط الاختبار **بلا علاقة بالقفل**.
    #     الفشل الكاذب في اختبار تزامن أسوأ من غيابه: يُفقد الثقة
    #     فيه فيُتجاهَل حين يصطاد خطأ حقيقيًا.
    barrier = threading.Barrier(2)
    barrier_timeout = 30

    def attempt(order):
        try:
            barrier.wait(timeout=barrier_timeout)
        except threading.BrokenBarrierError:
            # ⚠️  يُميَّز صراحةً: هذا عطل في التزامن نفسه لا نتيجة
            #     من نتائج الاختبار، ويُقال كذلك في رسالة الفشل.
            results.append("barrier-broken")
            connections.close_all()
            return

        try:
            services.charge_on_credit(business, order)
            results.append("ok")
        except BusinessError:
            results.append("refused")
        except Exception as failure:
            results.append(f"error:{failure}")
        finally:
            connections.close_all()

    threads = [threading.Thread(target=attempt, args=(order,)) for order in orders]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    if "barrier-broken" in results:
        pytest.skip(f"تعذّر تزامن الخيطين على هذا الجهاز: {results}")

    assert results.count("ok") == 1, f"مرّ أكثر من طلب: {results}"
    assert results.count("refused") == 1, f"النتائج: {results}"
    assert services.outstanding_balance(business) == Decimal("3000.00")


@pytest.mark.django_db
def test_quick_reorder_ranks_by_frequency_not_recency(pharmacy):
    """
    ⚠️  الصيدلية تعيد طلب نفس الأصناف كل أسبوعين.

        «آخر طلب» يعطي طلبًا واحدًا قد يكون استثنائيًا؛ والتكرار
        يعطي سلّتها المعتادة فعلًا.
    """
    from catalog.models import Category, Product
    from orders.models import OrderLine

    category = Category.objects.create(slug="b2b", name_ar="فئة", name_en="Cat")
    staple = Product.objects.create(
        sku="STAPLE", name_ar="أساسي", name_en="Staple", category=category, base_price=10
    )
    oneoff = Product.objects.create(
        sku="ONEOFF", name_ar="نادر", name_en="Rare", category=category, base_price=10
    )

    for _ in range(3):
        order = make_order(pharmacy.customer, "100.00")
        order.status = OrderStatus.DELIVERED
        order.save()
        OrderLine.objects.create(
            order=order,
            product=staple,
            product_sku=staple.sku,
            product_name_ar=staple.name_ar,
            product_name_en=staple.name_en,
            quantity=5,
            unit_price=Decimal("10.00"),
            list_price=Decimal("10.00"),
        )

    recent = make_order(pharmacy.customer, "100.00")
    recent.status = OrderStatus.DELIVERED
    recent.save()
    OrderLine.objects.create(
        order=recent,
        product=oneoff,
        product_sku=oneoff.sku,
        product_name_ar=oneoff.name_ar,
        product_name_en=oneoff.name_en,
        quantity=99,
        unit_price=Decimal("10.00"),
        list_price=Decimal("10.00"),
    )

    rows = services.frequently_ordered(pharmacy.customer)

    assert rows[0]["sku"] == "STAPLE", "الأكثر تكرارًا أولًا لا الأحدث"
