"""
The product page's colours — what the storefront receives.

Lives beside the cart tests because the payload joins three layers the catalogue
itself may not import: prices (`pricing`), availability (`inventory`) and the
catalogue's own colours. `cart` sits above all three, like the checkout that
consumes the result.
"""

from decimal import Decimal

import pytest
from django.apps import apps
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from catalog import colors as color_services
from catalog.models import Category, Product, ProductColor, ProductImage
from conftest import png_upload
from core.models.settings import SystemSetting
from inventory import services as inventory_services

PASSWORD = "Str0ng-Test-Pass!23"


@pytest.fixture(autouse=True)
def tax_off(db):
    SystemSetting.set("tax.enabled", False, value_type="BOOL", label_ar="ض", label_en="t")


@pytest.fixture
def location(db):
    return apps.get_model("inventory", "StockLocation").objects.create(
        code="main", name_ar="الرئيسي", name_en="Main", is_default=True
    )


@pytest.fixture
def product(db, location):
    from django.core.management import call_command

    from access.models import AccessPolicy

    call_command("seed_access_policies", verbosity=0)
    category = Category.objects.create(name_ar="ملابس", name_en="Apparel")
    return Product.objects.create(
        sku="PG-001",
        name_ar="قميص",
        name_en="Top",
        category=category,
        base_price=Decimal("100.00"),
        access_policy=AccessPolicy.objects.get(code="public"),
    )


def add_color(product, location, name_en, *, stock=20, price=None, hex_="#1E40AF"):
    color = color_services.create_color(
        product,
        name_ar=f"ar-{name_en}",
        name_en=name_en,
        hex=hex_,
        price_override=None if price is None else Decimal(price),
    )
    if stock:
        inventory_services.receive(
            product, stock, Decimal("50.00"), location=location, variant=color.variants.get()
        )
    return color


def detail(product, client=None):
    client = client or APIClient()
    return client.get(reverse("v1:catalog:product-detail", args=[product.slug]))


def color_row(response, name_en):
    return next(row for row in response.data["colors"] if row["name_en"] == name_en)


@pytest.mark.django_db
class TestPayloadShape:
    def test_a_product_without_colours_has_an_empty_list(self, product, location):
        inventory_services.receive(product, 5, Decimal("10.00"), location=location)

        response = detail(product)

        assert response.status_code == 200
        assert response.data["colors"] == []

    def test_each_colour_carries_what_the_swatch_needs(self, product, location):
        blue = add_color(product, location, "Blue")

        row = color_row(detail(product), "Blue")

        assert row["id"] == str(blue.pk)
        assert row["hex"] == "#1E40AF"
        assert row["variant_id"] == str(blue.variants.get().pk)
        assert row["is_available"] is True
        assert row["images"] == []

    def test_colours_come_in_display_order(self, product, location):
        for name in ("Blue", "Green", "Red"):
            add_color(product, location, name)

        response = detail(product)

        assert [row["name_en"] for row in response.data["colors"]] == ["Blue", "Green", "Red"]

    def test_a_hidden_colour_is_not_offered(self, product, location):
        add_color(product, location, "Blue")
        hidden = add_color(product, location, "Green")
        deleted = add_color(product, location, "Red")
        color_services.update_color(hidden, is_active=False)
        color_services.delete_color(deleted)

        response = detail(product)

        assert [row["name_en"] for row in response.data["colors"]] == ["Blue"]
        # …and neither is their variant in the flat `variants` list
        assert len(response.data["variants"]) == 1

    def test_the_exact_stock_figure_never_reaches_the_public(self, product, location):
        add_color(product, location, "Blue", stock=847)

        row = color_row(detail(product), "Blue")

        assert "quantity" not in row
        assert row["available"] is None, "فوق العتبة: «متوفر» فقط"

    def test_a_low_colour_shows_its_number(self, product, location):
        add_color(product, location, "Blue", stock=3)

        row = color_row(detail(product), "Blue")

        assert row["is_low"] is True and row["available"] == 3


