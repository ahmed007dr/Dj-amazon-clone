"""
اختبارات التقارير.

⚠️  بوابة الخروج للمرحلة ١٣:

        كل رقم يوازي مصدره · لا مصدر حقيقة ثانٍ · المدى المقلوب
        يُرفض لا يُنتج أصفارًا تبدو حقيقية.

    وأخطر ما تحرسه: أن يُقيَّم المخزون بسعر البيع فيظهر ربح لم
    يتحقّق كأصل مملوك · أن يُخفي تقرير الصلاحية ما **انتهى فعلًا**
    وما زال في المخزن · أن يخالف رقم الربح هنا قائمة الأرباح.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from administration.models import AdminProfile
from catalog.models import Category, Product
from core.errors import BusinessError
from customers.models import CustomerProfile
from inventory import services as inventory_services
from inventory.models import LocationKind, StockLocation
from orders.models import Order, OrderChannel, OrderLine, OrderStatus, PaymentStatus
from reporting import services

PASSWORD = "Str0ng-Test-Pass!23"


@pytest.fixture
def location(db):
    return StockLocation.objects.create(
        code="rep-loc",
        name_ar="مخزن",
        name_en="Store",
        kind=LocationKind.WAREHOUSE,
        is_default=True,
        is_sellable=True,
    )


@pytest.fixture
def product(db, location):
    category = Category.objects.create(slug="rep", name_ar="فئة", name_en="Cat")
    item = Product.objects.create(
        sku="REP-1",
        name_ar="صنف",
        name_en="Item",
        category=category,
        base_price=Decimal("100.00"),
    )
    inventory_services.receive(item, 40, Decimal("60.00"), location=location)
    return item


@pytest.fixture
def customer(db):
    user = User.objects.create_user(email="rbuyer@test.local", password=PASSWORD)
    user.is_active = True
    user.save()
    return CustomerProfile.objects.create(user=user, display_name_ar="عميل")


@pytest.fixture
def viewer(db):
    from django.contrib.auth.models import Permission

    user = User.objects.create_user(
        email="reports@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    user.is_active = True
    user.save()
    AdminProfile.objects.create(user=user)
    user.user_permissions.add(Permission.objects.get(codename="view_revenueentry"))
    return User.objects.get(pk=user.pk)


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def make_order(customer, total="500.00", *, status=OrderStatus.DELIVERED, channel=None):
    amount = Decimal(total)
    return Order.objects.create(
        customer=customer,
        channel=channel or OrderChannel.ONLINE,
        status=status,
        payment_status=PaymentStatus.PAID,
        subtotal=amount,
        grand_total=amount,
        completed_at=timezone.now(),
    )


def today_range():
    today = timezone.localdate()
    return today, today


# ═══════════════════════════════════════════════════════════
#  المبيعات
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSales:
    def test_summary_excludes_cancelled_and_subtracts_returns(self, customer):
        make_order(customer, "1000.00")
        make_order(customer, "300.00", status=OrderStatus.REFUNDED)
        make_order(customer, "9000.00", status=OrderStatus.CANCELLED)

        start, end = today_range()
        result = services.sales_summary(start, end)

        assert result.gross_sales == Decimal("1000.00")
        assert result.returns_total == Decimal("300.00")
        assert result.net_sales == Decimal("700.00")
        assert result.orders_count == 1

    def test_average_order_does_not_divide_by_zero(self, db):
        start, end = today_range()
        result = services.sales_summary(start, end)

        assert result.orders_count == 0
        assert result.average_order == Decimal("0.00")

    def test_inverted_range_is_refused(self, db):
        """⚠️  المدى المقلوب يُنتج تقريرًا بأصفار يبدو حقيقيًا."""
        today = timezone.localdate()

        with pytest.raises(BusinessError):
            services.sales_summary(today, today - timedelta(days=5))

    def test_channels_are_separated(self, customer):
        make_order(customer, "600.00", channel=OrderChannel.ONLINE)
        make_order(customer, "400.00", channel=OrderChannel.POS)

        start, end = today_range()
        rows = {row["channel"]: row["total"] for row in services.sales_by_channel(start, end)}

        assert rows[OrderChannel.ONLINE] == "600.00"
        assert rows[OrderChannel.POS] == "400.00"

    def test_top_products_rank_by_revenue_not_count(self, customer, product, location):
        """
        ⚠️  الترتيب بالعدد يضع أرخص صنف أولًا دائمًا.

            علبة بجنيهين تُباع ألف مرة تسبق جهازًا بألف بيع عشرين
            — والقرار الشرائي يُبنى على القيمة.
        """
        category = product.category
        cheap = Product.objects.create(
            sku="CHEAP", name_ar="رخيص", name_en="Cheap", category=category, base_price=2
        )

        order = make_order(customer, "1000.00")
        OrderLine.objects.create(
            order=order,
            product=product,
            product_sku=product.sku,
            product_name_ar=product.name_ar,
            product_name_en=product.name_en,
            quantity=10,
            unit_price=Decimal("100.00"),
            list_price=Decimal("100.00"),
        )
        OrderLine.objects.create(
            order=order,
            product=cheap,
            product_sku=cheap.sku,
            product_name_ar=cheap.name_ar,
            product_name_en=cheap.name_en,
            quantity=200,
            unit_price=Decimal("2.00"),
            list_price=Decimal("2.00"),
        )

        start, end = today_range()
        rows = services.top_products(start, end)

        assert rows[0]["sku"] == "REP-1", "الأعلى قيمة أولًا"
        assert rows[0]["revenue"] == "1000.00"
        assert rows[1]["quantity"] == 200


# ═══════════════════════════════════════════════════════════
#  المخزون
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestInventory:
    def test_stock_is_valued_at_cost_not_sale_price(self, product):
        """
        ⚠️  **خطأ محاسبي أساسي لو عُكس.**

            التقييم بسعر البيع يُظهر ربحًا لم يتحقّق كأنه أصل
            مملوك — ورقم يُقدَّم للبنك أحيانًا.
        """
        summary = services.inventory_summary()

        # ٤٠ وحدة × ٦٠ تكلفة = ٢٤٠٠ (لا ٤٠ × ١٠٠ = ٤٠٠٠)
        assert summary["stock_value_at_cost"] == "2400.00"

    def test_expiry_report_includes_already_expired_batches(self, product, location):
        """
        ⚠️  استبعاد المنتهية يُخفي ما **انتهى وما زال في المخزن** —
            وهو الأخطر: بضاعة قد تُباع.
        """
        from inventory.models import Batch

        Batch.objects.filter(product=product).update(
            expires_at=timezone.localdate() - timedelta(days=3)
        )

        rows = services.expiry_report(days=30)

        assert len(rows) == 1
        assert rows[0]["is_expired"] is True
        assert rows[0]["days_left"] < 0

    def test_expiry_report_values_at_cost(self, product, location):
        from inventory.models import Batch

        Batch.objects.filter(product=product).update(
            expires_at=timezone.localdate() + timedelta(days=10)
        )

        rows = services.expiry_report(days=30)
        assert rows[0]["value_at_cost"] == "2400.00"


# ═══════════════════════════════════════════════════════════
#  العملاء
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCustomers:
    def test_new_customers_are_measured_by_first_order(self, customer):
        """
        ⚠️  من سجّل قبل سنة واشترى اليوم أول مرة هو عميل **جديد**
            تجاريًا؛ وعدّه قديمًا يجعل كل حملة تبدو بلا أثر.
        """
        customer.first_order_at = timezone.now()
        customer.save()
        make_order(customer, "500.00")

        start, end = today_range()
        result = services.customer_behaviour(start, end)

        assert result["new_customers"] == 1
        assert result["active_customers"] == 1

    def test_top_customers_rank_by_spend(self, customer, db):
        other_user = User.objects.create_user(email="big@test.local", password=PASSWORD)
        other_user.is_active = True
        other_user.save()
        whale = CustomerProfile.objects.create(user=other_user, display_name_ar="كبير")

        make_order(customer, "100.00")
        make_order(whale, "9000.00")

        start, end = today_range()
        rows = services.customer_behaviour(start, end)["top_customers"]

        assert rows[0]["name"] == "كبير"
        assert rows[0]["total"] == "9000.00"


# ═══════════════════════════════════════════════════════════
#  اللوحة الجامعة
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestOverview:
    def test_profit_comes_from_finance_not_recomputed(self, customer, product, location):
        """
        ⚠️  **مصدر واحد للربح.**

            حسابه هنا ثانيةً يُنتج رقمًا يخالف قائمة الأرباح، ولا
            أحد يعرف أيّهما يُصدَّق.
        """
        from finance import services as finance_services

        order = make_order(customer, "1000.00")
        inventory_services.sell_immediately(
            product, 10, location=location, reference_type="order", reference_id=str(order.pk)
        )
        entry = finance_services.RevenueEntry.objects.get(order=order)
        finance_services.record_cogs(entry)

        start, end = today_range()
        report = services.overview(start, end)
        pnl = finance_services.profit_and_loss(start, end)

        assert report["gross_profit"] == str(pnl.gross_profit)
        assert report["cogs"] == str(pnl.cogs)
        assert report["net_profit"] == str(pnl.net_profit)

    def test_overview_surfaces_profit_reliability(self, customer):
        """تقرير فيه تكلفة مجهولة يقول ذلك صراحةً."""
        start, end = today_range()
        report = services.overview(start, end)

        assert "profit_is_reliable" in report


# ═══════════════════════════════════════════════════════════
#  الصلاحيات
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPermissions:
    def test_a_customer_is_refused(self, db):
        user = User.objects.create_user(email="nosy@test.local", password=PASSWORD)
        user.is_active = True
        user.save()

        assert client_for(user).get(reverse("v1:reporting:overview")).status_code == 403

    def test_a_plain_admin_is_refused(self, db):
        """
        ⚠️  التقارير تكشف المبيعات والأرباح وأداء كل موظف بالاسم —
            وربطها بدخول اللوحة يفتحها لمن يفتحها لسبب آخر.
        """
        staff = User.objects.create_user(
            email="plain@test.local", password=PASSWORD, account_type=AccountType.ADMIN
        )
        staff.is_active = True
        staff.save()
        AdminProfile.objects.create(user=staff)

        assert client_for(staff).get(reverse("v1:reporting:overview")).status_code == 403

    def test_the_finance_permission_opens_reports(self, viewer):
        response = client_for(viewer).get(reverse("v1:reporting:overview"))
        assert response.status_code == 200

    def test_every_report_endpoint_answers(self, viewer, customer, product):
        make_order(customer, "500.00")
        client = client_for(viewer)

        for name in ("overview", "sales", "inventory", "customers", "performance"):
            response = client.get(reverse(f"v1:reporting:{name}"))
            assert response.status_code == 200, name


@pytest.mark.django_db
def test_reporting_has_no_models():
    """
    ⚠️  **هذا النطاق يقرأ ولا يكتب — والاختبار يحرس ذلك.**

        أول موديل يُضاف هنا ينشئ مصدر حقيقة ثانيًا يجب أن يوازي
        مصادره، وأول انحراف لا يملك أحد حسمه.
    """
    from django.apps import apps

    assert list(apps.get_app_config("reporting").get_models()) == []
