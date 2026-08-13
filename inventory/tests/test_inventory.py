"""
اختبارات المخزون.

⚠️  المجموعات الحرجة:
      ١. منع البيع الزائد — الخطأ الأخطر في النموذج القديم
      ٢. FEFO — الأقرب انتهاءً أولًا لا الأقدم استلامًا
      ٣. لقطة التكلفة — بدونها يستحيل حساب الربح لاحقًا
      ٤. منع تكرار التنبيهات
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db.utils import IntegrityError
from django.utils import timezone

from catalog.models import Category, Product
from core.errors import BusinessError
from inventory import services
from inventory.models import (
    AlertType,
    Batch,
    LocationKind,
    MovementType,
    ReservationStatus,
    Stock,
    StockAlert,
    StockLocation,
    StockMovement,
)


@pytest.fixture
def location(db):
    return StockLocation.objects.create(
        code="main", name_ar="المخزن الرئيسي", name_en="Main", is_default=True
    )


@pytest.fixture
def branch(db):
    return StockLocation.objects.create(
        code="branch-1", name_ar="فرع ١", name_en="Branch 1", kind=LocationKind.BRANCH
    )


@pytest.fixture
def product(db):
    category = Category.objects.create(name_ar="فئة", name_en="Category")
    return Product.objects.create(
        sku="TEST-001", name_ar="منتج", name_en="Product", category=category
    )


@pytest.fixture
def stocked(product, location):
    """١٠٠ قطعة بتكلفة ١٠ جنيه."""
    services.receive(product, 100, Decimal("10.00"), location=location)
    return product


# ═══════════════════════════════════════════════════════════
#  منع البيع الزائد
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestOverselling:
    def test_cannot_reserve_more_than_available(self, stocked, location):
        with pytest.raises(BusinessError) as exc:
            services.reserve(stocked, 101, location=location)

        assert exc.value.code == "INSUFFICIENT_STOCK"

    def test_reservations_accumulate_against_available(self, stocked, location):
        """
        ⚠️  حجزان متتاليان لا يتجاوزان المتاح مجتمعين.

        الفحص ضد الكمية الفعلية بدل المتاح يسمح بحجز نفس القطعة
        مرتين — وهو بالضبط ما يحدث عند غفلة عن `quantity_reserved`.
        """
        services.reserve(stocked, 60, location=location)

        with pytest.raises(BusinessError):
            services.reserve(stocked, 50, location=location)

        services.reserve(stocked, 40, location=location)  # المتبقي بالضبط

        stock = Stock.objects.get(product=stocked, location=location)
        assert stock.quantity_reserved == 100
        assert stock.available == 0

    def test_database_constraint_blocks_negative_available(self, stocked, location):
        """
        ⚠️  **خط الدفاع الأخير.**

        القفل يحمي من التزامن لكنه لا يعمل على SQLite. القيد في
        قاعدة البيانات يعمل على المحركين ولا يمكن تجاوزه من أي
        مسار كود مهما أخطأ — هذا الاختبار يتجاوز طبقة الخدمات عمدًا.
        """
        stock = Stock.objects.get(product=stocked, location=location)

        with pytest.raises(IntegrityError):
            Stock.objects.filter(pk=stock.pk).update(quantity_reserved=150)

    def test_batch_remaining_cannot_exceed_received(self, stocked, location):
        batch = Batch.objects.filter(product=stocked).first()

        with pytest.raises(IntegrityError):
            Batch.objects.filter(pk=batch.pk).update(quantity_remaining=999)

    def test_immediate_sale_respects_availability(self, stocked, location):
        """بيع نقطة البيع الفوري يخضع لنفس الفحص."""
        services.reserve(stocked, 95, location=location)

        with pytest.raises(BusinessError):
            services.sell_immediately(stocked, 10, location=location)

        services.sell_immediately(stocked, 5, location=location)

    def test_adjustment_down_respects_availability(self, stocked, location):
        services.reserve(stocked, 90, location=location)

        with pytest.raises(BusinessError):
            services.adjust(stocked, -20, location=location, reason="تسوية")


# ═══════════════════════════════════════════════════════════
#  دورة الحجز
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestReservationLifecycle:
    def test_reserve_reduces_available_not_physical(self, stocked, location):
        """الحجز لا يُخرج البضاعة من الرف — يمنع بيعها لغير الحاجز."""
        services.reserve(stocked, 30, location=location)

        stock = Stock.objects.get(product=stocked, location=location)
        assert stock.quantity_physical == 100
        assert stock.quantity_reserved == 30
        assert stock.available == 70

    def test_release_restores_availability(self, stocked, location):
        reservation = services.reserve(stocked, 30, location=location)
        services.release(reservation)

        stock = Stock.objects.get(product=stocked, location=location)
        assert stock.quantity_reserved == 0
        assert stock.available == 100

        reservation.refresh_from_db()
        assert reservation.status == ReservationStatus.RELEASED

    def test_commit_reduces_both_physical_and_reserved(self, stocked, location):
        reservation = services.reserve(stocked, 30, location=location)
        services.commit(reservation)

        stock = Stock.objects.get(product=stocked, location=location)
        assert stock.quantity_physical == 70
        assert stock.quantity_reserved == 0
        assert stock.available == 70

    def test_committed_reservation_cannot_be_committed_twice(self, stocked, location):
        reservation = services.reserve(stocked, 10, location=location)
        services.commit(reservation)

        with pytest.raises(BusinessError) as exc:
            services.commit(reservation)
        assert exc.value.code == "INVALID_STATE_TRANSITION"

    def test_double_release_is_safe(self, stocked, location):
        """الإفراج مرتين لا ينتج رصيدًا سالبًا."""
        reservation = services.reserve(stocked, 20, location=location)
        services.release(reservation)
        services.release(reservation)

        stock = Stock.objects.get(product=stocked, location=location)
        assert stock.quantity_reserved == 0

    def test_expired_reservations_are_released(self, stocked, location):
        """
        ⚠️  سلة مهجورة تحجز مخزونًا للأبد تجعل منتجًا متوفرًا يبدو نافدًا.
        """
        reservation = services.reserve(stocked, 40, location=location, ttl=timedelta(seconds=-1))
        assert reservation.is_expired

        released = services.release_expired_reservations()
        assert released == 1

        stock = Stock.objects.get(product=stocked, location=location)
        assert stock.available == 100


# ═══════════════════════════════════════════════════════════
#  FEFO
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestFEFO:
    def test_nearest_expiry_is_consumed_first(self, product, location):
        """
        ⚠️  **FEFO لا FIFO.**

        الترتيب بالأقدم استلامًا يترك دفعة تنتهي غدًا على الرف
        بينما تُباع دفعة صالحة لسنة — فتُهدر الأولى.
        """
        today = timezone.localdate()

        # الأقدم استلامًا لكن الأبعد انتهاءً
        old_receipt = services.receive(
            product,
            50,
            Decimal("10.00"),
            location=location,
            expires_at=today + timedelta(days=365),
        )
        # الأحدث استلامًا لكن الأقرب انتهاءً
        near_expiry = services.receive(
            product,
            50,
            Decimal("12.00"),
            location=location,
            expires_at=today + timedelta(days=30),
        )

        services.sell_immediately(product, 30, location=location)

        near_expiry.refresh_from_db()
        old_receipt.refresh_from_db()

        assert near_expiry.quantity_remaining == 20  # استُهلكت أولًا
        assert old_receipt.quantity_remaining == 50  # لم تُمَس

    def test_consumption_spans_batches_in_order(self, product, location):
        today = timezone.localdate()

        first = services.receive(
            product,
            20,
            Decimal("10.00"),
            location=location,
            expires_at=today + timedelta(days=10),
        )
        second = services.receive(
            product,
            30,
            Decimal("11.00"),
            location=location,
            expires_at=today + timedelta(days=60),
        )

        services.sell_immediately(product, 35, location=location)

        first.refresh_from_db()
        second.refresh_from_db()
        assert first.quantity_remaining == 0
        assert second.quantity_remaining == 15

    def test_batches_without_expiry_come_last(self, product, location):
        """الدفعة بلا تاريخ صلاحية لا تسبق دفعة تنتهي قريبًا."""
        no_expiry = services.receive(product, 40, Decimal("10.00"), location=location)
        expiring = services.receive(
            product,
            40,
            Decimal("10.00"),
            location=location,
            expires_at=timezone.localdate() + timedelta(days=15),
        )

        services.sell_immediately(product, 20, location=location)

        expiring.refresh_from_db()
        no_expiry.refresh_from_db()
        assert expiring.quantity_remaining == 20
        assert no_expiry.quantity_remaining == 40

    def test_expired_batch_is_skipped(self, product, location):
        """الدفعة المنتهية لا تُباع حتى لو كانت الأقرب في الترتيب."""
        expired = services.receive(
            product,
            30,
            Decimal("10.00"),
            location=location,
            expires_at=timezone.localdate() - timedelta(days=1),
        )
        valid = services.receive(
            product,
            30,
            Decimal("10.00"),
            location=location,
            expires_at=timezone.localdate() + timedelta(days=100),
        )

        services.sell_immediately(product, 10, location=location)

        expired.refresh_from_db()
        valid.refresh_from_db()
        assert expired.quantity_remaining == 30  # لم تُمَس
        assert valid.quantity_remaining == 20


# ═══════════════════════════════════════════════════════════
#  لقطة التكلفة —  لـ COGS في المرحلة ٨
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCostSnapshot:
    def test_sale_movement_records_batch_cost(self, product, location):
        """
        ⚠️  **هذا ما يجعل حساب الربح ممكنًا لاحقًا.**

        بلا لقطة التكلفة وقت البيع، لا سبيل لمعرفة ربح بيعة تمت
        قبل شهور — تكلفة الشراء تتغيّر بين الدفعات.
        """
        services.receive(product, 10, Decimal("10.00"), location=location)
        services.receive(product, 10, Decimal("15.00"), location=location)

        services.sell_immediately(product, 15, location=location)

        sales = StockMovement.objects.filter(
            product=product, movement_type=MovementType.SALE
        ).order_by("id")  # ترتيب مستقر — الطوابع الزمنية قد تتطابق

        costs = [(m.quantity, m.unit_cost) for m in sales]
        assert costs == [(10, Decimal("10.00")), (5, Decimal("15.00"))]

    def test_cogs_is_computable_from_movements(self, product, location):
        services.receive(product, 10, Decimal("10.00"), location=location)
        services.receive(product, 10, Decimal("20.00"), location=location)
        services.sell_immediately(product, 15, location=location)

        cogs = sum(
            m.quantity * m.unit_cost
            for m in StockMovement.objects.filter(product=product, movement_type=MovementType.SALE)
            if m.unit_cost is not None
        )
        # ١٠ × ١٠ + ٥ × ٢٠ = ٢٠٠
        assert cogs == Decimal("200.00")


# ═══════════════════════════════════════════════════════════
#  سجل الحركات
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestMovementLedger:
    def test_every_change_leaves_a_movement(self, stocked, location):
        services.reserve(stocked, 10, location=location)
        services.adjust(stocked, 5, location=location, reason="جرد")

        types = set(
            StockMovement.objects.filter(product=stocked).values_list("movement_type", flat=True)
        )
        assert MovementType.RECEIPT in types
        assert MovementType.RESERVE in types
        assert MovementType.ADJUSTMENT_UP in types

    def test_movements_are_append_only(self, stocked):
        """التصحيح بحركة معاكسة لا بتعديل — وإلا فسد السجل."""
        movement = StockMovement.objects.filter(product=stocked).first()
        movement.quantity = 999

        with pytest.raises(ValueError, match="للإضافة فقط"):
            movement.save()

    def test_adjustment_requires_a_reason(self, stocked, location):
        with pytest.raises(BusinessError):
            services.adjust(stocked, 10, location=location, reason="")


# ═══════════════════════════════════════════════════════════
#  التحويل بين المواقع
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestTransfer:
    def test_transfer_moves_stock_between_locations(self, stocked, location, branch):
        services.transfer(stocked, 30, from_location=location, to_location=branch)

        source = Stock.objects.get(product=stocked, location=location)
        destination = Stock.objects.get(product=stocked, location=branch)

        assert source.quantity_physical == 70
        assert destination.quantity_physical == 30

    def test_transfer_creates_paired_movements(self, stocked, location, branch):
        """
        الحركتان في معاملة واحدة — الفصل يعني بضاعة تختفي من الأول
        ولا تظهر في الثاني عند أي فشل جزئي.
        """
        services.transfer(stocked, 20, from_location=location, to_location=branch)

        assert StockMovement.objects.filter(
            movement_type=MovementType.TRANSFER_OUT, location=location
        ).exists()
        assert StockMovement.objects.filter(
            movement_type=MovementType.TRANSFER_IN, location=branch
        ).exists()

    def test_cannot_transfer_more_than_available(self, stocked, location, branch):
        with pytest.raises(BusinessError):
            services.transfer(stocked, 200, from_location=location, to_location=branch)

    def test_cannot_transfer_to_same_location(self, stocked, location):
        with pytest.raises(BusinessError):
            services.transfer(stocked, 10, from_location=location, to_location=location)


# ═══════════════════════════════════════════════════════════
#  التنبيهات
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAlerts:
    def test_low_stock_alert_is_raised(self, stocked, location):
        stock = Stock.objects.get(product=stocked, location=location)
        stock.reorder_point = 20
        stock.save()

        services.sell_immediately(stocked, 85, location=location)

        assert StockAlert.objects.filter(
            product=stocked, alert_type=AlertType.LOW_STOCK, is_resolved=False
        ).exists()

    def test_alerts_are_not_duplicated(self, stocked, location):
        """
        ⚠️  منتج نافد يولّد تنبيهًا مع كل محاولة بيع.

        عشرات التنبيهات لنفس الحالة تجعل شاشة التنبيهات بلا فائدة.
        """
        services.sell_immediately(stocked, 100, location=location)

        for _ in range(5):
            services.check_alerts(stocked, location)

        count = StockAlert.objects.filter(
            product=stocked, alert_type=AlertType.OUT_OF_STOCK, is_resolved=False
        ).count()
        assert count == 1

    def test_alert_resolves_when_stock_returns(self, stocked, location):
        services.sell_immediately(stocked, 100, location=location)
        assert StockAlert.objects.filter(
            product=stocked, alert_type=AlertType.OUT_OF_STOCK, is_resolved=False
        ).exists()

        services.receive(stocked, 50, Decimal("10.00"), location=location)

        assert not StockAlert.objects.filter(
            product=stocked, alert_type=AlertType.OUT_OF_STOCK, is_resolved=False
        ).exists()

    def test_expiring_batches_are_flagged(self, product, location):
        services.receive(
            product,
            10,
            Decimal("10.00"),
            location=location,
            expires_at=timezone.localdate() + timedelta(days=30),
        )

        created = services.check_expiring_batches(days=90)
        assert created == 1

        # التشغيل الثاني لا يكرّر
        assert services.check_expiring_batches(days=90) == 0


# ═══════════════════════════════════════════════════════════
#  الصلاحية
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestExpiry:
    def test_expired_batch_is_quarantined_and_removed_from_available(self, product, location):
        """
        ⚠️  دفعة منتهية تبقى في المتاح تعني بيع دواء منتهي الصلاحية.
        """
        services.receive(
            product,
            40,
            Decimal("10.00"),
            location=location,
            expires_at=timezone.localdate() - timedelta(days=1),
        )

        assert services.quarantine_expired_batches() == 1

        stock = Stock.objects.get(product=product, location=location)
        assert stock.quantity_expired == 40
        assert stock.available == 0
        assert stock.quantity_physical == 40  # ما زالت على الرف

    def test_quarantine_is_idempotent(self, product, location):
        services.receive(
            product,
            10,
            Decimal("10.00"),
            location=location,
            expires_at=timezone.localdate() - timedelta(days=5),
        )

        assert services.quarantine_expired_batches() == 1
        assert services.quarantine_expired_batches() == 0


# ═══════════════════════════════════════════════════════════
#  الأداء
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAvailabilityBatching:
    def test_availability_for_many_products_is_one_query(
        self, location, django_assert_max_num_queries
    ):
        """
        ⚠️  الدالة التي تمنع عودة الـ N+1 إلى الكتالوج.

        الكتالوج يستدعيها مرة لكل صفحة لا مرة لكل منتج.
        """
        category = Category.objects.create(name_ar="فئة", name_en="Category")
        products = [
            Product.objects.create(
                sku=f"BULK-{i:03d}",
                name_ar=f"منتج {i}",
                name_en=f"Product {i}",
                category=category,
            )
            for i in range(20)
        ]
        for product in products:
            services.receive(product, 10, Decimal("5.00"), location=location)

        with django_assert_max_num_queries(2):
            result = services.availability_for([p.pk for p in products])

        assert len(result) == 20
        assert all(entry.available == 10 for entry in result.values())


# ═══════════════════════════════════════════════════════════
#  حدود النطاق
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestDomainBoundaries:
    def test_movement_uses_textual_reference_not_foreign_key(self):
        """
        ⚠️  `inventory` في L3 و`orders` في L6.

        مفتاح أجنبي إلى الطلبات هنا يجعل الاتجاه صاعدًا ويكسر
        الحدود — فالمرجع نصي.
        """
        names = {f.name for f in StockMovement._meta.get_fields()}
        assert "reference_type" in names
        assert "reference_id" in names
        assert "order" not in names
        assert "order_item" not in names

    def test_inventory_does_not_import_orders(self):
        import inspect

        from inventory import services as inventory_services

        source = inspect.getsource(inventory_services)
        assert "from orders" not in source
        assert "import orders" not in source


# ═══════════════════════════════════════════════════════════
#  التزامن —  يحتاج PostgreSQL
# ═══════════════════════════════════════════════════════════


def _is_sqlite() -> bool:
    from django.db import connection

    return connection.vendor == "sqlite"


@pytest.mark.django_db(transaction=True)
@pytest.mark.skipif(
    _is_sqlite(),
    reason=(
        "select_for_update لا يفعل شيئًا على SQLite — "
        "هذا الاختبار يمرّ زائفًا فيُتخطّى صراحةً. "
        "شغّله على PostgreSQL للتحقق الفعلي."
    ),
)
class TestConcurrency:
    """
    ⚠️  **الفجوة المعلنة في المرحلة ٤.**

        SQLite لا ينفّذ `select_for_update` — يتجاهله بصمت. أي
        اختبار تزامن هنا يمرّ بلا أن يثبت شيئًا، وهو أسوأ من غيابه:
        يعطي ثقة زائفة في أخطر مسار في النظام.

        القيد في قاعدة البيانات (`reserved <= physical`) يعمل على
        المحركين ومُختبَر في `TestOverselling`. لكنه يمنع الفساد
        لا التزاحم: تحت PostgreSQL يفشل الطلب الثاني بنظافة،
        وتحت SQLite قد يفشل بخطأ سلامة خام.

        **قبل الإطلاق: ثبّت PostgreSQL وشغّل هذه المجموعة.**
    """

    def test_concurrent_reservations_do_not_oversell(self, stocked, location):
        import threading

        errors = []
        successes = []

        def attempt():
            from django.db import connection

            try:
                services.reserve(stocked, 60, location=location)
                successes.append(1)
            except BusinessError:
                errors.append(1)
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # ١٠٠ متاح · طلبان بـ ٦٠ ⟵ واحد ينجح والآخر يُرفض
        assert len(successes) == 1
        assert len(errors) == 1

        stock = Stock.objects.get(product=stocked, location=location)
        assert stock.quantity_reserved == 60
        assert stock.available == 40