@pytest.mark.django_db
class TestImages:
    def test_a_colours_images_are_its_own_and_the_base_gallery_is_separate(self, product, location):
        blue = add_color(product, location, "Blue")
        ProductImage.objects.create(product=product, image=png_upload("base.png"), is_primary=True)
        own = ProductImage.objects.create(
            product=product, color=blue, image=png_upload("blue.png"), is_primary=True
        )

        response = detail(product)

        assert len(response.data["images"]) == 1, "المعرض العام لا يحمل صور الألوان"
        assert response.data["images"][0]["color"] is None
        assert [str(i["id"]) for i in color_row(response, "Blue")["images"]] == [str(own.pk)]

    def test_a_colour_without_images_has_an_empty_list_for_the_page_to_fall_back_on(
        self, product, location
    ):
        add_color(product, location, "Blue")
        ProductImage.objects.create(product=product, image=png_upload("base.png"), is_primary=True)

        response = detail(product)

        assert color_row(response, "Blue")["images"] == []
        assert len(response.data["images"]) == 1

    def test_the_list_thumbnail_is_always_a_base_image(self, product, location):
        """
        ⚠️  Every colour has a primary of its own; without the `color IS NULL` filter in
            `primary_image_prefetch` the card would show a random colour's photo.
        """
        blue = add_color(product, location, "Blue")
        base = ProductImage.objects.create(
            product=product, image=png_upload("base.png"), is_primary=True
        )
        ProductImage.objects.create(
            product=product, color=blue, image=png_upload("blue.png"), is_primary=True
        )

        response = APIClient().get(reverse("v1:catalog:products"))

        card = next(row for row in response.data["results"] if row["sku"] == "PG-001")
        assert str(card["primary_image"]["id"]) == str(base.pk)

    def test_a_product_with_only_colour_images_has_no_list_thumbnail(self, product, location):
        blue = add_color(product, location, "Blue")
        ProductImage.objects.create(
            product=product, color=blue, image=png_upload("blue.png"), is_primary=True
        )

        response = APIClient().get(reverse("v1:catalog:products"))

        card = next(row for row in response.data["results"] if row["sku"] == "PG-001")
        assert card["primary_image"] is None


@pytest.mark.django_db
class TestPrices:
    def test_a_colour_without_a_price_shows_the_products(self, product, location):
        add_color(product, location, "Blue")

        assert color_row(detail(product), "Blue")["price"] == "100.00"
        assert color_row(detail(product), "Blue")["price_override"] is None

    def test_a_colour_with_its_own_price_shows_it(self, product, location):
        add_color(product, location, "Green", price="120.00")

        row = color_row(detail(product), "Green")

        assert row["price"] == "120.00" and row["price_override"] == "120.00"

    def test_a_student_list_beats_the_colour_price(self, product, location):
        """⚠️  Owner's precedence: price list → colour → product."""
        add_color(product, location, "Blue")
        add_color(product, location, "Green", price="120.00")
        # By reference: `cart` may not import another domain's models (import-linter)
        price_list_model = apps.get_model("pricing", "PriceList")
        price_rule_model = apps.get_model("pricing", "PriceRule")
        student_list = price_list_model.objects.create(
            code="student",
            name_ar="طلاب",
            name_en="Student",
            account_types=[AccountType.STUDENT],
            priority=10,
        )
        price_rule_model.objects.create(
            price_list=student_list, product=product, unit_price=Decimal("75.00")
        )
        student = User.objects.create_user(
            email="stu@test.local", password=PASSWORD, account_type=AccountType.STUDENT
        )
        student.is_active = True
        student.save()
        client = APIClient()
        client.force_authenticate(user=student)

        as_student = detail(product, client)
        as_guest = detail(product)

        assert color_row(as_student, "Blue")["price"] == "75.00"
        assert color_row(as_student, "Green")["price"] == "75.00"
        assert color_row(as_guest, "Blue")["price"] == "100.00"
        assert color_row(as_guest, "Green")["price"] == "120.00"

    def test_the_swatch_price_is_what_the_cart_charges(self, product, location):
        from cart import services as cart_services

        add_color(product, location, "Green", price="120.00")
        row = color_row(detail(product), "Green")
        user = User.objects.create_user(
            email="b@test.local", password=PASSWORD, account_type=AccountType.DOCTOR
        )
        user.is_active = True
        user.save()
        cart = cart_services.get_active_cart(user=user)
        variant = ProductColor.objects.get(product=product, name_en="Green").variants.get()
        cart_services.add_line(cart, product, 1, variant=variant, user=user)

        snapshot = cart_services.revalidate(cart, user=user)

        assert str(snapshot.lines[0][1].unit_price) == row["price"]


