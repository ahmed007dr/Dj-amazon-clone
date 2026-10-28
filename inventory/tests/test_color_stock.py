"""
Stock per colour — availability, the "assign existing stock" step, and the guards.

⚠️  The product's stock is keyed on `(product, variant, location)`. Adding the first
    colour to a product that already holds stock leaves those units on `variant=None`,
    where the cart can no longer reach them. The tests under `TestAssign` pin that
    the admin's explicit choice moves them — through recorded movements, with the
    batches, and without changing the total on the shelf.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from catalog import colors as color_services
from catalog.models import Category, Product, ProductColor, ProductVariant
from catalog.tests.color_support import make_admin_client, make_customer_client
from core.errors import BusinessError
from core.models.audit import AuditAction, AuditLog
from inventory import services
from inventory.models import (
    Batch,
    LocationKind,
    MovementType,
    Stock,
    StockLocation,
    StockMovement,
)


@pytest.fixture
def main(db):
    return StockLocation.objects.create(
        code="main", name_ar="الرئيسي", name_en="Main", is_default=True
    )


@pytest.fixture
def branch(db):
    return StockLocation.objects.create(
        code="branch", name_ar="فرع", name_en="Branch", kind=LocationKind.BRANCH
    )


@pytest.fixture
def product(db):
    category = Category.objects.create(name_ar="ملابس", name_en="Apparel")
    return Product.objects.create(
        sku="CS-001", name_ar="قميص", name_en="Top", category=category, base_price=Decimal("100.00")
    )


@pytest.fixture
def blue(product):
    return color_services.create_color(product, name_ar="أزرق", name_en="Blue", hex="#1E40AF")


@pytest.fixture
def red(product):
    return color_services.create_color(product, name_ar="أحمر", name_en="Red", hex="#B91C1C")


@pytest.fixture
def admin_client(db):
    return make_admin_client("stock-admin@test.local")


# ═══════════════════════════════════════════════════════════
#  Reading
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPerVariantAvailability:
    def test_every_sellable_variant_is_present_even_with_no_stock_row(
        self, product, blue, red, main
    ):
        services.receive(product, 4, Decimal("10.00"), location=main, variant=blue.variants.get())

        result = services.availability_by_variant([product.pk])[str(product.pk)]

        assert result[blue.variants.get().pk] == 4
        assert result[red.variants.get().pk] == 0, "لا صفّ = صفر لا «مجهول»"

    def test_a_deactivated_colours_stock_is_not_reported(self, product, blue, red, main):
        services.receive(product, 4, Decimal("10.00"), location=main, variant=blue.variants.get())
        color_services.update_color(blue, is_active=False)

        result = services.availability_by_variant([product.pk])[str(product.pk)]

        assert blue.variants.get().pk not in result

    def test_a_non_sellable_location_is_left_out(self, product, blue, main):
        quarantine = StockLocation.objects.create(
            code="quar", name_ar="حجر", name_en="Quarantine", is_sellable=False
        )
        services.receive(
            product, 9, Decimal("10.00"), location=quarantine, variant=blue.variants.get()
        )

        assert (
            services.availability_by_variant([product.pk])[str(product.pk)][blue.variants.get().pk]
            == 0
        )

    def test_the_public_endpoint_masks_big_numbers(self, client, product, blue, red, main):
        services.receive(product, 50, Decimal("10.00"), location=main, variant=blue.variants.get())
        services.receive(product, 2, Decimal("10.00"), location=main, variant=red.variants.get())

        response = client.get(reverse("v1:inventory:product-availability", args=[product.pk]))

        assert response.status_code == 200
        by_variant = response.data["variants"]
        assert by_variant[str(blue.variants.get().pk)] == {
            "is_available": True,
            "is_low": False,
            "available": None,
        }
        assert by_variant[str(red.variants.get().pk)]["available"] == 2
        assert response.data["is_available"] is True

    def test_the_public_endpoint_never_shows_unassigned_stock(self, client, product, blue, main):
        services.receive(product, 10, Decimal("10.00"), location=main)  # on no variant

        response = client.get(reverse("v1:inventory:product-availability", args=[product.pk]))

        assert list(response.data["variants"]) == [str(blue.variants.get().pk)]
        assert response.data["is_available"] is False

    def test_a_product_without_variants_answers_with_its_total(self, client, product, main):
        services.receive(product, 3, Decimal("10.00"), location=main)

        response = client.get(reverse("v1:inventory:product-availability", args=[product.pk]))

        assert response.data["variants"] == {} and response.data["is_available"] is True

    def test_colour_stock_facts_sum_over_every_variant_of_the_colour(
        self, product, blue, main, branch
    ):
        size = ProductVariant.objects.create(
            product=product, color=blue, sku="CS-001-BLUE-L", name_ar="L", name_en="L"
        )
        services.receive(product, 3, Decimal("10.00"), location=main, variant=blue.variants.first())
        services.receive(product, 4, Decimal("10.00"), location=branch, variant=size)

        facts = services.color_stock_facts(product, [blue], None)[str(blue.pk)]

        assert facts["quantity"] == 7
        assert facts["available"] is None and facts["is_low"] is False  # 7 is above the threshold


# ═══════════════════════════════════════════════════════════
#  Assigning the un-assigned stock to a colour
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAssign:
    def test_the_units_move_and_the_total_does_not_change(self, product, blue, main, branch):
        services.receive(product, 10, Decimal("10.00"), location=main)
        services.receive(product, 5, Decimal("10.00"), location=branch)
        variant = blue.variants.get()
        total_before = sum(Stock.objects.values_list("quantity_physical", flat=True))

        result = services.assign_unvariated_stock(product, variant)

        assert result["moved"] == 15
        assert services.available_quantity(product, variant=variant) == 15
        assert services.available_quantity(product) == 0
        assert sum(Stock.objects.values_list("quantity_physical", flat=True)) == total_before

    def test_movements_are_recorded_on_both_rows(self, product, blue, main):
        services.receive(product, 10, Decimal("10.00"), location=main)
        variant = blue.variants.get()

        services.assign_unvariated_stock(product, variant)

        moves = StockMovement.objects.filter(reference_type="variant_assignment")
        down = moves.get(movement_type=MovementType.ADJUSTMENT_DOWN)
        up = moves.get(movement_type=MovementType.ADJUSTMENT_UP)
        assert down.variant_id is None and down.quantity == 10 and down.balance_after == 0
        assert up.variant_id == variant.pk and up.quantity == 10 and up.balance_after == 10
        assert up.reference_id == str(variant.pk)

    def test_only_the_available_units_move(self, product, blue, main):
        services.receive(product, 10, Decimal("10.00"), location=main)
        services.reserve(product, 3, location=main)
        services.mark_damaged(product, 2, location=main, reason="كسر")
        variant = blue.variants.get()

        result = services.assign_unvariated_stock(product, variant)

        assert result["moved"] == 5
        old = Stock.objects.get(product=product, variant__isnull=True)
        assert (old.quantity_physical, old.quantity_reserved, old.quantity_damaged) == (5, 3, 2)

    def test_the_batches_travel_with_the_stock_and_a_split_keeps_the_cost(
        self, product, blue, main
    ):
        soon = timezone.localdate() + timedelta(days=30)
        services.receive(product, 6, Decimal("10.00"), location=main, expires_at=soon)
        services.receive(product, 10, Decimal("12.00"), location=main)
        services.reserve(product, 4, location=main)  # 12 available of 16
        variant = blue.variants.get()

        services.assign_unvariated_stock(product, variant)

        moved = Batch.objects.filter(product=product, variant=variant)
        assert sum(b.quantity_remaining for b in moved) == 12
        left = Batch.objects.get(product=product, variant__isnull=True, quantity_remaining__gt=0)
        assert left.quantity_remaining == 4
        # Cost survives: the split half is costed like the batch it came from
        assert {b.unit_cost for b in moved} == {Decimal("10.00"), Decimal("12.00")}
        assert all(b.quantity_remaining <= b.quantity_received for b in Batch.objects.all())

    def test_a_sale_afterwards_consumes_the_moved_batch_with_its_cost(self, product, blue, main):
        services.receive(product, 10, Decimal("10.00"), location=main)
        variant = blue.variants.get()
        services.assign_unvariated_stock(product, variant)

        movements = services.sell_immediately(product, 2, location=main, variant=variant)

        assert all(m.batch_id is not None and m.unit_cost == Decimal("10.00") for m in movements)

    def test_nothing_to_move_moves_nothing(self, product, blue, main):
        assert services.assign_unvariated_stock(product, blue.variants.get())["moved"] == 0

    def test_a_single_location_can_be_chosen(self, product, blue, main, branch):
        services.receive(product, 10, Decimal("10.00"), location=main)
        services.receive(product, 5, Decimal("10.00"), location=branch)

        result = services.assign_unvariated_stock(product, blue.variants.get(), location=branch)

        assert result["moved"] == 5
        assert services.available_quantity(product, location=main) == 10

    def test_a_variant_of_another_product_is_refused(self, product, blue, main):
        other = Product.objects.create(
            sku="CS-002", name_ar="س", name_en="S", category=product.category
        )
        foreign = color_services.create_color(other, name_ar="أ", name_en="A", hex="#111111")
        services.receive(product, 10, Decimal("10.00"), location=main)

        with pytest.raises(BusinessError):
            services.assign_unvariated_stock(product, foreign.variants.get())

    def test_unassigned_stock_is_reported_per_location(self, product, blue, main, branch):
        services.receive(product, 10, Decimal("10.00"), location=main)
        services.receive(product, 5, Decimal("10.00"), location=branch)

        rows = services.unassigned_stock(product)

        assert {(row["location_code"], row["quantity"]) for row in rows} == {
            ("main", 10),
            ("branch", 5),
        }


@pytest.mark.django_db
class TestAssignAPI:
    def test_assigning_by_colour_moves_the_stock_and_is_audited(
        self, admin_client, product, blue, main
    ):
        services.receive(product, 10, Decimal("10.00"), location=main)

        probe = admin_client.get(reverse("v1:inventory:unassigned-stock"), {"product": product.pk})
        assert probe.data["total"] == 10

        response = admin_client.post(
            reverse("v1:inventory:assign-stock"),
            {"product": str(product.pk), "color": str(blue.pk)},
            format="json",
        )

        assert response.status_code == 200, response.data
        assert response.data["moved"] == 10
        assert services.available_quantity(product, variant=blue.variants.get()) == 10
        assert AuditLog.objects.filter(action=AuditAction.STOCK_CHANGE).count() == 2
        assert (
            admin_client.get(
                reverse("v1:inventory:unassigned-stock"), {"product": product.pk}
            ).data["total"]
            == 0
        )

    def test_nothing_to_assign_is_a_409(self, admin_client, product, blue, main):
        response = admin_client.post(
            reverse("v1:inventory:assign-stock"),
            {"product": str(product.pk), "color": str(blue.pk)},
            format="json",
        )

        assert response.status_code == 409

    def test_exactly_one_of_colour_and_variant(self, admin_client, product, blue, main):
        for body in (
            {"product": str(product.pk)},
            {
                "product": str(product.pk),
                "color": str(blue.pk),
                "variant": str(blue.variants.get().pk),
            },
        ):
            assert (
                admin_client.post(
                    reverse("v1:inventory:assign-stock"), body, format="json"
                ).status_code
                == 400
            )

    def test_another_products_colour_is_a_404(self, admin_client, product, blue, main):
        other = Product.objects.create(
            sku="CS-002", name_ar="س", name_en="S", category=product.category
        )
        foreign = color_services.create_color(other, name_ar="أ", name_en="A", hex="#111111")

        response = admin_client.post(
            reverse("v1:inventory:assign-stock"),
            {"product": str(product.pk), "color": str(foreign.pk)},
            format="json",
        )

        assert response.status_code == 404

    def test_a_customer_cannot(self, product, blue, main):
        client = make_customer_client("stock-customer@test.local")

        response = client.post(
            reverse("v1:inventory:assign-stock"),
            {"product": str(product.pk), "color": str(blue.pk)},
            format="json",
        )

        assert response.status_code == 403


# ═══════════════════════════════════════════════════════════
#  The commands refuse a wrong or missing variant
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCommandGuards:
    def receive(self, client, product, variant=None, quantity=5):
        body = {"product": str(product.pk), "quantity": quantity, "unit_cost": "10.00"}
        if variant is not None:
            body["variant"] = str(variant.pk)
        return client.post(reverse("v1:inventory:receive"), body, format="json")

    def test_receiving_into_a_colour_works(self, admin_client, product, blue, main):
        response = self.receive(admin_client, product, blue.variants.get())

        assert response.status_code == 201, response.data
        assert services.available_quantity(product, variant=blue.variants.get()) == 5

    def test_receiving_without_a_variant_is_refused_once_the_product_has_colours(
        self, admin_client, product, blue, main
    ):
        """⚠️  Units on "no variant" would be unsellable and nobody would notice."""
        assert self.receive(admin_client, product).status_code == 400
        assert not Stock.objects.filter(product=product, quantity_physical__gt=0).exists()

    def test_receiving_without_a_variant_still_works_for_a_plain_product(
        self, admin_client, product, main
    ):
        assert self.receive(admin_client, product).status_code == 201

    def test_a_variant_of_another_product_is_refused(self, admin_client, product, blue, main):
        other = Product.objects.create(
            sku="CS-002", name_ar="س", name_en="S", category=product.category
        )
        foreign = color_services.create_color(other, name_ar="أ", name_en="A", hex="#111111")

        response = self.receive(admin_client, product, foreign.variants.get())

        assert response.status_code == 400
        assert not Stock.objects.filter(variant=foreign.variants.get()).exists()

    def test_a_positive_adjustment_needs_a_variant_but_a_cleanup_does_not(
        self, admin_client, product, blue, main
    ):
        services.receive(product, 4, Decimal("10.00"), location=main)  # legacy, unassigned

        up = admin_client.post(
            reverse("v1:inventory:adjust"),
            {"product": str(product.pk), "quantity": 2, "reason": "جرد"},
            format="json",
        )
        down = admin_client.post(
            reverse("v1:inventory:adjust"),
            {"product": str(product.pk), "quantity": -2, "reason": "تنظيف"},
            format="json",
        )

        assert up.status_code == 400 and down.status_code == 201

    def test_the_stock_list_names_the_variant(self, admin_client, product, blue, main):
        services.receive(product, 4, Decimal("10.00"), location=main, variant=blue.variants.get())

        row = admin_client.get(reverse("v1:inventory:stock"), {"product": product.pk}).data[
            "results"
        ][0]

        assert row["variant_sku"] == "CS-001-BLUE"
        assert row["color_hex"] == "#1E40AF"


@pytest.mark.django_db
class TestDeletingAColourWithStock:
    def test_it_needs_confirmation_then_goes(self, admin_client, product, blue, main):
        services.receive(product, 7, Decimal("50.00"), location=main, variant=blue.variants.get())
        url = reverse("v1:catalog:admin-product-color-detail", args=[product.pk, blue.pk])

        refused = admin_client.delete(url)
        assert refused.status_code == 409 and "7" in refused.data["detail"]
        assert ProductColor.objects.filter(pk=blue.pk).exists()

        assert admin_client.delete(url + "?force=true").status_code == 204
        # The stock stays on the books — unsellable, not erased
        assert Stock.objects.get(variant=blue.variants.get()).quantity_physical == 7
        assert (
            services.availability_by_variant([product.pk])[str(product.pk)].get(
                blue.variants.get().pk
            )
            is None
        )


@pytest.mark.django_db
class TestVariantChoices:
    def test_it_lists_the_sellable_variants_with_their_stock(
        self, admin_client, product, blue, red, main
    ):
        services.receive(product, 4, Decimal("10.00"), location=main, variant=blue.variants.get())
        color_services.update_color(red, is_active=False)

        rows = admin_client.get(
            reverse("v1:inventory:product-variants"), {"product": product.pk}
        ).data

        assert [(row["sku"], row["available"]) for row in rows] == [("CS-001-BLUE", 4)]
        assert rows[0]["color"]["hex"] == "#1E40AF"

    def test_a_customer_cannot(self, product, blue):
        client = make_customer_client("variant-choices@test.local")

        response = client.get(reverse("v1:inventory:product-variants"), {"product": product.pk})

        assert response.status_code == 403
