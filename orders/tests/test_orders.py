"""
اختبارات الطلبات — دورة الشراء الكاملة.

⚠️  المجموعات الحرجة:
      ١. اللقطات — الفاتورة الصادرة لا تتغيّر بتغيّر الكتالوج
      ٢. آلة الحالة — الانتقال غير المسموح مرفوض
      ٣. إعادة التحقق — لا طلب بسعر قديم أو مخزون ناقص
      ٤. الإلغاء — مخزون وكوبون يعودان معًا
"""

from decimal import Decimal

import pytest
from django.apps import apps

from accounts.models import AccountType, User
from cart import services as cart_services
from cart.models import CartStatus
from catalog.models import Category, Product
from core.errors import BusinessError
from core.models.tax import TaxClass
from customers.models import CustomerProfile
from inventory import services as inventory_services
from orders import services as order_services
from orders.models import Order, OrderChannel, OrderStatus, PaymentStatus
from promotions.models import Coupon, CouponKind, CouponRedemption

PASSWORD = "Str0ng-Test-Pass!23"


# ⚠️  مراجع نصية لا استيراد — **وكسولة**.
#
#     `orders` في L6 و`inventory` في L3، والعقد يمنع استيراد
#     موديلات نطاق آخر مباشرةً. الاختبار ليس استثناءً.
#
#     والكسل ضروري: `apps.get_model` على مستوى الوحدة يُنفَّذ قبل
#     تحميل سجل التطبيقات فيفشل بـ AppRegistryNotReady.


def stock_model():
    return apps.get_model("inventory", "Stock")


def location_model():
    return apps.get_model("inventory", "StockLocation")


ADDRESS = {
    "recipient_name": "أحمد محمود",
    "phone": "+201001234567",
    "governorate": "القاهرة",
    "city": "مدينة نصر",
    "street": "شارع ١",
}


@pytest.fixture
def location(db):
    return location_model().objects.create(
        code="main", name_ar="الرئيسي", name_en="Main", is_default=True
    )


@pytest.fixture
def tax_class(db):
    return TaxClass.objects.create(
        name_ar="قياسي",
        name_en="Standard",
        code="standard",
        rate=Decimal("14.00"),
        is_default=True,
    )


@pytest.fixture
def user(db):
    user = User.objects.create_user(
        email="buyer@test.local", password=PASSWORD, account_type=AccountType.STUDENT
    )
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def customer(user):
    return CustomerProfile.objects.create(user=user)


@pytest.fixture
def product(db, tax_class, location):
    category = Category.objects.create(name_ar="فئة", name_en="Category")
    product = Product.objects.create(
        sku="P-001",
        name_ar="منتج",
        name_en="Product",
        category=category,
        base_price=Decimal("100.00"),
        tax_class=tax_class,
    )
    inventory_services.receive(product, 50, Decimal("60.00"), location=location)
    return product


@pytest.fixture
def cart(user, product):
    cart = cart_services.get_active_cart(user=user)
    cart_services.add_line(cart, product, 2, user=user)
    return cart


def make_order(cart, customer, **kwargs):
    return order_services.create_from_cart(cart, customer=customer, address=ADDRESS, **kwargs)


