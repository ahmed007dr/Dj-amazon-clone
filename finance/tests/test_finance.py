"""
Finance tests.

⚠️  The exit gate for phase 8:

        the P&L **balances** against the orders and expenses data ·
        every number is traceable to its source · no black-box calculation.

    And the greatest dangers these tests guard are not the equation but what
    surrounds it: an order's revenue being counted twice · tax being counted as
    profit · goods of unknown cost being read as though they were free.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from administration.models import AdminProfile
from core.testing import grant_all_domains
from catalog.models import Category, Product
from core.errors import BusinessError
from core.models.settings import SystemSetting
from core.models.tax import TaxClass
from finance import services
from finance.models import (
    COGSEntry,
    Expense,
    ExpenseCategory,
    ExpenseStatus,
    FiscalPeriod,
    RevenueEntry,
    RevenueSource,
)
from inventory import services as inventory_services
from inventory.models import LocationKind, StockLocation
from orders.models import Order, OrderChannel, OrderStatus, PaymentStatus

PASSWORD = "Str0ng-Test-Pass!23"


# ═══════════════════════════════════════════════════════════
#  Setup
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def tax_free(db):
    """Round numbers, so a failure of the equation is legible."""
    SystemSetting.set("tax.enabled", False, value_type="BOOL", label_ar="ض", label_en="t")
    TaxClass.objects.create(
        code="zero", name_ar="صفري", name_en="Zero", rate=Decimal("0"), is_default=True
    )


@pytest.fixture
def location(db):
    return StockLocation.objects.create(
        code="fin-loc",
        name_ar="مخزن",
        name_en="Store",
        kind=LocationKind.WAREHOUSE,
        is_default=True,
        is_sellable=True,
    )


@pytest.fixture
def product(db, tax_free, location):
    """An item costing 30 and selling at 50 — a margin of 20 per unit."""
    category = Category.objects.create(slug="fin", name_ar="فئة", name_en="Cat")
    item = Product.objects.create(
        sku="FIN-1",
        name_ar="صنف",
        name_en="Item",
        category=category,
        base_price=Decimal("50.00"),
    )
    inventory_services.receive(item, 100, Decimal("30.00"), location=location)
    return item


@pytest.fixture
def staff(db):
    user = User.objects.create_user(
        email="fin-staff@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    user.is_active = True
    user.save()
    AdminProfile.objects.create(user=user)
    grant_all_domains(user)
    return user


@pytest.fixture
def category(db):
    return ExpenseCategory.objects.create(code="rent", name_ar="إيجار", name_en="Rent")


def make_order(location, *, subtotal="100.00", tax="0.00", discount="0.00", channel="ONLINE"):
    """A direct order — bypassing the state machine, to test the capture alone."""
    subtotal_d = Decimal(subtotal)
    grand = subtotal_d + Decimal(tax) - Decimal(discount)
    return Order.objects.create(
        channel=channel,
        location=location,
        status=OrderStatus.PENDING,
        payment_status=PaymentStatus.PAID,
        subtotal=subtotal_d,
        discount_total=Decimal(discount),
        tax_total=Decimal(tax),
        grand_total=grand,
        completed_at=timezone.now(),
    )


# ═══════════════════════════════════════════════════════════
#  Revenue capture
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRevenueCapture:
    def test_completed_order_creates_one_entry(self, location):
        order = make_order(location)

        services.record_order_revenue(order)

        assert RevenueEntry.objects.filter(order=order).count() == 1

    def test_the_same_order_is_never_counted_twice(self, location):
        """
        ⚠️  **The most dangerous possible defect in this domain.**

            `order_completed` is emitted twice by a retry, a manual correction,
            or a listener registered twice. And with no guard the report says
            double what was sold — discovered only by a manual reconciliation.
        """
        order = make_order(location)

        services.record_order_revenue(order)
        services.record_order_revenue(order)
        services.record_order_revenue(order)

        assert RevenueEntry.objects.filter(order=order).count() == 1

    def test_duplicate_is_blocked_by_the_database_not_only_by_code(self, location):
        """A check in code loses the race; the unique constraint settles it."""
        from django.db import IntegrityError, transaction

        order = make_order(location)
        services.record_order_revenue(order)

        with pytest.raises(IntegrityError), transaction.atomic():
            RevenueEntry.objects.create(
                source=RevenueSource.ORDER,
                order=order,
                gross=Decimal("1.00"),
                net=Decimal("1.00"),
                occurred_on=date.today(),
            )

    def test_tax_is_not_revenue(self, location):
        """
        ⚠️  The store collects the tax on the state's behalf and does not own it.

            Counting it as revenue inflates the profit by its full rate — an
            error that passes silently because the number looks larger, not smaller.
        """
        order = make_order(location, subtotal="100.00", tax="14.00")

        entry = services.record_order_revenue(order)

        assert entry.gross == Decimal("100.00")
        assert entry.tax == Decimal("14.00")
        assert entry.net == Decimal("100.00"), "الصافي بلا ضريبة"

    def test_entry_uses_the_completion_date_not_today(self, location):
        """
        ⚠️  Re-running the capture for old orders would have piled them all into
            one month, distorting every comparison between periods.
        """
        order = make_order(location)
        order.completed_at = timezone.now() - timedelta(days=40)
        order.save()

        entry = services.record_order_revenue(order)

        # ⚠️  `localdate(...)`, not `.date()`: the latter is the UTC date, which is
        #     the previous accounting day during the first hours of the day in Cairo.
        assert entry.occurred_on == timezone.localdate(order.completed_at)


# ═══════════════════════════════════════════════════════════
#  Returns
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRefunds:
    def test_refund_is_a_negative_entry_not_a_deletion(self, location):
        """
        ⚠️  Deleting the revenue entry erases that the sale ever happened — so
            the order count, its average value and everything built on them break.
        """
        order = make_order(location)
        services.record_order_revenue(order)

        services.record_refund(order)

        assert RevenueEntry.objects.filter(order=order).count() == 2
        assert RevenueEntry.objects.filter(source=RevenueSource.ORDER, order=order).exists()

        refund = RevenueEntry.objects.get(source=RevenueSource.REFUND, order=order)
        assert refund.net == Decimal("-100.00")

    def test_refund_without_an_original_entry_is_ignored(self, location):
        order = make_order(location)

        assert services.record_refund(order) is None

    def test_a_refund_is_recorded_once(self, location):
        order = make_order(location)
        services.record_order_revenue(order)

        services.record_refund(order)
        services.record_refund(order)

        assert RevenueEntry.objects.filter(source=RevenueSource.REFUND).count() == 1


# ═══════════════════════════════════════════════════════════
#  Cost of goods sold
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCOGS:
    def test_cost_comes_from_the_batch_actually_consumed(self, location, product):
        order = make_order(location)
        inventory_services.sell_immediately(
            product, 3, location=location, reference_type="order", reference_id=str(order.pk)
        )

        entry = services.record_order_revenue(order)

        assert entry.cogs.amount == Decimal("90.00"), "٣ × ٣٠ تكلفة الدفعة"
        assert entry.cogs.quantity == 3
        assert entry.cogs.is_complete

    def test_two_batches_at_different_costs_are_summed_not_averaged(self, location, product):
        """
        ⚠️  FEFO consumes the oldest first, and every movement carries its batch's cost.

            Computing an average instead gives a profit matching no sale that
            happened — and it changes retroactively every time a new batch arrives.
        """
        # The first batch: 100 units at a cost of 30 · the second at a cost of 40
        inventory_services.receive(product, 50, Decimal("40.00"), location=location)

        order = make_order(location)
        inventory_services.sell_immediately(
            product, 120, location=location, reference_type="order", reference_id=str(order.pk)
        )

        entry = services.record_order_revenue(order)

        # 100 × 30 + 20 × 40 = 3800
        assert entry.cogs.amount == Decimal("3800.00")

    def test_stock_without_a_batch_is_flagged_not_treated_as_free(self, location, product):
        """
        ⚠️  **The worst direction for the error.**

            Treating unknown cost as zero makes the profit appear higher than
            reality by the full price of the goods — so the report looks excellent.
        """
        from inventory.models import Batch, MovementType, StockMovement

        order = make_order(location)
        # A sale movement with no batch — as happens for stock entered without a receipt
        stock_movement = StockMovement.objects.create(
            product=product,
            location=location,
            movement_type=MovementType.SALE,
            quantity=5,
            reference_type="order",
            reference_id=str(order.pk),
            note="بلا دفعة مرتبطة",
        )
        assert stock_movement.unit_cost is None
        assert Batch.objects.filter(product=product).exists()

        entry = services.record_order_revenue(order)

        assert entry.cogs.unknown_quantity == 5
        assert not entry.cogs.is_complete

    def test_report_declares_itself_unreliable_when_cost_is_unknown(self, location, product):
        from inventory.models import MovementType, StockMovement

        order = make_order(location)
        StockMovement.objects.create(
            product=product,
            location=location,
            movement_type=MovementType.SALE,
            quantity=2,
            reference_type="order",
            reference_id=str(order.pk),
        )
        services.record_order_revenue(order)

        report = services.profit_and_loss(date.today(), date.today())

        assert report.unknown_cost_units == 2
        assert not report.is_reliable


# ═══════════════════════════════════════════════════════════
#  The profit statement — the exit gate
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestProfitAndLoss:
    def test_the_equation_balances(self, location, product, staff, category):
        """
        ⚠️  **The exit gate:** the P&L balances against the orders and expenses data.

            A sale of 10 units at 50 = 500 · its cost 10 × 30 = 300 ·
            gross profit 200 · an expense of 50 ⟵ net 150.
        """
        order = make_order(location, subtotal="500.00")
        inventory_services.sell_immediately(
            product, 10, location=location, reference_type="order", reference_id=str(order.pk)
        )
        services.record_order_revenue(order)

        expense = Expense.objects.create(
            category=category,
            amount=Decimal("50.00"),
            incurred_on=date.today(),
            entered_by=staff,
        )
        services.approve_expense(expense, approved_by=staff)

        report = services.profit_and_loss(date.today(), date.today())

        assert report.net_sales == Decimal("500.00")
        assert report.cogs == Decimal("300.00")
        assert report.gross_profit == Decimal("200.00")
        assert report.expenses == Decimal("50.00")
        assert report.net_profit == Decimal("150.00")
        assert report.gross_margin == Decimal("40.00")

    def test_refunds_reduce_net_sales_exactly_once(self, location, product):
        """
        ⚠️  A return is **already a negative entry**, so it is added, not subtracted.

            Subtracting it a second time doubles its effect — a sign error that
            surfaces only when a return occurs, after the report has been issued
            repeatedly.
        """
        first = make_order(location, subtotal="300.00")
        second = make_order(location, subtotal="200.00")
        services.record_order_revenue(first)
        services.record_order_revenue(second)

        services.record_refund(second)

        report = services.profit_and_loss(date.today(), date.today())

        assert report.revenue == Decimal("500.00")
        assert report.refunds == Decimal("-200.00")
        assert report.net_sales == Decimal("300.00")

    def test_draft_expenses_stay_out_but_stay_visible(self, location, staff, category):
        """
        ⚠️  The profit figure does not move every time an employee writes down an
            unreviewed expense — but hiding it entirely makes the admin read a
            profit that will change without warning.
        """
        Expense.objects.create(
            category=category,
            amount=Decimal("70.00"),
            incurred_on=date.today(),
            entered_by=staff,
        )

        report = services.profit_and_loss(date.today(), date.today())

        assert report.expenses == Decimal("0.00")
        assert report.pending_expenses == Decimal("70.00")

    def test_expenses_are_counted_in_the_month_they_belong_to(self, location, staff, category):
        """
        ⚠️  March's rent is entered in April and must appear in March's profit.

            Conflating the incurred date with the entry date shows one
            profitable month and one loss-making one for no real reason.
        """
        last_month = date.today().replace(day=1) - timedelta(days=1)

        expense = Expense.objects.create(
            category=category,
            amount=Decimal("400.00"),
            incurred_on=last_month,
            entered_by=staff,
        )
        services.approve_expense(expense, approved_by=staff)

        this_month = services.profit_and_loss(date.today().replace(day=1), date.today())
        assert this_month.expenses == Decimal("0.00")

        previous = services.profit_and_loss(last_month.replace(day=1), last_month)
        assert previous.expenses == Decimal("400.00")

    def test_margin_is_zero_not_a_crash_without_sales(self, location):
        report = services.profit_and_loss(date.today(), date.today())

        assert report.net_sales == Decimal("0.00")
        assert report.gross_margin == Decimal("0.00")

    def test_channels_are_separated(self, location, product):
        online = make_order(location, subtotal="300.00", channel=OrderChannel.ONLINE)
        counter = make_order(location, subtotal="200.00", channel=OrderChannel.POS)
        services.record_order_revenue(online)
        services.record_order_revenue(counter)

        rows = {
            row["channel"]: row["total"]
            for row in services.revenue_by_channel(date.today(), date.today())
        }

        assert rows[OrderChannel.ONLINE] == "300.00"
        assert rows[OrderChannel.POS] == "200.00"


# ═══════════════════════════════════════════════════════════
#  Expenses and approval
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestExpenseApproval:
    def test_an_expense_starts_as_a_draft(self, staff, category):
        expense = Expense.objects.create(
            category=category,
            amount=Decimal("10.00"),
            incurred_on=date.today(),
            entered_by=staff,
        )
        assert expense.status == ExpenseStatus.DRAFT
        assert not expense.counts_toward_profit

    def test_approving_twice_is_rejected(self, staff, category):
        expense = Expense.objects.create(
            category=category,
            amount=Decimal("10.00"),
            incurred_on=date.today(),
            entered_by=staff,
        )
        services.approve_expense(expense, approved_by=staff)

        with pytest.raises(BusinessError):
            services.approve_expense(expense, approved_by=staff)

    def test_rejection_requires_a_reason(self, staff, category):
        expense = Expense.objects.create(
            category=category,
            amount=Decimal("10.00"),
            incurred_on=date.today(),
            entered_by=staff,
        )
        with pytest.raises(BusinessError):
            services.reject_expense(expense, rejected_by=staff, reason="   ")


# ═══════════════════════════════════════════════════════════
#  Closing periods
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestFiscalPeriods:
    def test_a_missing_period_is_open(self):
        """⚠️  Treating absence as closed blocked the very first expense in the system."""
        services.assert_period_open(date.today())

    def test_a_closed_period_rejects_new_expenses(self, staff, category):
        today = date.today()
        period = FiscalPeriod.objects.create(year=today.year, month=today.month)
        period.close(by=staff)

        with pytest.raises(BusinessError):
            services.assert_period_open(today)

    def test_a_closed_period_rejects_approval(self, staff, category):
        """
        ⚠️  A report that was issued, acted upon, and then changed retroactively
            is the worst thing that can happen in a financial system.
        """
        today = date.today()
        expense = Expense.objects.create(
            category=category,
            amount=Decimal("10.00"),
            incurred_on=today,
            entered_by=staff,
        )
        FiscalPeriod.objects.create(year=today.year, month=today.month).close(by=staff)

        with pytest.raises(BusinessError):
            services.approve_expense(expense, approved_by=staff)


# ═══════════════════════════════════════════════════════════
#  Permissions — business rule 14
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestFinancePermissions:
    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_a_plain_admin_cannot_read_the_pnl(self, staff):
        """
        ⚠️  **Seeing profits is not an automatic admin permission.**

            The admin panel is opened by a catalogue manager, customer service
            and a warehouse supervisor — and none of them needs to know the
            margins, the salaries or the shop's rent.
        """
        response = self._client(staff).get(reverse("v1:finance:pnl"))

        assert response.status_code == 403

    def test_granting_the_permission_opens_it(self, staff):
        from django.contrib.auth.models import Permission

        staff.user_permissions.add(Permission.objects.get(codename="view_revenueentry"))
        staff = User.objects.get(pk=staff.pk)  # clear the permissions cache

        response = self._client(staff).get(reverse("v1:finance:pnl"))

        assert response.status_code == 200

    def test_a_customer_is_refused(self, db):
        customer = User.objects.create_user(email="c-fin@test.local", password=PASSWORD)
        customer.is_active = True
        customer.save()

        assert self._client(customer).get(reverse("v1:finance:pnl")).status_code == 403

    def test_the_owner_always_passes(self, db):
        """Without it the first user cannot grant the permissions — a deadlock."""
        owner = User.objects.create_superuser(email="owner-fin@test.local", password=PASSWORD)

        assert self._client(owner).get(reverse("v1:finance:pnl")).status_code == 200


# ═══════════════════════════════════════════════════════════
#  Automatic capture through the events
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAutomaticCapture:
    def test_a_pos_sale_is_captured_even_without_the_completion_event(self, location, product):
        """
        ⚠️  **A counter sale does not pass through `order_completed`.**

            Point of sale creates the order directly in its final state with no
            state machine. Relying on the signal alone meant all branch sales
            were absent from the profit statement while the report looked sound.
        """
        order = Order.objects.create(
            channel=OrderChannel.POS,
            location=location,
            status=OrderStatus.DELIVERED,
            payment_status=PaymentStatus.PAID,
            subtotal=Decimal("150.00"),
            grand_total=Decimal("150.00"),
            completed_at=timezone.now(),
        )

        assert RevenueEntry.objects.filter(order=order).exists()

    def test_marking_an_order_refunded_creates_the_reversal(self, location):
        order = Order.objects.create(
            channel=OrderChannel.POS,
            location=location,
            status=OrderStatus.DELIVERED,
            payment_status=PaymentStatus.PAID,
            subtotal=Decimal("80.00"),
            grand_total=Decimal("80.00"),
            completed_at=timezone.now(),
        )

        order.status = OrderStatus.REFUNDED
        order.save()

        assert RevenueEntry.objects.filter(source=RevenueSource.REFUND, order=order).exists()

    def test_a_failing_capture_never_breaks_the_sale(self, location, monkeypatch):
        """
        ⚠️  An accounting entry that was not written must not cancel a sale whose
            goods have been handed over.
        """

        def explode(*args, **kwargs):
            raise RuntimeError("انهيار متعمَّد")

        monkeypatch.setattr(services, "record_order_revenue", explode)

        order = Order.objects.create(
            channel=OrderChannel.POS,
            location=location,
            status=OrderStatus.DELIVERED,
            payment_status=PaymentStatus.PAID,
            subtotal=Decimal("10.00"),
            grand_total=Decimal("10.00"),
        )

        assert Order.objects.filter(pk=order.pk).exists()
        assert not RevenueEntry.objects.filter(order=order).exists()


@pytest.mark.django_db
class TestPOSCostIsNotZero:
    """
    ⚠️  **The trap the ordering genuinely caught us in.**

        Point of sale deducts stock before creating the order, so the movements
        are linked to the shift. And `post_save` on the order fires before they
        are redirected to it, so the first cost calculation happened on zero
        movements — and the sale was posted at a profit equal to the full
        selling price.

        The test measures the financial effect, not the mechanism of the fix: if
        the ordering reverted to what it was, this case fails.
    """

    @pytest.fixture
    def counter(self, db, location, product):
        from payments.models import PaymentMethodKind, PaymentProvider
        from pos import services as pos_services
        from pos.models import Register

        PaymentProvider.objects.create(
            code="fin-cash",
            adapter_key="cash",
            name_ar="نقدي",
            name_en="Cash",
            supported_methods=[PaymentMethodKind.CASH],
            supported_channels=["POS"],
            is_active=True,
            is_sandbox=False,
        )
        register = Register.objects.create(
            code="fin-reg", name_ar="كاونتر", name_en="Counter", location=location
        )
        cashier = User.objects.create_user(
            email="fin-cashier@test.local",
            password=PASSWORD,
            account_type=AccountType.EMPLOYEE,
        )
        cashier.is_active = True
        cashier.save()
        return pos_services.open_session(register, cashier)

    def test_a_counter_sale_records_its_real_cost(self, counter, product):
        from pos import services as pos_services

        result = pos_services.checkout(
            counter,
            [pos_services.SaleLine(product, 5)],
            [pos_services.SplitPayment(method="CASH", amount=Decimal("250.00"))],
        )

        entry = RevenueEntry.objects.get(order=result.order)

        assert entry.cogs.amount == Decimal("150.00"), "٥ × ٣٠ — لا صفر"
        assert entry.cogs.quantity == 5
        assert entry.net == Decimal("250.00")

    def test_counter_profit_is_not_the_whole_sale_price(self, counter, product):
        """The profit is 100, not 250 — the difference is the defect that used to occur."""
        from pos import services as pos_services

        result = pos_services.checkout(
            counter,
            [pos_services.SaleLine(product, 5)],
            [pos_services.SplitPayment(method="CASH", amount=Decimal("250.00"))],
        )

        entry = RevenueEntry.objects.get(order=result.order)

        assert entry.net - entry.cogs.amount == Decimal("100.00")


@pytest.mark.django_db
def test_cogs_is_deleted_with_its_revenue_entry(location, product):
    """The cost entry belongs to the revenue entry — it does not linger as an orphan distorting the
    totals."""
    order = make_order(location)
    entry = services.record_order_revenue(order)

    COGSEntry.objects.get(revenue_entry=entry).delete()

    assert not COGSEntry.objects.filter(revenue_entry=entry).exists()
