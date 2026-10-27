"""
Product colours — the admin API.

⚠️  A colour is a swatch + a gallery + an optional price **in front of a variant**.
    The checks that matter most here are the ones that keep that pairing honest: a
    colour is never created without its variant, deactivating one deactivates the
    other, and deleting one keeps the variant (orders point at it) but takes it off sale.
"""

from decimal import Decimal

import pytest
from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from catalog.models import Product, ProductColor, ProductImage, ProductVariant
from catalog.tests.color_support import (
    add_color,
    make_admin_client,
    make_customer_client,
    make_product,
)
from conftest import png_upload
from core.models.audit import AuditAction, AuditLog
from inventory import services as inventory_services
from inventory.models import StockLocation


@pytest.fixture
def product(db):
    return make_product()


@pytest.fixture
def admin_client(db):
    return make_admin_client()


def colors_url(product):
    return reverse("v1:catalog:admin-product-colors", args=[product.pk])


def color_url(product, color):
    return reverse("v1:catalog:admin-product-color-detail", args=[product.pk, color.pk])


def create(client, product, **overrides):
    body = {"name_ar": "أزرق", "name_en": "Blue", "hex": "#1e40af", **overrides}
    return client.post(colors_url(product), body, format="json")


def timeline(product):
    return AuditLog.objects.filter(
        content_type=ContentType.objects.get_for_model(Product), object_id=str(product.pk)
    )


# ═══════════════════════════════════════════════════════════
#  Creating
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCreate:
    def test_a_colour_is_created_with_its_variant(self, admin_client, product):
        response = create(admin_client, product)

        assert response.status_code == 201, response.data
        color = ProductColor.objects.get(product=product)
        variant = color.variants.get()
        assert variant.product_id == product.pk
        assert variant.sku == "CLR-001-BLUE"
        assert (variant.name_ar, variant.name_en) == ("أزرق", "Blue")
        assert variant.attributes == {"color": "Blue"}
        assert variant.price_adjustment == Decimal("0.00")
        assert variant.is_active is True

        assert response.data["variant_id"] == str(variant.pk)
        assert response.data["image_count"] == 0
        assert response.data["primary_image"] is None

    def test_the_hex_is_stored_upper_case(self, admin_client, product):
        response = create(admin_client, product, hex="#1e40af")

        assert response.data["hex"] == "#1E40AF"

    def test_without_a_price_the_colour_uses_the_products(self, admin_client, product):
        response = create(admin_client, product)

        assert response.data["price_override"] is None
        assert ProductColor.objects.get().price_override is None

    def test_its_own_price_is_kept(self, admin_client, product):
        response = create(admin_client, product, price_override="120.50")

        assert response.data["price_override"] == "120.50"

    def test_zero_is_a_price_not_an_absence(self, admin_client, product):
        response = create(admin_client, product, price_override="0.00")

        assert response.status_code == 201
        assert ProductColor.objects.get().price_override == Decimal("0.00")

    def test_colours_are_ordered_as_they_are_added(self, admin_client, product):
        create(admin_client, product)
        create(admin_client, product, name_ar="أخضر", name_en="Green")

        orders = list(ProductColor.objects.filter(product=product).values_list("display_order", flat=True))
        assert orders == sorted(orders)
        assert len(set(orders)) == 2

    def test_it_is_recorded_on_the_products_timeline(self, admin_client, product):
        create(admin_client, product, price_override="120.00")

        entry = timeline(product).get(action=AuditAction.CREATE)
        assert entry.object_repr == f"لون منتج {product.sku}"
        assert entry.changes["color"] == "Blue"
        assert entry.changes["price_override"] == "120.00"

    def test_the_product_records_who_touched_it(self, admin_client, product):
        create(admin_client, product)

        product.refresh_from_db()
        assert product.updated_by is not None

    def test_a_product_with_size_variants_keeps_them(self, admin_client, product):
        """A colour never rewrites a variant it did not create."""
        size = ProductVariant.objects.create(
            product=product, sku="CLR-001-M", name_ar="وسط", name_en="Medium"
        )

        create(admin_client, product)

        size.refresh_from_db()
        assert size.color_id is None
        assert product.variants.count() == 2


