"""
اختبارات نقطة البيع.

⚠️  بوابة الخروج للمرحلة ٧:

        إغلاق وردية **يوازن حسابيًا** · لا بيع بمخزون غير متاح ·
        كل عملية POS تنتج `Order` قابلًا للتتبع في نفس نظام الطلبات.

    الاختبارات هنا تحرس الثلاثة، وتحرس ما هو أدقّ منها: أن الفرق
    النقدي يُحسب من **حركات الصندوق** لا من المبيعات — وإلا اتُّهم
    الكاشير بعجز يساوي كل مبيعات البطاقات.
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from administration.models import AdminProfile
from catalog.models import Category, Product
from core.errors import BusinessError
from core.models.settings import SystemSetting
from core.models.tax import TaxClass
from inventory import services as inventory_services
from inventory.models import LocationKind, StockLocation
from orders.models import Order, OrderChannel, OrderStatus, PaymentStatus
from pos import services
from pos.models import CashMovementKind, Register, SessionStatus

PASSWORD = "Str0ng-Test-Pass!23"


# ═══════════════════════════════════════════════════════════
#  التجهيز
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def location(db):
    return StockLocation.objects.create(
        code="branch-1",
        name_ar="فرع",
        name_en="Branch",
        kind=LocationKind.BRANCH,
        is_default=True,
        is_sellable=True,
    )


@pytest.fixture
def register(location):
    return Register.objects.create(
        code="reg-1", name_ar="كاونتر ١", name_en="Counter 1", location=location
    )


@pytest.fixture
def cashier(db):
    user = User.objects.create_user(
        email="cashier@test.local", password=PASSWORD, account_type=AccountType.EMPLOYEE
    )
    user.is_active = True
    user.first_name = "ياسمين"
    user.save()
    return user


@pytest.fixture
def manager(db):
    user = User.objects.create_user(
        email="pos-manager@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    user.is_active = True
    user.save()
    AdminProfile.objects.create(user=user)
    return user


@pytest.fixture
def tax_free(db):
    """
    ⚠️  ضريبة صفرية في الاختبارات المالية عمدًا.

        الأرقام المستديرة تجعل فشل التسوية مقروءًا: «توقّعت ١٠٠
        وعددت ٩٠» أوضح من «١١٤.٠٠ مقابل ١٠٢.٦٠».
    """
    SystemSetting.set("tax.enabled", False, value_type="BOOL", label_ar="ض", label_en="t")
    TaxClass.objects.create(
        code="zero", name_ar="صفري", name_en="Zero", rate=Decimal("0"), is_default=True
    )


@pytest.fixture
def product(db, tax_free, location):
    category = Category.objects.create(slug="c", name_ar="فئة", name_en="Cat")
    item = Product.objects.create(
        sku="POS-1",
        name_ar="صنف",
        name_en="Item",
        category=category,
        base_price=Decimal("50.00"),
    )
    inventory_services.receive(item, 100, Decimal("30.00"), location=location)
    return item


@pytest.fixture(autouse=True)
def pos_payment_providers(db):
    """
    ⚠️  بوابتا الكاونتر — **تجهيز صريح لا اعتماد على البذرة**.

        الاختبار الذي يعتمد على `seed_dev` يفشل حين تتغيّر البذرة
        لسبب لا علاقة له بنقطة البيع، ورسالة الفشل («طريقة الدفع
        غير متاحة») لا تدلّ على السبب إطلاقًا.
    """
    from payments.models import PaymentMethodKind, PaymentProvider

    PaymentProvider.objects.create(
        code="pos-cash",
        adapter_key="cash",
        name_ar="نقدي",
        name_en="Cash",
        supported_methods=[PaymentMethodKind.CASH],
        supported_channels=["POS"],
        priority=100,
        is_active=True,
        is_sandbox=False,
    )
    PaymentProvider.objects.create(
        code="pos-card",
        adapter_key="cash",
        name_ar="بطاقة على الطرفية",
        name_en="Card terminal",
        supported_methods=[PaymentMethodKind.CARD],
        supported_channels=["POS"],
        priority=90,
        is_active=True,
        is_sandbox=False,
    )


@pytest.fixture
def session(register, cashier):
    return services.open_session(register, cashier, opening_float=Decimal("200.00"))


def cash(amount: str):
    return services.SplitPayment(method="CASH", amount=Decimal(amount))


def card(amount: str):
    return services.SplitPayment(method="CARD", amount=Decimal(amount))


# ═══════════════════════════════════════════════════════════
#  الوردية
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSession:
    def test_only_one_open_session_per_register(self, register, cashier, session):
        """
        ⚠️  جهاز بورديتين مفتوحتين يعني بيعات تُنسب لأيّهما شاء
            الاستعلام — وتسوية لا توازن أبدًا.
        """
        with pytest.raises(BusinessError):
            services.open_session(register, cashier)

    def test_closed_register_reopens_fine(self, register, cashier, session):
        services.close_session(session, counted_cash=Decimal("200.00"), closed_by=cashier)

        second = services.open_session(register, cashier)
        assert second.is_open

    def test_inactive_register_cannot_open(self, register, cashier):
        register.is_active = False
        register.save()

        with pytest.raises(BusinessError):
            services.open_session(register, cashier)

    def test_closed_session_cannot_close_twice(self, session, cashier):
        """
        ⚠️  الإغلاق المكرر كان سيعيد كتابة `expected_cash` بلقطة
            جديدة، فتتغيّر تسوية مُعتمدة بأثر رجعي.
        """
        services.close_session(session, counted_cash=Decimal("200.00"), closed_by=cashier)

        with pytest.raises(BusinessError):
            services.close_session(session, counted_cash=Decimal("999.00"), closed_by=cashier)

    def test_closed_session_rejects_cash_movements(self, session, cashier):
        services.close_session(session, counted_cash=Decimal("200.00"), closed_by=cashier)

        with pytest.raises(BusinessError):
            services.record_cash(session, kind=CashMovementKind.PAY_IN, amount=Decimal("10.00"))


# ═══════════════════════════════════════════════════════════
#  التسوية النقدية — بوابة الخروج
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCashReconciliation:
    def test_a_perfect_shift_balances_to_zero(self, session, product, cashier):
        """
        ⚠️  **بوابة الخروج الأولى:** إغلاق وردية يوازن حسابيًا.
        """
        services.checkout(session, [services.SaleLine(product, 2)], [cash("100.00")])

        expected = services.expected_cash_for(session)
        assert expected == Decimal("300.00"), "٢٠٠ افتتاحي + ١٠٠ نقدًا"

        closed = services.close_session(session, counted_cash=Decimal("300.00"), closed_by=cashier)
        assert closed.variance == Decimal("0.00")

    def test_card_sales_do_not_count_as_cash(self, session, product, cashier):
        """
        ⚠️  **الفخّ الأخطر في التسوية.**

            بيعة بالبطاقة لا تضع نقدًا في الدرج. حسابها ضمن
            المتوقَّع يُنتج عجزًا وهميًا بحجم كل مبيعات البطاقات —
            ويُتَّهم الكاشير بما لم يفعله.
        """
        services.checkout(session, [services.SaleLine(product, 2)], [card("100.00")])

        assert services.expected_cash_for(session) == Decimal("200.00"), "الافتتاحي وحده"

    def test_split_payment_counts_only_the_cash_part(self, session, product, cashier):
        """نصفها نقدًا ونصفها بالبطاقة — حالة يومية على الكاونتر."""
        services.checkout(
            session,
            [services.SaleLine(product, 4)],
            [cash("120.00"), card("80.00")],
        )

        assert services.expected_cash_for(session) == Decimal("320.00")

    def test_pay_out_reduces_expected_cash(self, session, cashier):
        services.record_cash(
            session,
            kind=CashMovementKind.PAY_OUT,
            amount=Decimal("50.00"),
            reason="شراء أكياس",
        )

        assert services.expected_cash_for(session) == Decimal("150.00")

    def test_shortage_above_threshold_requires_an_explanation(self, session, cashier):
        """
        ⚠️  فرق بلا تفسير يتراكم شهورًا ثم يُكتشف كعجز لا يعرف أحد
            مصدره — والتفسير وقت الإغلاق هو الوقت الوحيد الذي
            يتذكّر فيه الكاشير ما جرى.
        """
        with pytest.raises(BusinessError) as failure:
            services.close_session(session, counted_cash=Decimal("100.00"), closed_by=cashier)

        # ⚠️  `error_detail` لا `str(exc)`: الثاني يعيد رسالة الكتالوج
        #     العامة، والتفصيل هو ما يقرأه الكاشير فعلًا.
        assert "التفسير إلزامي" in failure.value.error_detail

    def test_shortage_with_an_explanation_is_accepted(self, session, cashier):
        closed = services.close_session(
            session,
            counted_cash=Decimal("100.00"),
            closed_by=cashier,
            variance_note="سُلّم مبلغ للمورّد بلا إيصال",
        )

        assert closed.variance == Decimal("-100.00")
        assert closed.variance_note

    def test_small_difference_needs_no_explanation(self, session, cashier):
        """فكّة ناقصة بجنيهات ليست حادثة تستحق تحقيقًا."""
        closed = services.close_session(session, counted_cash=Decimal("195.00"), closed_by=cashier)
        assert closed.variance == Decimal("-5.00")

    def test_variance_is_none_before_closing(self, session):
        """
        ⚠️  الصفر يُقرأ «وازنت»، والوردية المفتوحة لم تُعدّ بعد.
        """
        assert session.variance is None

    def test_threshold_is_configurable_from_settings(self, session, cashier):
        SystemSetting.set(
            services.VARIANCE_THRESHOLD,
            "500",
            value_type="DECIMAL",
            label_ar="ح",
            label_en="t",
        )

        closed = services.close_session(session, counted_cash=Decimal("0.00"), closed_by=cashier)
        assert closed.variance == Decimal("-200.00")


# ═══════════════════════════════════════════════════════════
#  البيع — بوابة الخروج
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCheckout:
    def test_a_sale_produces_a_normal_order(self, session, product):
        """
        ⚠️  **بوابة الخروج الثالثة:** كل عملية POS تنتج `Order`
            قابلًا للتتبع في نفس نظام الطلبات.

            النموذج الموازي كان سينتج تقريرَي مبيعات ومخزونين
            ومصدرَي حقيقة.
        """
        result = services.checkout(session, [services.SaleLine(product, 2)], [cash("100.00")])

        order = Order.objects.get(pk=result.order.pk)
        assert order.channel == OrderChannel.POS
        assert order.status == OrderStatus.DELIVERED
        assert order.payment_status == PaymentStatus.PAID
        assert order.location == session.register.location
        assert order.lines.count() == 1

    def test_stock_is_deducted_immediately(self, session, product, location):
        """
        ⚠️  بلا حجز — البيع على الكاونتر لحظي والبضاعة تُسلَّم فورًا.
        """
        before = inventory_services.available_quantity(product, location=location)

        services.checkout(session, [services.SaleLine(product, 3)], [cash("150.00")])

        after = inventory_services.available_quantity(product, location=location)
        assert after == before - 3

    def test_selling_more_than_available_is_rejected(self, session, product):
        """⚠️  **بوابة الخروج الثانية:** لا بيع بمخزون غير متاح."""
        with pytest.raises(BusinessError):
            services.checkout(session, [services.SaleLine(product, 500)], [cash("25000.00")])

    def test_a_rejected_sale_leaves_no_order_and_no_stock_change(self, session, product, location):
        """
        ⚠️  المعاملة ذرّية: نفاد صنف في منتصف بيعة لا يترك طلبًا
            يتيمًا ولا مخزونًا مخصومًا جزئيًا.
        """
        before = inventory_services.available_quantity(product, location=location)
        orders_before = Order.objects.count()

        with pytest.raises(BusinessError):
            services.checkout(session, [services.SaleLine(product, 500)], [cash("25000.00")])

        assert Order.objects.count() == orders_before
        assert inventory_services.available_quantity(product, location=location) == before

    def test_payments_must_equal_the_total_exactly(self, session, product):
        """
        ⚠️  الأقل يعني بيعة غير مسدَّدة تُسجَّل كمكتملة؛ والأكثر
            يعني فائضًا لا يعرف النظام أين يذهب.
        """
        for amount in ("90.00", "110.00"):
            with pytest.raises(BusinessError) as failure:
                services.checkout(session, [services.SaleLine(product, 2)], [cash(amount)])
            assert "لا يساوي الإجمالي" in failure.value.error_detail

    def test_discount_above_the_cap_is_rejected(self, session, product):
        """
        ⚠️  قاعدة العمل ١١ — الافتراضي صفر: لا خصم بلا اعتماد.
            الافتراضي المتساهل يفتح بابًا يصعب إغلاقه بعد أن يعتاده
            الكاشير.
        """
        with pytest.raises(BusinessError) as failure:
            services.checkout(
                session,
                [services.SaleLine(product, 2)],
                [cash("90.00")],
                discount_percent=Decimal("10"),
            )
        assert "يتجاوز السقف" in failure.value.error_detail

    def test_discount_within_a_raised_cap_is_allowed(self, session, product):
        SystemSetting.set(
            services.MAX_DISCOUNT_PERCENT,
            "10",
            value_type="DECIMAL",
            label_ar="س",
            label_en="c",
        )

        result = services.checkout(
            session,
            [services.SaleLine(product, 2)],
            [cash("90.00")],
            discount_percent=Decimal("10"),
        )
        assert result.order.grand_total == Decimal("90.00")

    def test_selling_on_a_closed_session_is_rejected(self, session, product, cashier):
        services.close_session(session, counted_cash=Decimal("200.00"), closed_by=cashier)

        with pytest.raises(BusinessError):
            services.checkout(session, [services.SaleLine(product, 1)], [cash("50.00")])

    def test_a_walk_in_sale_needs_no_customer(self, session, product):
        """
        ⚠️  البيع على الكاونتر لا يستلزم حسابًا — الطلب بلا مالك
            هو الحال الطبيعي في متجر فعلي لا نقص في البيانات.
        """
        result = services.checkout(session, [services.SaleLine(product, 1)], [cash("50.00")])
        assert result.order.customer is None


# ═══════════════════════════════════════════════════════════
#  المرتجع
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRefund:
    def test_refund_returns_stock_and_marks_the_order(self, session, product, location, manager):
        """
        ⚠️  **لا حذف.** البيعة وقعت وضريبتها حُصّلت؛ حذفها يمحو
            الاثنين من تقرير اليوم.
        """
        result = services.checkout(session, [services.SaleLine(product, 2)], [cash("100.00")])
        after_sale = inventory_services.available_quantity(product, location=location)

        services.refund_sale(
            session,
            result.order,
            reason="الصنف تالف",
            cash_amount=Decimal("100.00"),
            performed_by=manager,
        )

        order = Order.objects.get(pk=result.order.pk)
        assert order.status == OrderStatus.REFUNDED
        assert inventory_services.available_quantity(product, location=location) == (after_sale + 2)

    def test_cash_refund_leaves_the_drawer(self, session, product, manager):
        """
        ⚠️  النقد المُعاد يخرج بحركة مسجَّلة — وإلا بدا الفرق عجزًا
            عند الإغلاق.
        """
        result = services.checkout(session, [services.SaleLine(product, 2)], [cash("100.00")])
        assert services.expected_cash_for(session) == Decimal("300.00")

        services.refund_sale(
            session,
            result.order,
            reason="مرتجع",
            cash_amount=Decimal("100.00"),
            performed_by=manager,
        )

        assert services.expected_cash_for(session) == Decimal("200.00")

    def test_double_refund_is_rejected(self, session, product, manager):
        result = services.checkout(session, [services.SaleLine(product, 1)], [cash("50.00")])
        services.refund_sale(session, result.order, reason="مرتجع", performed_by=manager)

        with pytest.raises(BusinessError) as failure:
            services.refund_sale(session, result.order, reason="مرتجع ثانٍ", performed_by=manager)
        assert "مسترد بالفعل" in failure.value.error_detail


# ═══════════════════════════════════════════════════════════
#  الواجهة والصلاحيات
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPermissions:
    def test_a_customer_cannot_touch_pos(self, db):
        """⚠️  نقطة البيع أداة داخلية — العميل لا يصل إليها مهما كان."""
        customer = User.objects.create_user(email="c-pos@test.local", password=PASSWORD)
        customer.is_active = True
        customer.save()

        client = APIClient()
        client.force_authenticate(user=customer)

        assert client.get(reverse("v1:pos:session")).status_code == 403
        assert client.get(reverse("v1:pos:registers")).status_code == 403

    def test_cashier_cannot_refund(self, session, cashier, product):
        """
        ⚠️  الافتراضي الأشدّ حتى تُحسم قاعدة العمل ١١: توسيعه قرار
            يُتخذ صراحةً لا يُورَث من افتراضي متساهل.
        """
        result = services.checkout(session, [services.SaleLine(product, 1)], [cash("50.00")])

        client = APIClient()
        client.force_authenticate(user=cashier)

        response = client.post(
            reverse("v1:pos:refund"),
            {"order": str(result.order.pk), "reason": "مرتجع"},
            format="json",
        )
        assert response.status_code == 403

    def test_a_cashier_cannot_sell_on_another_cashiers_session(
        self, register, session, product, db
    ):
        """
        ⚠️  الوردية تُستخرج من **المستخدم** لا من مُعامل الطلب.

            قبولها كمعرّف يعني كاشيرًا يسجّل بيعة على وردية زميله،
            فتُنسب النقدية للشخص الخطأ ولا توازن أي تسوية.
        """
        other = User.objects.create_user(
            email="other-cashier@test.local",
            password=PASSWORD,
            account_type=AccountType.EMPLOYEE,
        )
        other.is_active = True
        other.save()

        client = APIClient()
        client.force_authenticate(user=other)

        response = client.post(
            reverse("v1:pos:checkout"),
            {
                "lines": [{"product": str(product.pk), "quantity": 1}],
                "payments": [{"method": "CASH", "amount": "50.00"}],
            },
            format="json",
        )
        # لا وردية مفتوحة لهذا المستخدم — لا يرث وردية غيره
        assert response.status_code == 409

    def test_full_flow_through_the_api(self, register, cashier, product):
        client = APIClient()
        client.force_authenticate(user=cashier)

        opened = client.post(
            reverse("v1:pos:session-open"),
            {"register": str(register.pk), "opening_float": "100.00"},
            format="json",
        )
        assert opened.status_code == 201

        sale = client.post(
            reverse("v1:pos:checkout"),
            {
                "lines": [{"product": str(product.pk), "quantity": 2}],
                "payments": [{"method": "CASH", "amount": "100.00"}],
            },
            format="json",
        )
        assert sale.status_code == 201, sale.data
        assert sale.data["order"]["channel"] == OrderChannel.POS

        closed = client.post(
            reverse("v1:pos:session-close"), {"counted_cash": "200.00"}, format="json"
        )
        assert closed.status_code == 200
        assert closed.data["variance"] == "0.00"

    def test_expected_cash_is_hidden_until_closing(self, session, cashier):
        """
        ⚠️  عرض المتوقَّع قبل العدّ يجعل الكاشير يعدّ حتى يطابقه —
            فتصير التسوية شكلية والفرق صفرًا دائمًا.
        """
        client = APIClient()
        client.force_authenticate(user=cashier)

        response = client.get(reverse("v1:pos:session"))
        assert response.data["expected_cash"] is None
        assert response.data["variance"] is None


# ═══════════════════════════════════════════════════════════
#  البحث والتسعير — ما تراه شاشة الكاشير
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def cashier_client(cashier):
    client = APIClient()
    client.force_authenticate(user=cashier)
    return client


@pytest.mark.django_db
class TestProductSearch:
    def test_barcode_returns_an_exact_match_only(self, cashier_client, product):
        """
        ⚠️  الماسح يرسل رقمًا كاملًا.

            مطابقته جزئيًا تعيد أصنافًا يشترك رقمها في مقطع —
            فيضيف الكاشير الصنف الخطأ بضغطة واحدة ولا يلاحظ.
        """
        product.barcode = "6221001"
        product.save()
        Product.objects.create(
            sku="POS-2",
            name_ar="آخر",
            name_en="Other",
            category=product.category,
            base_price=Decimal("10.00"),
            barcode="62210019",
        )

        response = cashier_client.get(reverse("v1:pos:products"), {"search": "6221001"})

        assert response.status_code == 200
        assert [row["sku"] for row in response.data] == ["POS-1"]

    def test_name_search_is_partial(self, cashier_client, product):
        response = cashier_client.get(reverse("v1:pos:products"), {"search": "صن"})

        assert [row["sku"] for row in response.data] == ["POS-1"]

    def test_restricted_products_are_visible_to_the_cashier(self, cashier_client, product):
        """
        ⚠️  **بلا فلترة سياسات — وهذا مقصود.**

            الصيدلي على الكاونتر يبيع المقيّد قانونًا. إخفاؤه عن
            جهازه يعني أن يسجّله يدويًا أو لا يسجّله، وفي الحالتين
            ينهار المخزون. الحاجز هنا `CanOperatePOS` لا السياسة.
        """
        from django.core.management import call_command

        from access.models import AccessPolicy

        call_command("seed_access_policies", verbosity=0)
        restricted = Product.objects.create(
            sku="POS-RX",
            name_ar="دواء مقيّد",
            name_en="Restricted",
            category=product.category,
            base_price=Decimal("80.00"),
            access_policy=AccessPolicy.objects.get(code="pharmacy_only"),
        )

        response = cashier_client.get(reverse("v1:pos:products"), {"search": "مقيّد"})

        assert [row["sku"] for row in response.data] == [restricted.sku]

    def test_customer_cannot_search(self, db, product):
        customer = User.objects.create_user(email="c-search@test.local", password=PASSWORD)
        customer.is_active = True
        customer.save()

        client = APIClient()
        client.force_authenticate(user=customer)

        assert client.get(reverse("v1:pos:products")).status_code == 403


@pytest.mark.django_db
class TestQuote:
    def test_quote_total_equals_what_checkout_charges(self, cashier_client, session, product):
        """
        ⚠️  **هذا هو الاختبار الذي يبرّر وجود النقطة.**

            الرقم المعروض والرقم المحصَّل يخرجان من نفس الدالة.
            انفصالهما يظهر أولًا كفرق بين الشاشة والإيصال — والعميل
            هو من يكتشفه.
        """
        payload = {"lines": [{"product": str(product.pk), "quantity": 3}]}

        quoted = cashier_client.post(reverse("v1:pos:quote"), payload, format="json")
        assert quoted.status_code == 200

        total = quoted.data["total"]
        sale = cashier_client.post(
            reverse("v1:pos:checkout"),
            {**payload, "payments": [{"method": "CASH", "amount": total}]},
            format="json",
        )

        assert sale.status_code == 201, sale.data
        assert sale.data["order"]["grand_total"] == total

    def test_quote_changes_nothing(self, cashier_client, session, product):
        """لا مخزون يُخصم ولا طلب يُنشأ — التسعير بلا أثر."""
        before = Order.objects.count()

        cashier_client.post(
            reverse("v1:pos:quote"),
            {"lines": [{"product": str(product.pk), "quantity": 2}]},
            format="json",
        )

        assert Order.objects.count() == before
        assert session.cash_movements.count() == 0

    def test_discount_above_the_cap_is_rejected_at_quote_time(
        self, cashier_client, session, product
    ):
        """
        ⚠️  الرفض عند الإدخال لا عند آخر ضغطة.

            تركه للإتمام وحده يجعل الكاشير يبني بيعة كاملة أمام
            العميل ثم يُرفض — والأصل أن يُمنع الخصم لحظة إدخاله.
        """
        response = cashier_client.post(
            reverse("v1:pos:quote"),
            {
                "lines": [{"product": str(product.pk), "quantity": 1}],
                "discount_percent": "50.00",
            },
            format="json",
        )

        assert response.status_code == 403

    def test_quote_needs_an_open_session(self, db, product, cashier):
        client = APIClient()
        client.force_authenticate(user=cashier)

        response = client.post(
            reverse("v1:pos:quote"),
            {"lines": [{"product": str(product.pk), "quantity": 1}]},
            format="json",
        )

        assert response.status_code == 409

    def test_unknown_product_is_a_clear_404(self, cashier_client, session):
        import uuid

        response = cashier_client.post(
            reverse("v1:pos:quote"),
            {"lines": [{"product": str(uuid.uuid4()), "quantity": 1}]},
            format="json",
        )

        assert response.status_code == 404


@pytest.mark.django_db
def test_cash_movements_are_append_only(session):
    """التصحيح بحركة معاكسة لا بتحرير — السجل أساس التسوية."""
    movement = services.record_cash(
        session, kind=CashMovementKind.PAY_IN, amount=Decimal("10.00"), reason="فكّة"
    )

    movement.amount = Decimal("999.00")
    with pytest.raises(ValueError):
        movement.save()


@pytest.mark.django_db
def test_session_closed_event_fires(session, cashier):
    """المالية في المرحلة ٨ تستمع لهذا الحدث لتقيّد النقد."""
    from pos.events import pos_session_closed

    received = []

    def listener(sender, session, **kwargs):
        received.append(session)

    pos_session_closed.connect(listener, weak=False)
    try:
        services.close_session(session, counted_cash=Decimal("200.00"), closed_by=cashier)
    finally:
        pos_session_closed.disconnect(listener)

    assert len(received) == 1
    assert received[0].status == SessionStatus.CLOSED


# ═══════════════════════════════════════════════════════════
#  إدارة الكاونترات — من اللوحة
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def manager_client(manager):
    client = APIClient()
    client.force_authenticate(user=manager)
    return client


@pytest.mark.django_db
class TestRegisterAdmin:
    """
    ⚠️  بوابة الخروج: الكاونتر يُنشأ ويُعدَّل ويُوقَف **من الشاشة**،
        ولا يُحذف، ولا يُنقل ووردية مفتوحة عليه.
    """

    def test_creating_a_register_from_the_panel(self, manager_client, location):
        response = manager_client.post(
            reverse("v1:pos:admin-registers"),
            {
                "code": "reg-new",
                "name_ar": "كاونتر جديد",
                "name_en": "New counter",
                "location": str(location.pk),
                "is_active": True,
            },
            format="json",
        )

        assert response.status_code == 201, response.data
        assert Register.objects.filter(code="reg-new").exists()

    def test_renaming_and_deactivating(self, manager_client, register):
        url = reverse("v1:pos:admin-register-detail", args=[register.pk])

        response = manager_client.patch(url, {"name_ar": "كاونتر معدَّل"}, format="json")
        assert response.status_code == 200
        assert response.data["name_ar"] == "كاونتر معدَّل"

        response = manager_client.patch(url, {"is_active": False}, format="json")
        assert response.status_code == 200

        register.refresh_from_db()
        assert register.is_active is False

    def test_an_open_session_blocks_deactivation(self, manager_client, register, session):
        """
        ⚠️  إيقاف كاونتر بوردية مفتوحة يترك نقدًا في درج لا يظهر
            في أي شاشة، ولا سبيل لإقفاله بعدها من البوابة.
        """
        response = manager_client.patch(
            reverse("v1:pos:admin-register-detail", args=[register.pk]),
            {"is_active": False},
            format="json",
        )

        assert response.status_code == 409
        register.refresh_from_db()
        assert register.is_active is True

    def test_an_open_session_blocks_moving_the_location(
        self, manager_client, register, session, db
    ):
        """
        ⚠️  النقل أثناء وردية يجعل نصف البيعات تخصم من فرع والنصف
            الآخر من فرع ثانٍ — ولا شيء في الدفتر يقول أين وقع
            الانقسام.
        """
        other = StockLocation.objects.create(
            code="branch-2",
            name_ar="فرع ثانٍ",
            name_en="Branch 2",
            kind=LocationKind.BRANCH,
            is_sellable=True,
        )

        response = manager_client.patch(
            reverse("v1:pos:admin-register-detail", args=[register.pk]),
            {"location": str(other.pk)},
            format="json",
        )

        assert response.status_code == 409

    def test_a_closed_register_still_moves(self, manager_client, register, location):
        """⚠️  المنع مشروط بالوردية المفتوحة لا بوجود تاريخ."""
        other = StockLocation.objects.create(
            code="branch-3",
            name_ar="فرع ثالث",
            name_en="Branch 3",
            kind=LocationKind.BRANCH,
            is_sellable=True,
        )

        response = manager_client.patch(
            reverse("v1:pos:admin-register-detail", args=[register.pk]),
            {"location": str(other.pk)},
            format="json",
        )

        assert response.status_code == 200

    def test_the_register_is_never_deleted(self, manager_client, register):
        """⚠️  كل وردية تشير إليه — والحذف يقطع تاريخ الفرع."""
        response = manager_client.delete(
            reverse("v1:pos:admin-register-detail", args=[register.pk])
        )

        assert response.status_code == 405
        assert Register.objects.filter(pk=register.pk).exists()
