"""
اختبارات المالية.

⚠️  بوابة الخروج للمرحلة ٨:

        P&L **يوازن** مقابل بيانات الطلبات والمصروفات ·
        كل رقم قابل للتتبع إلى مصدره · لا حساب صندوق أسود.

    وأخطر ما تحرسه هذه الاختبارات ليس المعادلة بل ما يحيط بها:
    ألّا يُحتسب إيراد الطلب مرتين · ألّا تُحتسب الضريبة ربحًا ·
    ألّا تُقرأ البضاعة مجهولة التكلفة كأنها مجانية.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from administration.models import AdminProfile
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
#  التجهيز
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def tax_free(db):
    """أرقام مستديرة تجعل فشل المعادلة مقروءًا."""
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
    """صنف بتكلفة ٣٠ وسعر ٥٠ — هامش ٢٠ للوحدة."""
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
    return user


@pytest.fixture
def category(db):
    return ExpenseCategory.objects.create(code="rent", name_ar="إيجار", name_en="Rent")


def make_order(location, *, subtotal="100.00", tax="0.00", discount="0.00", channel="ONLINE"):
    """طلب مباشر — بلا مرور بآلة الحالة، لاختبار الالتقاط وحده."""
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
#  التقاط الإيراد
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRevenueCapture:
    def test_completed_order_creates_one_entry(self, location):
        order = make_order(location)

        services.record_order_revenue(order)

        assert RevenueEntry.objects.filter(order=order).count() == 1

    def test_the_same_order_is_never_counted_twice(self, location):
        """
        ⚠️  **أخطر خطأ ممكن في هذا النطاق.**

            `order_completed` تُبعَث مرتين بإعادة محاولة أو تصحيح
            يدوي أو مستمع سُجّل مرتين. وبلا حارس يقول التقرير ضعف
            ما بيع — ولا يُكتشف إلا بمطابقة يدوية.
        """
        order = make_order(location)

        services.record_order_revenue(order)
        services.record_order_revenue(order)
        services.record_order_revenue(order)

        assert RevenueEntry.objects.filter(order=order).count() == 1

    def test_duplicate_is_blocked_by_the_database_not_only_by_code(self, location):
        """الفحص في الكود يخسر السباق؛ القيد الفريد يحسمه."""
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
        ⚠️  المتجر يحصّل الضريبة نيابةً عن الدولة ولا يملكها.

            احتسابها إيرادًا يضخّم الربح بنسبتها كاملة — وهو خطأ
            يمرّ صامتًا لأن الرقم يبدو أكبر لا أصغر.
        """
        order = make_order(location, subtotal="100.00", tax="14.00")

        entry = services.record_order_revenue(order)

        assert entry.gross == Decimal("100.00")
        assert entry.tax == Decimal("14.00")
        assert entry.net == Decimal("100.00"), "الصافي بلا ضريبة"

    def test_entry_uses_the_completion_date_not_today(self, location):
        """
        ⚠️  إعادة تشغيل الالتقاط لطلبات قديمة كانت ستكدّسها كلها
            في شهر واحد فتشوّه كل مقارنة بين الفترات.
        """
        order = make_order(location)
        order.completed_at = timezone.now() - timedelta(days=40)
        order.save()

        entry = services.record_order_revenue(order)

        assert entry.occurred_on == order.completed_at.date()