# ═══════════════════════════════════════════════════════════
#  اللقطات —  ADR-30
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSnapshots:
    def test_line_captures_price_and_tax_rate(self, cart, customer, product):
        order = make_order(cart, customer)
        line = order.lines.first()

        assert line.unit_price == Decimal("100.00")
        assert line.tax_rate == Decimal("14.00")
        assert line.tax_amount == Decimal("28.00")  # ١٤٪ على ٢٠٠
        assert line.product_sku == "P-001"
        assert line.product_name_ar == "منتج"

    def test_price_change_does_not_alter_issued_order(self, cart, customer, product):
        """
        ⚠️  **جوهر اللقطة.**

        الفاتورة الصادرة لا تتغيّر بتغيّر سعر الكتالوج بعدها.
        """
        order = make_order(cart, customer)
        original_total = order.grand_total

        product.base_price = Decimal("500.00")
        product.save()

        order.refresh_from_db()
        line = order.lines.first()

        assert line.unit_price == Decimal("100.00")
        assert order.grand_total == original_total

    def test_tax_rate_change_does_not_alter_issued_order(self, cart, customer, tax_class):
        """
        ⚠️  النسبة تتغيّر بقرار حكومي؛ الفواتير القديمة تبقى بنسبتها.

        حسابها لاحقًا من النسبة الحالية يزوّر السجل المحاسبي.
        """
        order = make_order(cart, customer)

        tax_class.rate = Decimal("20.00")
        tax_class.save()

        order.refresh_from_db()
        assert order.lines.first().tax_rate == Decimal("14.00")

    def test_product_rename_does_not_alter_invoice(self, cart, customer, product):
        order = make_order(cart, customer)

        product.name_ar = "اسم جديد تمامًا"
        product.save()

        order.refresh_from_db()
        assert order.lines.first().product_name_ar == "منتج"

    def test_totals_are_consistent(self, cart, customer):
        order = make_order(cart, customer)

        # ٢ × ١٠٠ = ٢٠٠ · ضريبة ٢٨ · الإجمالي ٢٢٨
        assert order.subtotal == Decimal("200.00")
        assert order.tax_total == Decimal("28.00")
        assert order.grand_total == Decimal("228.00")


# ═══════════════════════════════════════════════════════════
#  الحقول المبكرة —  ADR-09
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEarlyFields:
    def test_channel_defaults_to_online(self, cart, customer):
        assert make_order(cart, customer).channel == OrderChannel.ONLINE

    def test_channel_supports_pos_before_phase_seven(self, cart, customer, location):
        """
        ⚠️  نقطة البيع في المرحلة ٧، والحقل يعمل الآن.

        إضافته بعد تراكم الطلبات تعني أن كل طلب سابق بلا قناة —
        فلا تقرير مبيعات يفصل القنوات رجعيًا.
        """
        order = make_order(cart, customer, channel=OrderChannel.POS, location=location)
        assert order.channel == OrderChannel.POS
        assert order.location == location

    def test_attribution_fields_exist_and_stay_empty(self, cart, customer):
        """حقول الإسناد تُخلق الآن وتُملأ في المرحلة ١٠."""
        order = make_order(cart, customer)

        assert order.owner_employee is None
        assert order.commission_employee is None

        names = {f.name for f in Order._meta.get_fields()}
        assert {"created_by", "owner_employee", "commission_employee"} <= names

    def test_location_is_recorded(self, cart, customer, location):
        assert make_order(cart, customer).location == location


# ═══════════════════════════════════════════════════════════
#  آلة الحالة
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestStateMachine:
    def test_valid_path_to_completion(self, cart, customer):
        order = make_order(cart, customer)

        for status in (
            OrderStatus.CONFIRMED,
            OrderStatus.PROCESSING,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
        ):
            order = order_services.transition(order, status)
            assert order.status == status

        order = order_services.complete(order)
        assert order.status == OrderStatus.COMPLETED

    def test_illegal_transition_is_rejected(self, cart, customer):
        """
        ⚠️  بلا آلة حالة، طلب «مكتمل» يعود إلى «قيد الانتظار» بنداء
            واحد — فيفسد كل تقرير مبيعات وكل عمولة محسوبة.
        """
        order = make_order(cart, customer)

        with pytest.raises(BusinessError) as exc:
            order_services.transition(order, OrderStatus.DELIVERED)

        assert exc.value.code == "INVALID_STATE_TRANSITION"
        assert exc.value.status_code == 409

    def test_terminal_states_have_no_exit(self, cart, customer):
        order = make_order(cart, customer)
        order_services.cancel(order, reason="اختبار")

        for status in (OrderStatus.CONFIRMED, OrderStatus.PROCESSING):
            with pytest.raises(BusinessError):
                order_services.transition(order, status)

    def test_every_transition_is_recorded(self, cart, customer):
        order = make_order(cart, customer)
        order_services.transition(order, OrderStatus.CONFIRMED, note="دفع مؤكد")

        history = order.status_history.all()
        assert history.count() == 2  # الإنشاء + التأكيد
        assert history.filter(to_status=OrderStatus.CONFIRMED, note="دفع مؤكد").exists()

    def test_payment_status_is_independent_of_order_status(self, cart, customer):
        """
        ⚠️  طلب مؤكد قد يكون غير مدفوع (دفع عند الاستلام)، وطلب
            ملغى قد يكون مدفوعًا وينتظر الاسترداد.
        """
        order = make_order(cart, customer)
        assert order.payment_status == PaymentStatus.UNPAID

        order = order_services.transition(order, OrderStatus.CONFIRMED)
        assert order.payment_status == PaymentStatus.UNPAID

    def test_marking_paid_confirms_a_pending_order(self, cart, customer):
        order = make_order(cart, customer)
        order = order_services.mark_paid(order)

        assert order.payment_status == PaymentStatus.PAID
        assert order.status == OrderStatus.CONFIRMED

    def test_cannot_pay_twice(self, cart, customer):
        order = order_services.mark_paid(make_order(cart, customer))

        with pytest.raises(BusinessError) as exc:
            order_services.mark_paid(order)
        assert exc.value.code == "ORDER_ALREADY_PAID"


