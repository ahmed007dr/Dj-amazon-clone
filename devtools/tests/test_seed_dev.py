"""
Development seed tests.

⚠️  The seed is not decorative data — it is **the first thing any new developer
    tries**, and the first thing the frontend builds its screens on.

    A seed that breaks silently means an hour lost before a single line is
    written; and a seed that doubles on the second run means false stock figures
    that everything afterwards is built on.
"""

from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import AccountStatus, User, VerificationStatus
from catalog.models import Product
from devtools.seeds import people
from inventory.models import Batch, Stock, StockMovement
from orders.models import Order
from pricing.models import PriceList
from promotions.models import Coupon


@pytest.fixture
def dev_mode(settings):
    """
    ⚠️  Django always forces `DEBUG=False` in tests.

        And rightly so — but it means any test of the seed runs into its guard.
        Lifting it here is deliberate and confined to these tests alone.
    """
    settings.DEBUG = True


@pytest.fixture
def seeded(db, dev_mode):
    call_command("seed_dev", verbosity=0)


# ═══════════════════════════════════════════════════════════
#  Safety
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_refuses_to_run_outside_debug(settings):
    """
    ⚠️  The seed creates accounts with a well-known, published password.

        The first barrier is that the app is not installed in production; this
        catches the case where it is installed by mistake.
    """
    settings.DEBUG = False

    with pytest.raises(CommandError, match="التطوير"):
        call_command("seed_dev", verbosity=0)

    assert not User.objects.exists()


# ═══════════════════════════════════════════════════════════
#  Repeated runs
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_reset_clears_then_rebuilds(seeded):
    """
    ⚠️  `--reset` deletes everything.

        Testing it is not a luxury: its failure path leaves a half-deleted
        database with broken foreign key constraints — which is worse than an
        empty one.
    """
    original_ids = set(Product.objects.values_list("id", flat=True))

    call_command("seed_dev", "--reset", verbosity=0)

    rebuilt_ids = set(Product.objects.values_list("id", flat=True))

    assert Product.objects.count() == len(original_ids)
    assert not (original_ids & rebuilt_ids), "الحذف لم يقع فعلًا"
    assert Order.objects.exists()


@pytest.mark.django_db
def test_running_twice_changes_nothing(seeded):
    """
    ⚠️  **The most important property.**

        A seed that doubles the stock on every run makes every number after it
        false — and the discovery comes weeks later, when the stock count
        matches nothing.
    """
    before = {
        "products": Product.objects.count(),
        "users": User.objects.count(),
        "batches": Batch.objects.count(),
        "movements": StockMovement.objects.count(),
        "orders": Order.objects.count(),
        "physical": sum(Stock.objects.values_list("quantity_physical", flat=True)),
    }

    call_command("seed_dev", verbosity=0)

    after = {
        "products": Product.objects.count(),
        "users": User.objects.count(),
        "batches": Batch.objects.count(),
        "movements": StockMovement.objects.count(),
        "orders": Order.objects.count(),
        "physical": sum(Stock.objects.values_list("quantity_physical", flat=True)),
    }

    assert before == after


@pytest.mark.django_db
def test_minimal_seeds_structure_without_data(db, dev_mode):
    call_command("seed_dev", "--minimal", verbosity=0)

    from inventory.models import StockLocation
    from shipping.models import ShippingZone

    assert StockLocation.objects.exists()
    assert ShippingZone.objects.exists()
    assert not Product.objects.exists()
    assert not User.objects.exists()


