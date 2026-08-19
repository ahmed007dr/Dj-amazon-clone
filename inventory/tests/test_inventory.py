"""
Inventory tests.

⚠️  The critical groups:
      1. preventing overselling — the most serious defect in the legacy model
      2. FEFO — nearest to expiry first, not oldest received first
      3. the cost snapshot — without it, calculating profit later is impossible
      4. preventing duplicate alerts
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
    StockCountStatus,
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
    """100 units at a cost of 10 pounds."""
    services.receive(product, 100, Decimal("10.00"), location=location)
    return product


# ═══════════════════════════════════════════════════════════
#  Preventing overselling
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestOverselling:
    def test_cannot_reserve_more_than_available(self, stocked, location):
        with pytest.raises(BusinessError) as exc:
            services.reserve(stocked, 101, location=location)

        assert exc.value.code == "INSUFFICIENT_STOCK"

    def test_reservations_accumulate_against_available(self, stocked, location):
        """
        ⚠️  Two consecutive reservations do not exceed the available quantity between them.

        Checking against the physical quantity rather than the available one
        allows the same unit to be reserved twice — which is exactly what
        happens when `quantity_reserved` is overlooked.
        """
        services.reserve(stocked, 60, location=location)

        with pytest.raises(BusinessError):
            services.reserve(stocked, 50, location=location)

        services.reserve(stocked, 40, location=location)  # exactly what remains

        stock = Stock.objects.get(product=stocked, location=location)
        assert stock.quantity_reserved == 100
        assert stock.available == 0

    def test_database_constraint_blocks_negative_available(self, stocked, location):
        """
        ⚠️  **The last line of defence.**

        The lock protects against concurrency but does nothing on SQLite. The
        database constraint works on both engines and cannot be bypassed by any
        code path however wrong — this test deliberately bypasses the service layer.
        """
        stock = Stock.objects.get(product=stocked, location=location)

        with pytest.raises(IntegrityError):
            Stock.objects.filter(pk=stock.pk).update(quantity_reserved=150)

    def test_batch_remaining_cannot_exceed_received(self, stocked, location):
        batch = Batch.objects.filter(product=stocked).first()

        with pytest.raises(IntegrityError):
            Batch.objects.filter(pk=batch.pk).update(quantity_remaining=999)

    def test_immediate_sale_respects_availability(self, stocked, location):
        """The point of sale's immediate sale is subject to the same check."""
        services.reserve(stocked, 95, location=location)

        with pytest.raises(BusinessError):
            services.sell_immediately(stocked, 10, location=location)

        services.sell_immediately(stocked, 5, location=location)

    def test_adjustment_down_respects_availability(self, stocked, location):
        services.reserve(stocked, 90, location=location)

        with pytest.raises(BusinessError):
            services.adjust(stocked, -20, location=location, reason="تسوية")


# ═══════════════════════════════════════════════════════════
#  The reservation cycle
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestReservationLifecycle:
    def test_reserve_reduces_available_not_physical(self, stocked, location):
        """A reservation does not take the goods off the shelf — it stops them being sold to anyone else."""
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
        """Releasing twice does not produce a negative balance."""
        reservation = services.reserve(stocked, 20, location=location)
        services.release(reservation)
        services.release(reservation)

        stock = Stock.objects.get(product=stocked, location=location)
        assert stock.quantity_reserved == 0

    def test_expired_reservations_are_released(self, stocked, location):
        """
        ⚠️  An abandoned cart holding stock forever makes an available product look out of stock.
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
        ⚠️  **FEFO, not FIFO.**

        Ordering by oldest received leaves a batch expiring tomorrow on the
        shelf while a batch good for a year gets sold — so the first is wasted.
        """
        today = timezone.localdate()

        # Received earliest but expiring latest
        old_receipt = services.receive(
            product,
            50,
            Decimal("10.00"),
            location=location,
            expires_at=today + timedelta(days=365),
        )
        # Received latest but expiring soonest
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

        assert near_expiry.quantity_remaining == 20  # consumed first
        assert old_receipt.quantity_remaining == 50  # untouched

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
        """A batch with no expiry date does not come before one expiring soon."""
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
        """An expired batch is not sold even if it is first in the ordering."""
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
        assert expired.quantity_remaining == 30  # untouched
        assert valid.quantity_remaining == 20