# ═══════════════════════════════════════════════════════════
#  المخزون
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestInventoryIntegration:
    def test_order_reserves_not_deducts(self, cart, customer, product, location):
        """
        ⚠️  الطلب يحجز؛ الشحن يخصم.

        الخصم عند الإنشاء يعني بضاعة مفقودة من الرصيد لطلب قد
        يُلغى بعد دقيقة.
        """
        make_order(cart, customer)

        stock = stock_model().objects.get(product=product, location=location)
        assert stock.quantity_physical == 50
        assert stock.quantity_reserved == 2
        assert stock.available == 48

    def test_shipping_commits_the_reservation(self, cart, customer, product, location):
        order = make_order(cart, customer)

        for status in (
            OrderStatus.CONFIRMED,
            OrderStatus.PROCESSING,
            OrderStatus.SHIPPED,
        ):
            order = order_services.transition(order, status)

        stock = stock_model().objects.get(product=product, location=location)
        assert stock.quantity_physical == 48
        assert stock.quantity_reserved == 0

    def test_cancelling_releases_the_reservation(self, cart, customer, product, location):
        order = make_order(cart, customer)
        order_services.cancel(order, reason="غيّر رأيه")

        stock = stock_model().objects.get(product=product, location=location)
        assert stock.quantity_reserved == 0
        assert stock.available == 50

    def test_order_fails_when_stock_ran_out(self, user, customer, product, location):
        """المخزون قد ينفد بين الإضافة وإتمام الشراء."""
        cart = cart_services.get_active_cart(user=user)
        cart_services.add_line(cart, product, 10, user=user)

        # مشترٍ آخر يستهلك كل المخزون
        inventory_services.sell_immediately(product, 50, location=location)

        with pytest.raises(BusinessError) as exc:
            make_order(cart, customer)
        assert exc.value.code == "INSUFFICIENT_STOCK"


# ═══════════════════════════════════════════════════════════
#  إعادة التحقق
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRevalidation:
    def test_deactivated_product_blocks_checkout(self, cart, customer, product):
        product.is_active = False
        product.save()

        with pytest.raises(BusinessError) as exc:
            make_order(cart, customer)
        assert exc.value.code == "PRODUCT_UNAVAILABLE"

    def test_empty_cart_is_rejected(self, user, customer):
        cart = cart_services.get_active_cart(user=user)

        with pytest.raises(BusinessError) as exc:
            make_order(cart, customer)
        assert exc.value.code == "CART_EMPTY"

    def test_price_is_recomputed_not_taken_from_client(self, user, customer, product, location):
        """
        ⚠️  ما ترسله الواجهة من أسعار يُتجاهَل تمامًا.

        السعر يُعاد حسابه من المصدر عند إنشاء الطلب.
        """
        cart = cart_services.get_active_cart(user=user)
        cart_services.add_line(cart, product, 1, user=user)

        product.base_price = Decimal("250.00")
        product.save()

        order = make_order(cart, customer)
        assert order.lines.first().unit_price == Decimal("250.00")

    def test_cart_is_marked_converted(self, cart, customer):
        make_order(cart, customer)
        cart.refresh_from_db()

        assert cart.status == CartStatus.CONVERTED
        assert cart.converted_at is not None


