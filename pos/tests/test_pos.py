"""
Point-of-sale tests.

⚠️  The exit gate for phase 7:

        closing a shift **balances arithmetically** · no selling from
        unavailable stock · every POS operation produces an `Order` traceable in
        the same orders system.

    The tests here guard all three, and something finer still: that the cash
    discrepancy is computed from **the drawer movements**, not from the sales —
    or the cashier is accused of a shortfall equal to every card sale.
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
from core.testing import grant_all_domains
from inventory import services as inventory_services
from inventory.models import LocationKind, StockLocation
from orders.models import Order, OrderChannel, OrderStatus, PaymentStatus
from pos import services
from pos.models import CashMovementKind, Register, SessionStatus

PASSWORD = "Str0ng-Test-Pass!23"


# ═══════════════════════════════════════════════════════════
#  Setup
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
    grant_all_domains(user)
    return user


@pytest.fixture
def tax_free(db):
    """
    ⚠️  Zero tax in the financial tests deliberately.

        Round numbers make a failed reconciliation legible: "expected 100 and
        counted 90" is clearer than "114.00 against 102.60".
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
    ⚠️  The two counter gateways — **set up explicitly rather than relying on the seed**.

        A test relying on `seed_dev` fails when the seed changes for a reason
        unrelated to point of sale, and the failure message ("payment method
        unavailable") gives no hint of the cause at all.
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
#  The shift
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSession:
    def test_only_one_open_session_per_register(self, register, cashier, session):
        """
        ⚠️  A register with two open shifts means sales attributed to whichever
            the query prefers — and a reconciliation that never balances.
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
        ⚠️  A repeated close would have rewritten `expected_cash` with a fresh
            snapshot, changing an approved reconciliation retroactively.
        """
        services.close_session(session, counted_cash=Decimal("200.00"), closed_by=cashier)

        with pytest.raises(BusinessError):
            services.close_session(session, counted_cash=Decimal("999.00"), closed_by=cashier)

    def test_closed_session_rejects_cash_movements(self, session, cashier):
        services.close_session(session, counted_cash=Decimal("200.00"), closed_by=cashier)

        with pytest.raises(BusinessError):
            services.record_cash(session, kind=CashMovementKind.PAY_IN, amount=Decimal("10.00"))


# ═══════════════════════════════════════════════════════════
#  Cash reconciliation — the exit gate
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCashReconciliation:
    def test_a_perfect_shift_balances_to_zero(self, session, product, cashier):
        """
        ⚠️  **The first exit gate:** closing a shift balances arithmetically.
        """
        services.checkout(session, [services.SaleLine(product, 2)], [cash("100.00")])

        expected = services.expected_cash_for(session)
        assert expected == Decimal("300.00"), "٢٠٠ افتتاحي + ١٠٠ نقدًا"

        closed = services.close_session(session, counted_cash=Decimal("300.00"), closed_by=cashier)
        assert closed.variance == Decimal("0.00")

    def test_card_sales_do_not_count_as_cash(self, session, product, cashier):
        """
        ⚠️  **The most dangerous trap in the reconciliation.**

            A card sale puts no cash in the drawer. Counting it in the expected
            figure produces a phantom shortfall the size of all card sales — and
            the cashier is accused of something they did not do.
        """
        services.checkout(session, [services.SaleLine(product, 2)], [card("100.00")])

        assert services.expected_cash_for(session) == Decimal("200.00"), "الافتتاحي وحده"

    def test_split_payment_counts_only_the_cash_part(self, session, product, cashier):
        """Half in cash and half by card — a daily occurrence at the counter."""
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
        ⚠️  A discrepancy with no explanation accumulates for months and is then
            discovered as a shortfall nobody can trace — and closing time is the
            only moment the cashier still remembers what happened.
        """
        with pytest.raises(BusinessError) as failure:
            services.close_session(session, counted_cash=Decimal("100.00"), closed_by=cashier)

        # ⚠️  `error_detail`, not `str(exc)`: the latter returns the generic catalogue
        #     message, and the detail is what the cashier actually reads.
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
        """Change short by a few pounds is not an incident deserving an investigation."""
        closed = services.close_session(session, counted_cash=Decimal("195.00"), closed_by=cashier)
        assert closed.variance == Decimal("-5.00")

    def test_variance_is_none_before_closing(self, session):
        """
        ⚠️  Zero reads as "it balanced", and an open shift has not been counted yet.
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
#  Selling — the exit gate
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCheckout:
    def test_a_sale_produces_a_normal_order(self, session, product):
        """
        ⚠️  **The third exit gate:** every POS operation produces an `Order`
            traceable in the same orders system.

            A parallel model would have produced two sales reports, two stock
            figures and two sources of truth.
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
        ⚠️  With no reservation — a counter sale is instantaneous and the goods are handed over at once.
        """
        before = inventory_services.available_quantity(product, location=location)

        services.checkout(session, [services.SaleLine(product, 3)], [cash("150.00")])

        after = inventory_services.available_quantity(product, location=location)
        assert after == before - 3

    def test_selling_more_than_available_is_rejected(self, session, product):
        """⚠️  **The second exit gate:** no selling from unavailable stock."""
        with pytest.raises(BusinessError):
            services.checkout(session, [services.SaleLine(product, 500)], [cash("25000.00")])

    def test_a_rejected_sale_leaves_no_order_and_no_stock_change(self, session, product, location):
        """
        ⚠️  The transaction is atomic: an item running out mid-sale leaves no
            orphan order and no partially deducted stock.
        """
        before = inventory_services.available_quantity(product, location=location)
        orders_before = Order.objects.count()

        with pytest.raises(BusinessError):
            services.checkout(session, [services.SaleLine(product, 500)], [cash("25000.00")])

        assert Order.objects.count() == orders_before
        assert inventory_services.available_quantity(product, location=location) == before

    def test_payments_must_equal_the_total_exactly(self, session, product):
        """
        ⚠️  Less means an unsettled sale recorded as complete; more means a
            surplus the system does not know where to put.
        """
        for amount in ("90.00", "110.00"):
            with pytest.raises(BusinessError) as failure:
                services.checkout(session, [services.SaleLine(product, 2)], [cash(amount)])
            assert "لا يساوي الإجمالي" in failure.value.error_detail

    def test_discount_above_the_cap_is_rejected(self, session, product):
        """
        ⚠️  Business rule 11 — the default is zero: no discount without
            approval. A permissive default opens a door that is hard to close
            once the cashier has grown used to it.
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
        ⚠️  A counter sale requires no account — an order with no owner is the
            normal case in a physical shop, not missing data.
        """
        result = services.checkout(session, [services.SaleLine(product, 1)], [cash("50.00")])
        assert result.order.customer is None


# ═══════════════════════════════════════════════════════════
#  Returns
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRefund:
    def test_refund_returns_stock_and_marks_the_order(self, session, product, location, manager):
        """
        ⚠️  **No deletion.** The sale happened and its tax was collected;
            deleting it erases both from the day's report.
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
        ⚠️  The cash returned leaves as a recorded movement — or the discrepancy
            looks like a shortfall at closing.
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
#  The interface and permissions
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPermissions:
    def test_a_customer_cannot_touch_pos(self, db):
        """⚠️  Point of sale is an internal tool — a customer never reaches it under any circumstances."""
        customer = User.objects.create_user(email="c-pos@test.local", password=PASSWORD)
        customer.is_active = True
        customer.save()

        client = APIClient()
        client.force_authenticate(user=customer)

        assert client.get(reverse("v1:pos:session")).status_code == 403
        assert client.get(reverse("v1:pos:registers")).status_code == 403

    def test_cashier_cannot_refund(self, session, cashier, product):
        """
        ⚠️  The stricter default until business rule 11 is settled: widening it
            is a decision taken explicitly, not inherited from a permissive default.
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
        ⚠️  The shift is derived from **the user**, not from a request parameter.

            Accepting it as an id means a cashier recording a sale on a
            colleague's shift, so the cash is attributed to the wrong person and
            no reconciliation balances.
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
        # No open shift for this user — they do not inherit someone else's shift
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
        ⚠️  Showing the expected figure before the count makes the cashier count
            until it matches — so the reconciliation becomes a formality and the
            discrepancy is always zero.
        """
        client = APIClient()
        client.force_authenticate(user=cashier)

        response = client.get(reverse("v1:pos:session"))
        assert response.data["expected_cash"] is None
        assert response.data["variance"] is None


# ═══════════════════════════════════════════════════════════
#  Search and pricing — what the cashier's screen sees
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
        ⚠️  The scanner sends a complete number.

            Matching it partially returns items whose numbers share a segment —
            so the cashier adds the wrong item with one press and does not notice.
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
        ⚠️  **No policy filtering — and that is deliberate.**

            The pharmacist at the counter sells the restricted item lawfully.
            Hiding it from their terminal means they record it by hand or not at
            all, and either way the stock falls apart. The barrier here is
            `CanOperatePOS`, not the policy.
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
        ⚠️  **This is the test that justifies the endpoint's existence.**

            The figure displayed and the figure charged come out of the same
            function. Their divergence first shows up as a difference between
            the screen and the receipt — and the customer is the one who finds it.
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
        """No stock deducted and no order created — pricing with no effect."""
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
        ⚠️  Refusal at entry, not on the last press.

            Leaving it to checkout alone makes the cashier build a whole sale in
            front of the customer and then be refused — when the discount should
            be blocked the moment it is entered.
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
    """Corrections go through an offsetting movement, not an edit — the log is the basis of the reconciliation."""
    movement = services.record_cash(
        session, kind=CashMovementKind.PAY_IN, amount=Decimal("10.00"), reason="فكّة"
    )

    movement.amount = Decimal("999.00")
    with pytest.raises(ValueError):
        movement.save()


@pytest.mark.django_db
def test_session_closed_event_fires(session, cashier):
    """Finance in phase 8 listens for this event to post the cash."""
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
#  Managing registers — from the panel
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def manager_client(manager):
    """
    ⚠️  **The admin profile no longer opens anything on its own.**

        After the gates were tightened, reviewing shifts and managing registers
        require `pos.view_possession` explicitly; and a manager with no grants
        is answered with 403 — which is exactly the intended behaviour.
    """
    from django.contrib.auth.models import Permission

    manager.user_permissions.add(
        Permission.objects.get(content_type__app_label="pos", codename="view_possession")
    )

    client = APIClient()
    client.force_authenticate(user=manager)
    return client


@pytest.mark.django_db
def test_a_manager_without_the_permission_is_refused(db):
    """
    ⚠️  The gate is tested from the refusal side as well: a grant opens, and its absence closes.

    ⚠️  And a dedicated user rather than the `manager` fixture: that one grants
        the domains in full (feature tests do not test the gate), so it cannot
        prove a denial.
    """
    from administration.models import AdminProfile

    user = User.objects.create_user(
        email="pos-bare@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    user.is_active = True
    user.save()
    AdminProfile.objects.create(user=user)

    client = APIClient()
    client.force_authenticate(user=user)

    assert client.get(reverse("v1:pos:admin-registers")).status_code == 403


@pytest.mark.django_db
class TestRegisterAdmin:
    """
    ⚠️  The exit gate: a register is created, edited and disabled **from the
        screen**, is never deleted, and is not moved while a shift is open on it.
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
        ⚠️  Disabling a register with an open shift leaves cash in a drawer that
            appears on no screen, with no way to close it from the portal afterwards.
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
        ⚠️  Moving it mid-shift makes half the sales deduct from one branch and
            the other half from a second — and nothing in the ledger says where
            the split happened.
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
        """⚠️  The block is conditioned on an open shift, not on having any history."""
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
        """⚠️  Every shift points at it — and deleting severs the branch's history."""
        response = manager_client.delete(
            reverse("v1:pos:admin-register-detail", args=[register.pk])
        )

        assert response.status_code == 405
        assert Register.objects.filter(pk=register.pk).exists()