# ═══════════════════════════════════════════════════════════
#  المرتجعات
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRefunds:
    def test_refund_is_a_negative_entry_not_a_deletion(self, location):
        """
        ⚠️  حذف قيد الإيراد يمحو أن البيعة وقعت أصلًا — فيختل عدد
            الطلبات ومتوسط قيمتها وكل ما يُبنى عليهما.
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
#  تكلفة البضاعة المباعة
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
        ⚠️  FEFO يستهلك الأقدم أولًا، وكل حركة تحمل تكلفة دفعتها.

            حساب المتوسط بدلها يعطي ربحًا لا يطابق أي بيعة وقعت —
            ويتغيّر بأثر رجعي كلما وصلت دفعة جديدة.
        """
        # الدفعة الأولى ١٠٠ وحدة بتكلفة ٣٠ · الثانية بتكلفة ٤٠
        inventory_services.receive(product, 50, Decimal("40.00"), location=location)

        order = make_order(location)
        inventory_services.sell_immediately(
            product, 120, location=location, reference_type="order", reference_id=str(order.pk)
        )

        entry = services.record_order_revenue(order)

        # ١٠٠ × ٣٠ + ٢٠ × ٤٠ = ٣٨٠٠
        assert entry.cogs.amount == Decimal("3800.00")

    def test_stock_without_a_batch_is_flagged_not_treated_as_free(self, location, product):
        """
        ⚠️  **الاتجاه الأسوأ للخطأ.**

            معاملة التكلفة المجهولة كصفر تجعل الربح يظهر أعلى من
            حقيقته بثمن البضاعة كاملًا — فيبدو التقرير ممتازًا.
        """
        from inventory.models import Batch, MovementType, StockMovement

        order = make_order(location)
        # حركة بيع بلا دفعة — كما يحدث لمخزون أُدخل بلا استلام
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
#  قائمة الأرباح — بوابة الخروج
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestProfitAndLoss:
    def test_the_equation_balances(self, location, product, staff, category):
        """
        ⚠️  **بوابة الخروج:** P&L يوازن مقابل بيانات الطلبات
            والمصروفات.

            بيعة ١٠ وحدات بـ٥٠ = ٥٠٠ · تكلفتها ١٠ × ٣٠ = ٣٠٠ ·
            مجمل الربح ٢٠٠ · مصروف ٥٠ ⟵ صافي ١٥٠.
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
        ⚠️  المرتجع **قيد سالب أصلًا** فيُجمَع لا يُطرَح.

            طرحه مرة ثانية يضاعف أثره — خطأ إشارة لا يظهر إلا حين
            يقع مرتجع، أي بعد أن يكون التقرير قد صدر مرارًا.
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
        ⚠️  رقم الربح لا يتحرّك كلما كتب موظف مصروفًا لم يُراجَع —
            لكن إخفاءه تمامًا يجعل الأدمن يقرأ ربحًا سيتغيّر بلا
            إنذار.
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
        ⚠️  إيجار مارس يُدخَل في أبريل ويجب أن يظهر في أرباح مارس.

            الخلط بين تاريخ الاستحقاق والإدخال يُظهر شهرًا رابحًا
            وآخر خاسرًا بلا سبب حقيقي.
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
#  المصروفات والاعتماد
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
#  إقفال الفترات
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestFiscalPeriods:
    def test_a_missing_period_is_open(self):
        """⚠️  اعتبار الغياب إقفالًا كان يمنع أول مصروف في النظام."""
        services.assert_period_open(date.today())

    def test_a_closed_period_rejects_new_expenses(self, staff, category):
        today = date.today()
        period = FiscalPeriod.objects.create(year=today.year, month=today.month)
        period.close(by=staff)

        with pytest.raises(BusinessError):
            services.assert_period_open(today)

    def test_a_closed_period_rejects_approval(self, staff, category):
        """
        ⚠️  تقرير صدر واتُّخذ عليه قرار ثم تغيّر بأثر رجعي هو أسوأ
            ما يقع في نظام مالي.
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
#  الصلاحيات — قاعدة العمل ١٤
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestFinancePermissions:
    def _client(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_a_plain_admin_cannot_read_the_pnl(self, staff):
        """
        ⚠️  **رؤية الأرباح ليست صلاحية أدمن تلقائية.**

            لوحة الأدمن يفتحها مدير كتالوج وخدمة عملاء ومسؤول
            مخزن — ولا واحد منهم يحتاج معرفة الهوامش ولا الرواتب
            ولا إيجار المحل.
        """
        response = self._client(staff).get(reverse("v1:finance:pnl"))

        assert response.status_code == 403

    def test_granting_the_permission_opens_it(self, staff):
        from django.contrib.auth.models import Permission

        staff.user_permissions.add(Permission.objects.get(codename="view_revenueentry"))
        staff = User.objects.get(pk=staff.pk)  # تفريغ كاش الصلاحيات

        response = self._client(staff).get(reverse("v1:finance:pnl"))

        assert response.status_code == 200

    def test_a_customer_is_refused(self, db):
        customer = User.objects.create_user(email="c-fin@test.local", password=PASSWORD)
        customer.is_active = True
        customer.save()

        assert self._client(customer).get(reverse("v1:finance:pnl")).status_code == 403

    def test_the_owner_always_passes(self, db):
        """بدونه لا يستطيع أول مستخدم منح الصلاحيات — حلقة مفرغة."""
        owner = User.objects.create_superuser(email="owner-fin@test.local", password=PASSWORD)

        assert self._client(owner).get(reverse("v1:finance:pnl")).status_code == 200


# ═══════════════════════════════════════════════════════════
#  الالتقاط التلقائي عبر الأحداث
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAutomaticCapture:
    def test_a_pos_sale_is_captured_even_without_the_completion_event(self, location, product):
        """
        ⚠️  **بيعة الكاونتر لا تمرّ بـ `order_completed`.**

            نقطة البيع تُنشئ الطلب في حالته النهائية مباشرةً بلا
            آلة حالة. الاكتفاء بالإشارة كان يعني أن كل مبيعات
            الفرع تغيب عن قائمة الأرباح بينما التقرير يبدو سليمًا.
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
        ⚠️  قيد محاسبي لم يُكتب يجب ألا يلغي بيعةً سُلِّمت بضاعتها.
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
    ⚠️  **الفخّ الذي أوقعنا فيه الترتيب فعلًا.**

        نقطة البيع تخصم المخزون قبل إنشاء الطلب، فتُربط الحركات
        بالوردية. و`post_save` على الطلب يسبق إعادة توجيهها إليه،
        فوقع أول حساب للتكلفة على صفر حركات — وقُيِّدت البيعة
        بربح يساوي ثمن البيع كاملًا.

        الاختبار يقيس الأثر المالي لا آلية الإصلاح: لو عاد
        الترتيب إلى ما كان، تسقط هذه الحالة.
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
        """الربح ١٠٠ لا ٢٥٠ — الفرق هو الخطأ الذي كان يقع."""
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
    """قيد التكلفة تابع لقيد الإيراد — لا يبقى يتيمًا يشوّه المجاميع."""
    order = make_order(location)
    entry = services.record_order_revenue(order)

    COGSEntry.objects.get(revenue_entry=entry).delete()

    assert not COGSEntry.objects.filter(revenue_entry=entry).exists()