@pytest.mark.django_db
class TestAvailability:
    def test_a_sold_out_colour_is_flagged_while_the_others_are_not(self, product, location):
        add_color(product, location, "Blue")
        add_color(product, location, "Red", stock=0)

        response = detail(product)

        assert color_row(response, "Blue")["is_available"] is True
        assert color_row(response, "Red")["is_available"] is False

    def test_reserved_and_damaged_units_do_not_count(self, product, location):
        blue = add_color(product, location, "Blue", stock=4)
        variant = blue.variants.get()
        inventory_services.reserve(product, 3, location=location, variant=variant)
        inventory_services.mark_damaged(product, 1, location=location, variant=variant, reason="x")

        row = color_row(detail(product), "Blue")

        assert row["is_available"] is False

    def test_a_product_whose_stock_is_unassigned_is_not_listed_nor_available(
        self, product, location
    ):
        """
        ⚠️  Units sitting on "no variant" are unsellable once the product has colours,
            so they must not keep the product on the shelf.
        """
        inventory_services.receive(product, 10, Decimal("10.00"), location=location)
        color_services.create_color(product, name_ar="أزرق", name_en="Blue", hex="#1E40AF")

        listed = APIClient().get(reverse("v1:catalog:products"))

        assert not any(row["sku"] == "PG-001" for row in listed.data["results"])
        assert color_row(detail(product), "Blue")["is_available"] is False


@pytest.mark.django_db
class TestQueryCount:
    def test_the_page_costs_the_same_for_one_colour_or_many(self, product, location):
        first = add_color(product, location, "Blue")
        ProductImage.objects.create(
            product=product, color=first, image=png_upload("b.png"), is_primary=True
        )
        detail(product)  # warm caches
        with CaptureQueriesContext(connection) as few:
            detail(product)

        for name in ("Green", "Red", "Black", "Pink", "Gray"):
            color = add_color(product, location, name, price="110.00")
            ProductImage.objects.create(
                product=product, color=color, image=png_upload(f"{name}.png"), is_primary=True
            )
        with CaptureQueriesContext(connection) as many:
            response = detail(product)

        assert len(response.data["colors"]) == 6
        extra = [q["sql"][:230] for q in many.captured_queries[len(few) :]]
        assert len(many) == len(few), "N+1: كل لون يضيف استعلامًا\n" + "\n".join(extra)


@pytest.mark.django_db
class TestSearchAndBarcode:
    def test_the_storefront_search_finds_a_product_by_a_variants_sku(self, product, location):
        blue = add_color(product, location, "Blue")

        response = APIClient().get(reverse("v1:catalog:products"), {"search": "PG-001-BLUE"})

        assert [row["sku"] for row in response.data["results"]] == ["PG-001"]
        assert blue.variants.get().sku == "PG-001-BLUE"

    def test_a_partial_variant_sku_does_not_match(self, product, location):
        add_color(product, location, "Blue")

        response = APIClient().get(reverse("v1:catalog:products"), {"search": "BLUE"})

        assert response.data["results"] == []

    def test_search_by_a_variants_barcode(self, product, location):
        blue = add_color(product, location, "Blue")
        variant = blue.variants.get()
        variant.barcode = "6220001112223"
        variant.save()

        response = APIClient().get(reverse("v1:catalog:products"), {"search": "6220001112223"})

        assert [row["sku"] for row in response.data["results"]] == ["PG-001"]

    def test_a_product_matching_two_variants_is_listed_once(self, product, location):
        for name in ("Blue", "Green"):
            color = add_color(product, location, name)
            variant = color.variants.get()
            variant.barcode = "SAME-CODE"
            variant.save()

        response = APIClient().get(reverse("v1:catalog:products"), {"search": "SAME-CODE"})

        assert len(response.data["results"]) == 1

    def test_the_barcode_endpoint_resolves_a_variant_barcode_and_names_the_colour(
        self, product, location
    ):
        blue = add_color(product, location, "Blue")
        variant = blue.variants.get()
        variant.barcode = "6220001112223"
        variant.save()

        response = APIClient().get(reverse("v1:catalog:product-by-barcode", args=["6220001112223"]))

        assert response.status_code == 200
        assert response.data["sku"] == "PG-001"
        assert response.data["matched_variant"] == str(variant.pk)

    def test_the_barcode_endpoint_still_resolves_the_products_own(self, product, location):
        product.barcode = "1112223334445"
        product.save()
        add_color(product, location, "Blue")

        response = APIClient().get(reverse("v1:catalog:product-by-barcode", args=["1112223334445"]))

        assert response.status_code == 200 and response.data["matched_variant"] is None

    def test_an_unknown_barcode_is_a_404(self, product, location):
        response = APIClient().get(reverse("v1:catalog:product-by-barcode", args=["000"]))

        assert response.status_code == 404

    def test_the_admin_search_finds_a_retired_variant(self, product, location):
        from catalog.tests.color_support import make_admin_client

        blue = add_color(product, location, "Blue")
        color_services.delete_color(blue)

        response = make_admin_client("srch@test.local").get(
            reverse("v1:catalog:admin-products"), {"search": "PG-001-BLUE"}
        )

        assert [row["sku"] for row in response.data["results"]] == ["PG-001"]