# ═══════════════════════════════════════════════════════════
#  الكوبونات
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCouponIntegration:
    @pytest.fixture
    def coupon(self, db):
        return Coupon.objects.create(
            code="SAVE10",
            name_ar="خصم ١٠٪",
            name_en="10% off",
            kind=CouponKind.PERCENTAGE,
            value=Decimal("10.00"),
        )

    def test_coupon_reduces_the_total(self, cart, customer, coupon):
        cart_services.apply_coupon(cart, "SAVE10")
        order = make_order(cart, customer)

        assert order.coupon_code == "SAVE10"
        assert order.coupon_discount == Decimal("20.00")  # ١٠٪ من ٢٠٠

    def test_redemption_is_recorded(self, cart, customer, coupon, user):
        cart_services.apply_coupon(cart, "SAVE10")
        order = make_order(cart, customer)

        redemption = CouponRedemption.objects.get(coupon=coupon, user=user)
        assert redemption.reference_id == str(order.pk)

        coupon.refresh_from_db()
        assert coupon.usage_count == 1

    def test_cancelling_the_order_restores_the_coupon(self, cart, customer, coupon):
        """
        ⚠️  السجل يبقى والعدّاد ينقص.

        الحذف يمحو أثر التدقيق: لا يبقى ما يثبت أن هذا العميل
        استخدم الكوبون ثم ألغى.
        """
        cart_services.apply_coupon(cart, "SAVE10")
        order = make_order(cart, customer)
        order_services.cancel(order, reason="اختبار")

        coupon.refresh_from_db()
        assert coupon.usage_count == 0

        redemption = CouponRedemption.objects.get(coupon=coupon)
        assert redemption.is_cancelled
        assert redemption.cancelled_at is not None

    def test_lowercase_code_is_accepted(self, cart, customer, coupon):
        """`SAVE10` و`save10` كوبون واحد."""
        result = cart_services.apply_coupon(cart, "save10")
        assert result.is_valid


# ═══════════════════════════════════════════════════════════
#  الإلغاء
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCancellation:
    def test_reason_is_required(self, cart, customer):
        order = make_order(cart, customer)

        with pytest.raises(BusinessError):
            order_services.cancel(order, reason="")

    def test_shipped_order_cannot_be_cancelled_after_delivery(self, cart, customer):
        order = make_order(cart, customer)
        for status in (
            OrderStatus.CONFIRMED,
            OrderStatus.PROCESSING,
            OrderStatus.SHIPPED,
            OrderStatus.DELIVERED,
        ):
            order = order_services.transition(order, status)

        with pytest.raises(BusinessError) as exc:
            order_services.cancel(order, reason="متأخر")
        assert exc.value.code == "ORDER_CANNOT_BE_CANCELLED"

    def test_cancellation_records_reason_and_time(self, cart, customer):
        order = make_order(cart, customer)
        order_services.cancel(order, reason="نفد الصبر")

        order.refresh_from_db()
        assert order.status == OrderStatus.CANCELLED
        assert order.cancellation_reason == "نفد الصبر"
        assert order.cancelled_at is not None


# ═══════════════════════════════════════════════════════════
#  حدود النطاق
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestDomainBoundaries:
    def test_orders_does_not_import_inventory_models(self):
        """
        ⚠️  الكود القديم عدّل `product.quantity` مباشرةً من
            `orders/api.py` — نطاق يكتب في موديل نطاق آخر.
        """
        import inspect

        from orders import services

        source = inspect.getsource(services)
        assert "from inventory.models" not in source
        assert "from catalog.models" not in source

    def test_orders_does_not_reimplement_coupon_logic(self):
        """
        ⚠️  المنطق كان منفّذًا مرتين متباعدتين — كوبون يُقبل من
            مسار ويُرفض من آخر.
        """
        import inspect

        from orders import services

        source = inspect.getsource(services)
        assert "promotion_services.validate" not in source
        assert "promotion_services" in source  # يستدعي لا يكرّر

    def test_order_number_is_not_the_url_identifier(self, cart, customer):
        """`ORD-2026-XXXXXX` للعرض · الرابط يحمل UUID."""
        import uuid

        order = make_order(cart, customer)
        assert order.number.startswith("ORD-")
        assert isinstance(order.pk, uuid.UUID)