# ═══════════════════════════════════════════════════════════
#  The data is fit to work with
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSeededData:
    def test_every_seeded_account_can_sign_in(self, seeded):
        """
        ⚠️  A seeded account whose password does not work is worse than no
            account — the developer assumes the fault is in authentication, not in the seed.
        """
        for user in User.objects.all():
            assert user.check_password(people.PASSWORD), user.email

    def test_suspended_account_exists_and_is_suspended(self, seeded):
        suspended = User.objects.get(email="suspended@dev.local")
        assert suspended.status == AccountStatus.SUSPENDED

    def test_verification_queue_is_not_empty(self, seeded):
        """The manual review queue has to be testable."""
        assert User.objects.filter(verification_status=VerificationStatus.PENDING).exists()
        assert User.objects.filter(verification_status=VerificationStatus.REJECTED).exists()

    def test_default_price_list_exists(self, seeded):
        assert PriceList.get_default() is not None

    def test_seeded_palettes_pass_contrast(self, seeded):
        """
        ⚠️  A palette the contrast check rejects **cannot be activated at all**.

            So a seed with failing colours means a system that does not boot —
            and the test lives here rather than in `branding` because the seed
            lives in `devtools`, which is above it in the layer diagram.
        """
        from branding.models import BrandProfile

        profile = BrandProfile.get_active()
        assert profile is not None

        for palette in profile.palettes.all():
            palette.clean()  # does not raise

    def test_student_prices_are_independent_not_derived(self, seeded):
        """
        ⚠️  Business rule 9 — a separate list, not a discount percentage.

            Were it a percentage, the student price would be a function of the
            retail price; here it is an independent number audited on its own.
        """
        student = PriceList.objects.get(code="student")
        rule = student.rules.get(product__sku="STE-CLS")

        assert rule.unit_price == Decimal("690.00")
        assert rule.unit_price != Product.objects.get(sku="STE-CLS").base_price

    def test_stock_movements_exist_for_every_batch(self, seeded):
        """
        ⚠️  A batch with no movement means stock with an empty ledger — the
            first stock count reveals a discrepancy nobody can explain. Going
            through the service prevents that.
        """
        assert Batch.objects.exists()
        for batch in Batch.objects.all():
            assert batch.movements.exists(), batch.number

    def test_edge_cases_are_present(self, seeded):
        """The cases nobody sees until a customer complains."""
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.localdate()

        # An already-expired batch
        assert Batch.objects.filter(expires_at__lt=today).exists()
        # A batch about to expire — inside the alert window
        assert Batch.objects.filter(
            expires_at__gte=today, expires_at__lte=today + timedelta(days=90)
        ).exists()
        # An expired coupon
        assert Coupon.objects.filter(code="EXPIRED2025").exists()

    def test_a_variant_is_out_of_stock_while_its_product_is_not(self, seeded):
        """
        ⚠️  This is the difference that makes tracking stock on the variant
            necessary: the product is "available" while one of its variants is not.
        """
        from catalog.models import ProductVariant

        out_of_stock = ProductVariant.objects.get(sku="GLV-NIT-L")
        in_stock = ProductVariant.objects.get(sku="GLV-NIT-M")

        assert not Stock.objects.filter(variant=out_of_stock, quantity_physical__gt=0).exists()
        assert Stock.objects.filter(variant=in_stock, quantity_physical__gt=0).exists()

    def test_orders_cover_multiple_statuses(self, seeded):
        statuses = set(Order.objects.values_list("status", flat=True))
        assert len(statuses) >= 3

    def test_orders_carry_price_snapshots(self, seeded):
        """
        ⚠️  A line with no price snapshot makes every old invoice change as
            today's product price changes. (ADR-30)
        """
        for order in Order.objects.all():
            for line in order.lines.all():
                assert line.product_sku
                assert line.product_name_ar
                assert line.unit_price > 0

    def test_orders_reserved_stock(self, seeded):
        """An order that reserves no stock sells what does not exist."""
        assert Stock.objects.filter(quantity_reserved__gt=0).exists()

    def test_payment_providers_are_available(self, seeded):
        from payments import services
        from payments.models import PaymentMethodKind

        providers = services.available_providers(
            method=PaymentMethodKind.CASH_ON_DELIVERY,
            channel="ONLINE",
            amount=Decimal("300"),
        )
        assert providers

    def test_student_bundles_reference_real_products(self, seeded):
        from academic.models import StudyBundle

        for bundle in StudyBundle.objects.all():
            assert bundle.items.exists(), bundle.slug