@pytest.mark.django_db
class TestValidation:
    @pytest.mark.parametrize("bad_hex", ["#fff", "blue", "1E40AF", "#GGGGGG", "#1E40AF0", ""])
    def test_only_rrggbb_is_accepted(self, admin_client, product, bad_hex):
        response = create(admin_client, product, hex=bad_hex)

        assert response.status_code == 400
        assert not ProductColor.objects.exists()

    def test_a_negative_price_is_rejected(self, admin_client, product):
        assert create(admin_client, product, price_override="-1").status_code == 400

    def test_both_names_are_required(self, admin_client, product):
        for body in ({"name_en": "Blue", "hex": "#111111"}, {"name_ar": "أزرق", "hex": "#111111"}):
            assert admin_client.post(colors_url(product), body, format="json").status_code == 400

    def test_a_name_is_unique_within_a_product(self, admin_client, product):
        create(admin_client, product)

        same_ar = create(admin_client, product, name_en="Navy")
        same_en = create(admin_client, product, name_ar="كحلي")

        assert same_ar.status_code == 400 and "name_ar" in same_ar.data["fields"]
        assert same_en.status_code == 400 and "name_en" in same_en.data["fields"]

    def test_another_product_may_reuse_the_name(self, admin_client, product):
        create(admin_client, product)
        other = make_product("CLR-002")

        assert create(admin_client, other).status_code == 201

    def test_an_unknown_product_is_a_404(self, admin_client, db):
        import uuid

        url = reverse("v1:catalog:admin-product-colors", args=[uuid.uuid4()])
        response = admin_client.post(url, {"name_ar": "أ", "name_en": "A", "hex": "#111111"}, format="json")

        assert response.status_code == 404

    def test_a_deleted_product_cannot_be_given_colours(self, admin_client, product):
        product.delete()

        assert create(admin_client, product).status_code == 404


@pytest.mark.django_db
class TestPermissions:
    def test_anonymous_is_refused(self, product):
        from rest_framework.test import APIClient

        assert APIClient().get(colors_url(product)).status_code in (401, 403)

    def test_a_customer_cannot_manage_colours(self, product):
        client = make_customer_client()

        assert client.get(colors_url(product)).status_code == 403
        assert create(client, product).status_code == 403
        assert not ProductColor.objects.exists()


# ═══════════════════════════════════════════════════════════
#  Reading
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestList:
    def test_lists_a_products_colours_only(self, admin_client, product):
        add_color(product)
        add_color(make_product("CLR-002"), "Green")

        response = admin_client.get(colors_url(product))

        assert response.status_code == 200
        assert [row["name_en"] for row in response.data] == ["Blue"]

    def test_reports_image_count_and_the_primary_image(self, admin_client, product):
        color = add_color(product)
        ProductImage.objects.create(
            product=product, color=color, image=png_upload("a.png"), is_primary=True
        )
        ProductImage.objects.create(product=product, color=color, image=png_upload("b.png"))

        row = admin_client.get(colors_url(product)).data[0]

        assert row["image_count"] == 2
        assert row["primary_image"]["is_primary"] is True

    def test_a_base_image_is_not_counted_against_a_colour(self, admin_client, product):
        add_color(product)
        ProductImage.objects.create(product=product, image=png_upload("a.png"), is_primary=True)

        assert admin_client.get(colors_url(product)).data[0]["image_count"] == 0

    def test_the_query_count_does_not_grow_with_the_colours(self, admin_client, product):
        add_color(product, "Blue")
        admin_client.get(colors_url(product))  # warm the permission / content-type caches
        with CaptureQueriesContext(connection) as few:
            admin_client.get(colors_url(product))

        for name in ("Green", "Red", "Black"):
            color = add_color(product, name)
            ProductImage.objects.create(
                product=product, color=color, image=png_upload(f"{name}.png"), is_primary=True
            )
        with CaptureQueriesContext(connection) as many:
            admin_client.get(colors_url(product))

        assert len(many) == len(few)

    def test_detail_of_another_products_colour_is_a_404(self, admin_client, product):
        foreign = add_color(make_product("CLR-002"))

        assert admin_client.get(color_url(product, foreign)).status_code == 404


# ═══════════════════════════════════════════════════════════
#  Changing
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestUpdate:
    def test_renaming_renames_the_untouched_variant(self, admin_client, product):
        color = add_color(product)

        response = admin_client.patch(
            color_url(product, color), {"name_ar": "أزرق ملكي", "name_en": "Royal blue"}, format="json"
        )

        assert response.status_code == 200, response.data
        variant = color.variants.get()
        assert (variant.name_ar, variant.name_en) == ("أزرق ملكي", "Royal blue")
        assert variant.attributes == {"color": "Royal blue"}

    def test_a_variant_renamed_by_hand_keeps_its_name(self, admin_client, product):
        color = add_color(product)
        variant = color.variants.get()
        variant.name_en = "Blue — Large"
        variant.save()

        admin_client.patch(color_url(product, color), {"name_en": "Royal blue"}, format="json")

        variant.refresh_from_db()
        assert variant.name_en == "Blue — Large"

    def test_a_price_move_is_a_price_change_entry(self, admin_client, product):
        color = add_color(product)

        admin_client.patch(color_url(product, color), {"price_override": "150.00"}, format="json")

        entry = timeline(product).get(action=AuditAction.PRICE_CHANGE)
        assert entry.changes["price_override"] == {"old": None, "new": "150.00"}

    def test_a_null_price_clears_the_override(self, admin_client, product):
        color = add_color(product, price_override="150.00")

        response = admin_client.patch(color_url(product, color), {"price_override": None}, format="json")

        assert response.status_code == 200
        color.refresh_from_db()
        assert color.price_override is None

    def test_omitting_the_price_leaves_it_alone(self, admin_client, product):
        color = add_color(product, price_override="150.00")

        admin_client.patch(color_url(product, color), {"hex": "#000000"}, format="json")

        color.refresh_from_db()
        assert color.price_override == Decimal("150.00")
        assert color.hex == "#000000"

    def test_deactivating_deactivates_the_variants_and_back(self, admin_client, product):
        color = add_color(product)

        admin_client.patch(color_url(product, color), {"is_active": False}, format="json")
        assert color.variants.get().is_active is False

        admin_client.patch(color_url(product, color), {"is_active": True}, format="json")
        assert color.variants.get().is_active is True

    def test_an_unchanged_save_writes_no_audit_entry(self, admin_client, product):
        color = add_color(product)
        before = timeline(product).count()

        admin_client.patch(color_url(product, color), {"hex": color.hex}, format="json")

        assert timeline(product).count() == before

    def test_renaming_into_a_taken_name_is_refused(self, admin_client, product):
        add_color(product, "Blue")
        green = add_color(product, "Green")

        response = admin_client.patch(color_url(product, green), {"name_en": "Blue"}, format="json")

        assert response.status_code == 400


