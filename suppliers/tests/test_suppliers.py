"""
Supplier and purchase order tests.

⚠️  The exit gate for phase 14:

        receiving enters stock **at its cost** · no over-receiving ·
        the supplier account balances · an order with anything received against
        it is never cancelled.

    And the greatest dangers it guards: goods entering with no stock movement ·
    an order invoiced twice · the direction of the debt being confused, so what
    we owe is read as what we are owed.
"""

from datetime import timedelta
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
from inventory.models import LocationKind, Stock, StockLocation, StockMovement
from suppliers import services
from suppliers.models import (
    PurchaseOrderStatus,
    Supplier,
    SupplierLedgerEntry,
    SupplierLedgerKind,
    SupplierProduct,
)

PASSWORD = "Str0ng-Test-Pass!23"


@pytest.fixture
def location(db):
    return StockLocation.objects.create(
        code="sup-loc",
        name_ar="مخزن",
        name_en="Store",
        kind=LocationKind.WAREHOUSE,
        is_default=True,
        is_sellable=True,
    )


@pytest.fixture
def product(db):
    category = Category.objects.create(slug="sup", name_ar="فئة", name_en="Cat")
    return Product.objects.create(
        sku="SUP-1",
        name_ar="صنف",
        name_en="Item",
        category=category,
        base_price=Decimal("100.00"),
    )


@pytest.fixture
def supplier(db):
    return Supplier.objects.create(
        code="acme", name_ar="أكمي للأدوية", name_en="Acme", payment_terms_days=30
    )


@pytest.fixture
def offer(supplier, product):
    return SupplierProduct.objects.create(
        supplier=supplier,
        product=product,
        unit_cost=Decimal("60.00"),
        minimum_order_quantity=10,
        is_preferred=True,
    )