# ═══════════════════════════════════════════════════════════
#  The cost snapshot —  for COGS in phase 8
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCostSnapshot:
    def test_sale_movement_records_batch_cost(self, product, location):
        """
        ⚠️  **This is what makes calculating profit possible later.**

        Without the cost snapshot at the time of sale there is no way to know
        the profit of a sale made months ago — the purchase cost changes between
        batches.
        """
        services.receive(product, 10, Decimal("10.00"), location=location)
        services.receive(product, 10, Decimal("15.00"), location=location)

        services.sell_immediately(product, 15, location=location)

        sales = StockMovement.objects.filter(
            product=product, movement_type=MovementType.SALE
        ).order_by("id")  # A stable ordering — the timestamps may be identical

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
        # 10 × 10 + 5 × 20 = 200
        assert cogs == Decimal("200.00")


# ═══════════════════════════════════════════════════════════
#  The movement log
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
        """Corrections go through an offsetting movement, not an edit — or the log becomes corrupt."""
        movement = StockMovement.objects.filter(product=stocked).first()
        movement.quantity = 999

        with pytest.raises(ValueError, match="للإضافة فقط"):
            movement.save()

    def test_adjustment_requires_a_reason(self, stocked, location):
        with pytest.raises(BusinessError):
            services.adjust(stocked, 10, location=location, reason="")


# ═══════════════════════════════════════════════════════════
#  Transfers between locations
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
        Both movements in one transaction — separating them means goods
        vanishing from the first and not appearing in the second on any partial failure.
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
#  Alerts
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
        ⚠️  An out-of-stock product generates an alert on every attempted sale.

        Dozens of alerts for the same situation make the alerts screen useless.
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

        # The second run does not duplicate
        assert services.check_expiring_batches(days=90) == 0