@pytest.mark.django_db
class TestDelete:
    def test_it_is_soft_and_the_variant_is_kept_but_off_sale(self, admin_client, product):
        color = add_color(product)
        variant = color.variants.get()

        response = admin_client.delete(color_url(product, color))

        assert response.status_code == 204
        assert not ProductColor.objects.filter(pk=color.pk).exists()
        assert ProductColor.all_objects.get(pk=color.pk).deleted_at is not None
        variant.refresh_from_db()
        assert variant.is_active is False, "الطلبات القديمة تشير إليها — تبقى لكن خارج البيع"

    def test_its_images_go_with_it(self, admin_client, product):
        color = add_color(product)
        ProductImage.objects.create(
            product=product, color=color, image=png_upload("a.png"), is_primary=True
        )
        ProductImage.objects.create(product=product, image=png_upload("base.png"), is_primary=True)

        admin_client.delete(color_url(product, color))

        assert not ProductImage.objects.filter(color=color).exists()
        assert ProductImage.objects.filter(product=product, color__isnull=True).count() == 1

    def test_the_name_can_be_reused_and_the_sku_stays_unique(self, admin_client, product):
        """⚠️  `ProductVariant.sku` is globally unique — the dead row still holds the first one."""
        color = add_color(product)
        admin_client.delete(color_url(product, color))

        response = create(admin_client, product)

        assert response.status_code == 201, response.data
        skus = set(ProductVariant.all_objects.filter(product=product).values_list("sku", flat=True))
        assert skus == {"CLR-001-BLUE", "CLR-001-BLUE-2"}

    def test_a_colour_with_stock_needs_confirmation(self, admin_client, product):
        location = StockLocation.objects.create(
            code="main", name_ar="الرئيسي", name_en="Main", is_default=True
        )
        color = add_color(product)
        inventory_services.receive(
            product, 7, Decimal("50.00"), location=location, variant=color.variants.get()
        )

        refused = admin_client.delete(color_url(product, color))
        assert refused.status_code == 409
        assert "7" in refused.data["detail"]
        assert ProductColor.objects.filter(pk=color.pk).exists()

        confirmed = admin_client.delete(color_url(product, color) + "?force=true")
        assert confirmed.status_code == 204

    def test_it_is_audited(self, admin_client, product):
        color = add_color(product)

        admin_client.delete(color_url(product, color))

        entry = timeline(product).get(action=AuditAction.DELETE)
        assert entry.changes["color"] == "Blue"
        assert entry.changes["soft"] is True


@pytest.mark.django_db
class TestReorder:
    def test_the_given_order_becomes_the_display_order(self, admin_client, product):
        blue, green, red = (add_color(product, name) for name in ("Blue", "Green", "Red"))

        response = admin_client.post(
            reverse("v1:catalog:admin-product-colors-reorder", args=[product.pk]),
            {"order": [str(red.pk), str(blue.pk), str(green.pk)]},
            format="json",
        )

        assert response.status_code == 200
        assert [row["name_en"] for row in response.data] == ["Red", "Blue", "Green"]
        # The auto-variant follows its colour, so "the colour's first variant" stays stable
        assert red.variants.get().display_order < blue.variants.get().display_order

    def test_another_products_colour_id_is_refused_before_anything_changes(
        self, admin_client, product
    ):
        blue = add_color(product, "Blue")
        green = add_color(product, "Green")
        foreign = add_color(make_product("CLR-002"), "Red")
        original = [blue.display_order, green.display_order]

        response = admin_client.post(
            reverse("v1:catalog:admin-product-colors-reorder", args=[product.pk]),
            {"order": [str(green.pk), str(foreign.pk), str(blue.pk)]},
            format="json",
        )

        assert response.status_code == 400
        blue.refresh_from_db()
        green.refresh_from_db()
        assert [blue.display_order, green.display_order] == original

    def test_an_empty_order_is_refused(self, admin_client, product):
        response = admin_client.post(
            reverse("v1:catalog:admin-product-colors-reorder", args=[product.pk]),
            {"order": []},
            format="json",
        )

        assert response.status_code == 400