@pytest.fixture
def manager(db):
    user = User.objects.create_user(
        email="buyer@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    user.is_active = True
    user.is_superuser = True
    user.save()
    AdminProfile.objects.create(user=user)
    grant_all_domains(user)
    return user


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ═══════════════════════════════════════════════════════════
#  Purchase orders
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPurchaseOrders:
    def test_price_comes_from_the_offer_not_the_caller(self, supplier, location, offer, product):
        """
        ⚠️  Accepting a sent price means whoever creates the order sets what we
            pay — the first thing exploited in purchasing.
        """
        order = services.create_order(supplier, location, [{"product": product.pk, "quantity": 10}])

        line = order.lines.first()
        assert line.unit_cost == Decimal("60.00")
        assert order.subtotal == Decimal("600.00")

    def test_a_product_the_supplier_does_not_offer_is_refused(self, supplier, location, product):
        with pytest.raises(BusinessError):
            services.create_order(supplier, location, [{"product": product.pk, "quantity": 5}])

    def test_below_minimum_order_quantity_is_refused(self, supplier, location, offer, product):
        with pytest.raises(BusinessError):
            services.create_order(supplier, location, [{"product": product.pk, "quantity": 3}])

    def test_an_inactive_supplier_is_refused(self, supplier, location, offer, product):
        supplier.is_active = False
        supplier.save()

        with pytest.raises(BusinessError):
            services.create_order(supplier, location, [{"product": product.pk, "quantity": 10}])

    def test_sending_records_the_invoice_on_our_account(self, supplier, location, offer, product):
        """
        ⚠️  Posting it on receipt hides an existing obligation: the order was
            sent and the supplier will claim it.
        """
        order = services.create_order(supplier, location, [{"product": product.pk, "quantity": 10}])
        services.send_order(order)

        entry = SupplierLedgerEntry.objects.get(purchase_order=order)
        assert entry.kind == SupplierLedgerKind.INVOICE
        assert entry.amount == Decimal("600.00")
        assert entry.due_on == timezone.localdate() + timedelta(days=30)
        assert services.payable_balance(supplier) == Decimal("600.00")

    def test_one_order_is_invoiced_once(self, supplier, location, offer, product):
        from django.db import IntegrityError, transaction

        order = services.create_order(supplier, location, [{"product": product.pk, "quantity": 10}])
        services.send_order(order)

        with pytest.raises(IntegrityError), transaction.atomic():
            SupplierLedgerEntry.objects.create(
                supplier=supplier,
                purchase_order=order,
                kind=SupplierLedgerKind.INVOICE,
                amount=Decimal("600.00"),
            )

    def test_a_draft_order_cannot_be_received(self, supplier, location, offer, product):
        order = services.create_order(supplier, location, [{"product": product.pk, "quantity": 10}])

        with pytest.raises(BusinessError):
            services.receive_line(order.lines.first(), 5)


# ═══════════════════════════════════════════════════════════
#  Receiving — the exit gate
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestReceiving:
    def _sent_order(self, supplier, location, product, quantity=10):
        order = services.create_order(
            supplier, location, [{"product": product.pk, "quantity": quantity}]
        )
        services.send_order(order)
        return order

    def test_receiving_creates_a_batch_with_the_agreed_cost(
        self, supplier, location, offer, product
    ):
        """
        ⚠️  **The exit gate:** receiving enters stock at its cost.

            And taking today's offer price instead of the order's price makes
            the batch's cost contradict the invoice — so every profit computed
            on it drifts.
        """
        order = self._sent_order(supplier, location, product)

        # The offer changed after sending — it must have no effect
        offer.unit_cost = Decimal("95.00")
        offer.save()

        batch = services.receive_line(order.lines.first(), 10)

        assert batch.unit_cost == Decimal("60.00"), "تكلفة سطر الأمر لا سعر اليوم"
        assert batch.quantity_remaining == 10
        assert Stock.objects.get(product=product, location=location).quantity_physical == 10

    def test_receiving_records_a_stock_movement(self, supplier, location, offer, product):
        """
        ⚠️  Goods entering with no movement mean a balance with no source — and
            a cost of goods sold that cannot be proved later.
        """
        order = self._sent_order(supplier, location, product)
        services.receive_line(order.lines.first(), 10)

        assert StockMovement.objects.filter(product=product, quantity=10).exists()

    def test_partial_receipt_marks_the_order_partial(self, supplier, location, offer, product):
        """
        ⚠️  The supplier sends what they have and completes later — and with no
            partial state the order is closed in full or stays as though nothing had arrived.
        """
        order = self._sent_order(supplier, location, product)
        services.receive_line(order.lines.first(), 4)

        order.refresh_from_db()
        assert order.status == PurchaseOrderStatus.PARTIAL
        assert order.lines.first().outstanding == 6

    def test_completing_the_receipt_closes_the_order(self, supplier, location, offer, product):
        order = self._sent_order(supplier, location, product)
        line = order.lines.first()

        services.receive_line(line, 4)
        line.refresh_from_db()
        services.receive_line(line, 6)

        order.refresh_from_db()
        assert order.status == PurchaseOrderStatus.RECEIVED
        assert order.received_at is not None

    def test_over_receiving_is_refused(self, supplier, location, offer, product):
        """
        ⚠️  Accepting it means entering goods that were never ordered and never
            invoiced — so the reconciliation of the invoice against what was received breaks.
        """
        order = self._sent_order(supplier, location, product)

        with pytest.raises(BusinessError):
            services.receive_line(order.lines.first(), 11)

    def test_expiry_is_carried_into_the_batch(self, supplier, location, offer, product):
        """The expiry is the basis of FEFO — losing it stops the oldest going out first."""
        order = self._sent_order(supplier, location, product)
        expiry = timezone.localdate() + timedelta(days=200)

        batch = services.receive_line(order.lines.first(), 10, expires_at=expiry)

        assert batch.expires_at == expiry


# ═══════════════════════════════════════════════════════════
#  Cancellation and the supplier account
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCancellationAndLedger:
    def test_an_order_with_receipts_cannot_be_cancelled(self, supplier, location, offer, product):
        """
        ⚠️  The goods entered the warehouse; cancelling their order leaves
            batches with no source and reverses an invoice for goods we genuinely own.
        """
        order = services.create_order(supplier, location, [{"product": product.pk, "quantity": 10}])
        services.send_order(order)
        services.receive_line(order.lines.first(), 3)

        with pytest.raises(BusinessError):
            services.cancel_order(order, reason="تراجعنا")

    def test_cancelling_a_sent_order_reverses_the_invoice(self, supplier, location, offer, product):
        """⚠️  A credit note, not a deletion: the invoice was sent and the supplier has recorded
        it."""
        order = services.create_order(supplier, location, [{"product": product.pk, "quantity": 10}])
        services.send_order(order)
        services.cancel_order(order, reason="نفد لديه")

        assert services.payable_balance(supplier) == Decimal("0.00")
        assert SupplierLedgerEntry.objects.filter(
            purchase_order=order, kind=SupplierLedgerKind.INVOICE
        ).exists()
        assert SupplierLedgerEntry.objects.filter(
            purchase_order=order, kind=SupplierLedgerKind.CREDIT_NOTE
        ).exists()

    def test_payment_reduces_what_we_owe(self, supplier, location, offer, product):
        """
        ⚠️  The direction is **inverted** relative to the customer ledger: here we are the debtor.

            Confusing the two directions between the two ledgers is the easiest possible mistake.
        """
        order = services.create_order(supplier, location, [{"product": product.pk, "quantity": 10}])
        services.send_order(order)
        services.record_payment(supplier, Decimal("250.00"))

        assert services.payable_balance(supplier) == Decimal("350.00")

    def test_ledger_entries_are_append_only(self, supplier):
        entry = services.record_payment(supplier, Decimal("100.00"))

        entry.amount = Decimal("999.00")
        with pytest.raises(ValueError):
            entry.save()

    def test_statement_balances(self, supplier, location, offer, product):
        today = timezone.localdate()

        old = services.record_payment(supplier, Decimal("200.00"))
        SupplierLedgerEntry.objects.filter(pk=old.pk).update(
            occurred_on=today - timedelta(days=100)
        )

        order = services.create_order(supplier, location, [{"product": product.pk, "quantity": 10}])
        services.send_order(order)

        result = services.statement(supplier, today - timedelta(days=30), today)

        assert result.opening_balance == Decimal("-200.00")
        assert result.closing_balance == Decimal("400.00")
        movement = sum((e.signed_amount for e in result.entries), Decimal("0"))
        assert result.opening_balance + movement == result.closing_balance


# ═══════════════════════════════════════════════════════════
#  The negotiated price
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestNegotiatedPrice:
    def test_price_defaults_to_the_offer(self, supplier, location, offer, product):
        order = services.create_order(supplier, location, [{"product": product.pk, "quantity": 10}])

        line = order.lines.first()
        assert line.unit_cost == Decimal("60.00")
        assert line.list_cost == Decimal("60.00")
        assert line.cost_variance == Decimal("0.00")

    def test_a_negotiated_price_is_accepted_and_the_offer_is_kept(
        self, supplier, location, offer, product
    ):
        """
        ⚠️  Purchasing is negotiated; and refusing the edit forced the buyer to
            change the offer itself — so the default price changed for every future order.
        """
        order = services.create_order(
            supplier,
            location,
            [{"product": product.pk, "quantity": 10, "unit_cost": Decimal("54.00")}],
        )

        line = order.lines.first()
        assert line.unit_cost == Decimal("54.00")
        assert line.list_cost == Decimal("60.00"), "سعر العرض محفوظ للمقارنة"
        assert line.cost_variance == Decimal("-6.00")
        assert order.subtotal == Decimal("540.00")

        # ⚠️  The offer itself did not change — the next order starts from 60 again
        offer.refresh_from_db()
        assert offer.unit_cost == Decimal("60.00")

    def test_variances_are_reported_for_the_audit_log(self, supplier, location, offer, product):
        order = services.create_order(
            supplier,
            location,
            [{"product": product.pk, "quantity": 10, "unit_cost": Decimal("70.00")}],
        )

        rows = services.price_variances(order)

        assert len(rows) == 1
        assert rows[0]["variance"] == "10.00"
        assert rows[0]["list_cost"] == "60.00"

    def test_matching_prices_produce_no_variance_noise(self, supplier, location, offer, product):
        """A line at the offer price is not logged — the log is for the exception, not the
        routine."""
        order = services.create_order(supplier, location, [{"product": product.pk, "quantity": 10}])

        assert services.price_variances(order) == []

    def test_a_negative_price_is_refused(self, supplier, location, offer, product):
        with pytest.raises(BusinessError):
            services.create_order(
                supplier,
                location,
                [{"product": product.pk, "quantity": 10, "unit_cost": Decimal("-5.00")}],
            )

    def test_the_negotiated_price_flows_into_the_batch(self, supplier, location, offer, product):
        """
        ⚠️  The batch's cost is what we actually paid — not the offer price.

            Taking the offer price makes every profit computed on these goods
            wrong by the negotiated difference.
        """
        order = services.create_order(
            supplier,
            location,
            [{"product": product.pk, "quantity": 10, "unit_cost": Decimal("54.00")}],
        )
        services.send_order(order)

        batch = services.receive_line(order.lines.first(), 10)

        assert batch.unit_cost == Decimal("54.00")


# ═══════════════════════════════════════════════════════════
#  Returns to the supplier
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSupplierReturns:
    def _received(self, supplier, location, product, quantity=10):
        order = services.create_order(
            supplier, location, [{"product": product.pk, "quantity": quantity}]
        )
        services.send_order(order)
        services.receive_line(order.lines.first(), quantity)
        line = order.lines.first()
        line.refresh_from_db()
        return order, line

    def test_a_return_reduces_stock_and_credits_the_account(
        self, supplier, location, offer, product
    ):
        """
        ⚠️  **The gate for the missing line item:** without this path, "returns"
            on the statement stays permanently zero.
        """
        order, line = self._received(supplier, location, product)
        assert Stock.objects.get(product=product, location=location).quantity_physical == 10
        assert services.payable_balance(supplier) == Decimal("600.00")

        entry = services.return_to_supplier(line, 4, reason="تالفة عند الاستلام")

        assert Stock.objects.get(product=product, location=location).quantity_physical == 6
        assert entry.kind == SupplierLedgerKind.CREDIT_NOTE
        assert entry.amount == Decimal("240.00")
        assert services.payable_balance(supplier) == Decimal("360.00")

    def test_a_return_records_a_return_out_movement_not_an_adjustment(
        self, supplier, location, offer, product
    ):
        """
        ⚠️  An adjustment means "the balance was wrong"; a return means "it went
            out to a known party against payment". Conflating them makes the
            discrepancy report count every return as a counting error.
        """
        from inventory.models import MovementType

        order, line = self._received(supplier, location, product)
        services.return_to_supplier(line, 3, reason="خطأ في الصنف")

        movement = StockMovement.objects.filter(
            product=product, movement_type=MovementType.RETURN_OUT
        ).first()

        assert movement is not None
        assert movement.quantity == 3
        assert movement.reference_type == "purchase_order"
        assert movement.reference_id == str(order.pk)

    def test_returning_more_than_received_is_refused(self, supplier, location, offer, product):
        order, line = self._received(supplier, location, product)

        with pytest.raises(BusinessError):
            services.return_to_supplier(line, 11, reason="زائد")

    def test_returning_twice_respects_the_remaining_quantity(
        self, supplier, location, offer, product
    ):
        """
        ⚠️  Returning the same quantity twice creates two credit notes for one
            lot of goods — so the supplier ends up owing us for what we never returned.
        """
        order, line = self._received(supplier, location, product)

        services.return_to_supplier(line, 6, reason="تالفة")
        line.refresh_from_db()
        assert line.quantity_on_hand == 4

        with pytest.raises(BusinessError):
            services.return_to_supplier(line, 5, reason="أكثر من الباقي")

        services.return_to_supplier(line, 4, reason="الباقي")
        line.refresh_from_db()
        assert line.quantity_on_hand == 0

    def test_a_reason_is_required(self, supplier, location, offer, product):
        """With no reason, assessing the supplier becomes impossible: damaged? wrong? surplus?"""
        order, line = self._received(supplier, location, product)

        with pytest.raises(BusinessError):
            services.return_to_supplier(line, 1, reason="   ")

    def test_the_original_invoice_is_never_deleted(self, supplier, location, offer, product):
        """⚠️  The invoice was issued and the supplier recorded it — the correction is a note, not
        an eraser."""
        order, line = self._received(supplier, location, product)
        services.return_to_supplier(line, 10, reason="الشحنة كلها خاطئة")

        assert SupplierLedgerEntry.objects.filter(
            purchase_order=order, kind=SupplierLedgerKind.INVOICE
        ).exists()
        assert services.payable_balance(supplier) == Decimal("0.00")

    def test_returns_appear_in_the_statement_totals(self, supplier, location, offer, product):
        order, line = self._received(supplier, location, product)
        services.return_to_supplier(line, 5, reason="تالفة")
        services.record_payment(supplier, Decimal("100.00"))

        today = timezone.localdate()
        result = services.statement(supplier, today, today)

        assert result.invoiced == Decimal("600.00")
        assert result.paid == Decimal("100.00")
        assert result.returned == Decimal("300.00")
        assert result.closing_balance == Decimal("200.00")


# ═══════════════════════════════════════════════════════════
#  The list — balance, purchases and filters
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSupplierList:
    def test_balance_and_purchases_come_from_one_query(
        self, supplier, location, offer, product, django_assert_num_queries
    ):
        """
        ⚠️  **The difference between a screen that works and one that stalls.**

            Calling `payable_balance()` per row means one query per supplier on
            the most frequently opened screen.
        """
        order = services.create_order(supplier, location, [{"product": product.pk, "quantity": 10}])
        services.send_order(order)

        other = Supplier.objects.create(code="beta2", name_ar="بيتا", name_en="Beta")
        second = services.create_order(
            supplier, location, [{"product": product.pk, "quantity": 20}]
        )
        services.send_order(second)

        # One query however many suppliers there are
        with django_assert_num_queries(1):
            rows = list(services.annotated_suppliers().order_by("name_ar"))

        by_code = {row.code: row for row in rows}
        assert by_code["acme"].payable == Decimal("1800.00")
        assert by_code["acme"].total_purchases == Decimal("1800.00")
        assert by_code[other.code].payable == Decimal("0.00")

    def test_totals_are_not_inflated_by_joining(self, supplier, location, offer, product):
        """
        ⚠️  Joining two tables in one query multiplies the rows: every account
            movement repeats once per purchase order and vice versa — so an
            inflated balance and purchase total come out with nothing looking wrong.
        """
        for _ in range(3):
            order = services.create_order(
                supplier, location, [{"product": product.pk, "quantity": 10}]
            )
            services.send_order(order)

        services.record_payment(supplier, Decimal("100.00"))

        row = services.annotated_suppliers().get(pk=supplier.pk)

        assert row.total_purchases == Decimal("1800.00"), "٣ × ٦٠٠ لا مضروبة في الحركات"
        assert row.payable == Decimal("1700.00")

    def test_draft_orders_are_not_counted_as_purchases(self, supplier, location, offer, product):
        """A draft was never sent — no obligation and no purchase."""
        services.create_order(supplier, location, [{"product": product.pk, "quantity": 10}])

        row = services.annotated_suppliers().get(pk=supplier.pk)
        assert row.total_purchases == Decimal("0.00")

    def test_the_inactive_filter_actually_filters(self, manager, supplier):
        """
        ⚠️  The old condition was `== "true"` only, so `status=inactive`
            **did nothing**: the admin asked for the disabled ones and saw everyone.
        """
        Supplier.objects.create(code="off", name_ar="موقوف", name_en="Off", is_active=False)

        client = client_for(manager)
        active = client.get(reverse("v1:suppliers:list"), {"status": "active"})
        inactive = client.get(reverse("v1:suppliers:list"), {"status": "inactive"})

        assert [row["code"] for row in inactive.data["results"]] == ["off"]
        assert "off" not in [row["code"] for row in active.data["results"]]

    def test_the_debt_filter_selects_only_indebted_suppliers(
        self, manager, supplier, location, offer, product
    ):
        Supplier.objects.create(code="clear", name_ar="بلا مديونية", name_en="Clear")
        order = services.create_order(supplier, location, [{"product": product.pk, "quantity": 10}])
        services.send_order(order)

        response = client_for(manager).get(reverse("v1:suppliers:list"), {"has_debt": "true"})

        assert [row["code"] for row in response.data["results"]] == ["acme"]

    def test_the_overdue_filter_finds_late_invoices(
        self, manager, supplier, location, offer, product
    ):
        order = services.create_order(supplier, location, [{"product": product.pk, "quantity": 10}])
        services.send_order(order)
        SupplierLedgerEntry.objects.filter(purchase_order=order).update(
            due_on=timezone.localdate() - timedelta(days=5)
        )

        response = client_for(manager).get(reverse("v1:suppliers:list"), {"overdue": "true"})

        assert [row["code"] for row in response.data["results"]] == ["acme"]

    def test_the_order_payload_carries_the_return_ceiling_and_variance(
        self, manager, supplier, location, offer, product
    ):
        """
        ⚠️  A field declared on the serializer does not go out unless it is
            listed in `fields` — it drops silently with no error, so the screen
            builds on `undefined`.
        """
        order = services.create_order(
            supplier,
            location,
            [{"product": product.pk, "quantity": 10, "unit_cost": Decimal("54.00")}],
        )
        services.send_order(order)
        services.receive_line(order.lines.first(), 10)

        response = client_for(manager).get(reverse("v1:suppliers:order-detail", args=[order.pk]))
        line = response.data["lines"][0]

        assert line["quantity_on_hand"] == 10
        assert line["quantity_returned"] == 0
        assert line["list_cost"] == "60.00"
        assert line["cost_variance"] == "-6.00"

    def test_the_list_carries_balance_and_purchases(
        self, manager, supplier, location, offer, product
    ):
        order = services.create_order(supplier, location, [{"product": product.pk, "quantity": 10}])
        services.send_order(order)

        response = client_for(manager).get(reverse("v1:suppliers:list"))
        row = next(r for r in response.data["results"] if r["code"] == "acme")

        assert row["payable"] == "600.00"
        assert row["total_purchases"] == "600.00"
        assert row["has_overdue"] is False


# ═══════════════════════════════════════════════════════════
#  Supplier offers — the basis of the marketplace
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestMarketplaceFoundation:
    def test_a_product_can_have_many_suppliers(self, product, supplier):
        """
        ⚠️  This table is what makes "one product from several suppliers" possible.

            With no intermediary, every product has one fixed supplier, and
            changing it loses the purchase history from the previous one.
        """
        cheaper = Supplier.objects.create(code="beta", name_ar="بيتا", name_en="Beta")

        SupplierProduct.objects.create(
            supplier=supplier, product=product, unit_cost=Decimal("60.00"), is_preferred=True
        )
        SupplierProduct.objects.create(
            supplier=cheaper, product=product, unit_cost=Decimal("52.00")
        )

        offers = services.offers_for(product)

        assert len(offers) == 2
        assert offers[0]["unit_cost"] == "52.00", "الأرخص أولًا"
        assert offers[1]["is_preferred"] is True

    def test_only_one_preferred_supplier_per_product(self, product, supplier):
        """
        ⚠️  Two preferred ones make the automatic purchase order unable to
            choose — so the choice becomes a matter of query ordering.
        """
        from django.db import IntegrityError, transaction

        other = Supplier.objects.create(code="gamma", name_ar="جاما", name_en="Gamma")
        SupplierProduct.objects.create(
            supplier=supplier, product=product, unit_cost=Decimal("60.00"), is_preferred=True
        )

        with pytest.raises(IntegrityError), transaction.atomic():
            SupplierProduct.objects.create(
                supplier=other, product=product, unit_cost=Decimal("55.00"), is_preferred=True
            )

    def test_the_same_supplier_cannot_offer_twice(self, product, supplier):
        from django.db import IntegrityError, transaction

        SupplierProduct.objects.create(
            supplier=supplier, product=product, unit_cost=Decimal("60.00")
        )

        with pytest.raises(IntegrityError), transaction.atomic():
            SupplierProduct.objects.create(
                supplier=supplier, product=product, unit_cost=Decimal("58.00")
            )

    def test_reorder_flags_products_without_a_supplier(self, product, location):
        """
        ⚠️  Excluding an item with no supplier makes the most important shortage
            vanish from the purchasing screen — and the reason is that it has no
            supplier, which is what needs dealing with.
        """
        from inventory import services as inventory_services

        inventory_services.receive(product, 1, Decimal("60.00"), location=location)
        Stock.objects.filter(product=product, location=location).update(reorder_point=50)

        rows = services.reorder_suggestions(location)

        assert len(rows) == 1
        assert rows[0]["sku"] == "SUP-1"
        assert rows[0]["has_supplier"] is False

    def test_reorder_picks_the_preferred_supplier(self, product, location, supplier, offer):
        from inventory import services as inventory_services

        inventory_services.receive(product, 1, Decimal("60.00"), location=location)
        Stock.objects.filter(product=product, location=location).update(reorder_point=50)

        rows = services.reorder_suggestions(location)

        assert rows[0]["has_supplier"] is True
        assert rows[0]["supplier_name"] == "أكمي للأدوية"


# ═══════════════════════════════════════════════════════════
#  Permissions
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPermissions:
    def test_a_customer_cannot_read_purchase_prices(self, db):
        """
        ⚠️  Purchase prices are the store's margin laid bare — leaking them lets
            any customer learn what we paid for what we sell them.
        """
        customer = User.objects.create_user(email="shopper@test.local", password=PASSWORD)
        customer.is_active = True
        customer.save()

        assert client_for(customer).get(reverse("v1:suppliers:list")).status_code == 403

    def test_a_plain_admin_without_the_permission_is_refused(self, db):
        staff = User.objects.create_user(
            email="plain-admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
        )
        staff.is_active = True
        staff.save()
        AdminProfile.objects.create(user=staff)
        grant_all_domains(staff)

        assert client_for(staff).get(reverse("v1:suppliers:list")).status_code == 403

    def test_the_owner_passes(self, manager):
        assert client_for(manager).get(reverse("v1:suppliers:list")).status_code == 200

    def test_receiving_a_line_of_another_order_is_refused(
        self, manager, supplier, location, offer, product
    ):
        """⚠️  Filtered by the order: another order's line id used to be receivable here."""
        first = services.create_order(supplier, location, [{"product": product.pk, "quantity": 10}])
        second = services.create_order(
            supplier, location, [{"product": product.pk, "quantity": 10}]
        )
        services.send_order(first)
        services.send_order(second)

        response = client_for(manager).post(
            reverse("v1:suppliers:order-receive", args=[first.pk]),
            {"line": str(second.lines.first().pk), "quantity": 1},
            format="json",
        )

        assert response.status_code == 404