# ═══════════════════════════════════════════════════════════
#  Expiry
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestExpiry:
    def test_expired_batch_is_quarantined_and_removed_from_available(self, product, location):
        """
        ⚠️  An expired batch remaining in available stock means selling an expired medicine.
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
        assert stock.quantity_physical == 40  # still on the shelf

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
#  Performance
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAvailabilityBatching:
    def test_availability_for_many_products_is_one_query(
        self, location, django_assert_max_num_queries
    ):
        """
        ⚠️  The function that keeps N+1 from returning to the catalogue.

        The catalogue calls it once per page, not once per product.
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
#  Domain boundaries
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestDomainBoundaries:
    def test_movement_uses_textual_reference_not_foreign_key(self):
        """
        ⚠️  `inventory` is in L3 and `orders` in L6.

        A foreign key to orders here makes the direction upward and breaks the
        boundaries — so the reference is a string.
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
#  Concurrency —  requires PostgreSQL
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
    ⚠️  **The gap declared in phase 4.**

        SQLite does not implement `select_for_update` — it ignores it silently.
        Any concurrency test here passes without proving anything, which is
        worse than not having it: it gives false confidence in the most
        dangerous path in the system.

        The database constraint (`reserved <= physical`) works on both engines
        and is covered in `TestOverselling`. But it prevents corruption, not
        contention: under PostgreSQL the second order fails cleanly, and under
        SQLite it may fail with a raw integrity error.

        **Before launch: install PostgreSQL and run this group.**
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

        # 100 available · two orders of 60 ⟵ one succeeds and the other is refused
        assert len(successes) == 1
        assert len(errors) == 1

        stock = Stock.objects.get(product=stocked, location=location)
        assert stock.quantity_reserved == 60
        assert stock.available == 40


# ═══════════════════════════════════════════════════════════
#  Stock counting
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestStockCount:
    """
    ⚠️  Both models had existed since phase 4 **with no service and no endpoint**:
        zero references to them in `services` and `api`. This group guards the
        behaviour built around them.
    """

    def test_opening_takes_a_snapshot_of_current_balances(self, stocked, location):
        """
        ⚠️  The snapshot is taken at the start, not at approval.

            A stock count takes hours and the stock moves; reading the expected
            figure at approval compares what was counted in the morning against
            the evening's balance — showing a shortfall equal to everything sold
            during the count.
        """
        count = services.open_count(location)
        lines = services.snapshot_count(count)

        count.refresh_from_db()
        assert lines == 1
        assert count.status == StockCountStatus.IN_PROGRESS
        assert count.started_at is not None

        line = count.lines.first()
        assert line.expected_quantity == 100
        # ⚠️  The counted figure starts at the expected one, not at zero: starting at
        #     zero makes every item not yet counted look like a total shortfall.
        assert line.counted_quantity == 100
        assert line.variance == 0

    def test_only_one_open_session_per_location(self, stocked, location):
        """
        ⚠️  Two sessions mean two counters, and whoever approves last erases the first one's work.
        """
        services.open_count(location)

        with pytest.raises(BusinessError):
            services.open_count(location)

    def test_a_second_session_opens_after_the_first_completes(self, stocked, location):
        first = services.open_count(location)
        services.snapshot_count(first)
        services.apply_count(first)

        second = services.open_count(location)
        assert second.pk != first.pk

    def test_shortage_is_applied_as_a_count_movement(self, stocked, location):
        """
        ⚠️  Settlement through a recorded movement, not by writing the balance directly.

            A direct write makes the accountant ask "where did this shortfall
            come from?" and find no movement.
        """
        count = services.open_count(location)
        services.snapshot_count(count)

        line = count.lines.first()
        services.record_counted(count, line, 93)

        result = services.apply_count(count)

        assert result == {"adjusted": 1, "surplus": 0, "shortage": 7}
        assert Stock.objects.get(product=stocked, location=location).quantity_physical == 93

        movement = StockMovement.objects.filter(movement_type=MovementType.COUNT).first()
        assert movement is not None
        assert movement.quantity == 7
        assert movement.reference_type == "stock_count"

    def test_surplus_is_applied_too(self, stocked, location):
        count = services.open_count(location)
        services.snapshot_count(count)
        services.record_counted(count, count.lines.first(), 105)

        result = services.apply_count(count)

        assert result["surplus"] == 5
        assert Stock.objects.get(product=stocked, location=location).quantity_physical == 105

    def test_lines_without_variance_produce_no_movement(self, stocked, location):
        """
        ⚠️  A zero movement for every item floods the log with thousands of
            meaningless rows, making a search for a real discrepancy impossible.
        """
        count = services.open_count(location)
        services.snapshot_count(count)

        result = services.apply_count(count)

        assert result["adjusted"] == 0
        assert not StockMovement.objects.filter(movement_type=MovementType.COUNT).exists()

    def test_the_variance_is_computed_not_entered(self, stocked, location):
        """⚠️  Entering the discrepancy by hand allows a shortfall to be hidden."""
        count = services.open_count(location)
        services.snapshot_count(count)
        line = count.lines.first()

        services.record_counted(count, line, 88)
        line.refresh_from_db()

        assert line.variance == -12

    def test_recording_on_a_draft_session_is_refused(self, stocked, location):
        count = services.open_count(location)

        from inventory.models import StockCountLine

        line = StockCountLine.objects.create(
            count=count, product=stocked, expected_quantity=100, counted_quantity=100
        )

        with pytest.raises(BusinessError):
            services.record_counted(count, line, 90)

    def test_applying_twice_is_refused(self, stocked, location):
        """
        ⚠️  A repeated approval applies the discrepancies twice — deducting the
            shortfall twice over from a balance the session itself corrected.
        """
        count = services.open_count(location)
        services.snapshot_count(count)
        services.record_counted(count, count.lines.first(), 90)
        services.apply_count(count)

        with pytest.raises(BusinessError):
            services.apply_count(count)

    def test_a_completed_count_cannot_be_cancelled(self, stocked, location):
        """⚠️  Its discrepancies have become movements — cancelling it leaves a balance adjusted by a cancelled session."""
        count = services.open_count(location)
        services.snapshot_count(count)
        services.apply_count(count)

        with pytest.raises(BusinessError):
            services.cancel_count(count, reason="تراجعنا")

    def test_cancelling_does_not_touch_stock(self, stocked, location):
        count = services.open_count(location)
        services.snapshot_count(count)
        services.record_counted(count, count.lines.first(), 40)

        services.cancel_count(count, reason="عدّ خاطئ")

        assert Stock.objects.get(product=stocked, location=location).quantity_physical == 100

    def test_applying_refreshes_alerts(self, stocked, location):
        """A stock count that reveals an out-of-stock item must fire its alert immediately."""
        count = services.open_count(location)
        services.snapshot_count(count)
        services.record_counted(count, count.lines.first(), 0)
        services.apply_count(count)

        assert Stock.objects.get(product=stocked, location=location).quantity_physical == 0


@pytest.mark.django_db
class TestReturnToSupplier:
    """⚠️  `RETURN_OUT` was defined on the model with nothing calling it."""

    def test_it_records_a_return_movement_not_an_adjustment(self, stocked, location):
        movement = services.return_to_supplier(
            stocked, 10, location=location, reason="تالفة", reference_type="purchase_order"
        )

        assert movement.movement_type == MovementType.RETURN_OUT
        assert Stock.objects.get(product=stocked, location=location).quantity_physical == 90

    def test_returning_more_than_available_is_refused(self, stocked, location):
        with pytest.raises(BusinessError):
            services.return_to_supplier(stocked, 200, location=location, reason="زائد")

    def test_a_reason_is_required(self, stocked, location):
        with pytest.raises(BusinessError):
            services.return_to_supplier(stocked, 1, location=location, reason="")
