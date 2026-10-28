"""
The cart and colours — ownership, the "a variant is required" rule, and what a line shows.

⚠️  Until package E the API fetched the variant by id with no check it belonged to the
    product, and `add_line` accepted a product with colours and no colour: only the
    UI stood between the customer and a line the shop could not fulfil.
"""

from decimal import Decimal

import pytest
from django.apps import apps
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from cart import services
from catalog import colors as color_services
from catalog.models import Category, Product, ProductImage, ProductVariant
from conftest import png_upload
from core.errors import BusinessError
from core.models.settings import SystemSetting
from inventory import services as inventory_services

PASSWORD = "Str0ng-Test-Pass!23"
GUEST_KEY = "7b0c5b52-5d0a-4a43-9b7e-0d9a5b1f7c11"


@pytest.fixture(autouse=True)
def tax_off(db):
    SystemSetting.set("tax.enabled", False, value_type="BOOL", label_ar="ض", label_en="t")


@pytest.fixture
def location(db):
    return apps.get_model("inventory", "StockLocation").objects.create(
        code="main", name_ar="الرئيسي", name_en="Main", is_default=True
    )


@pytest.fixture
def user(db):
    user = User.objects.create_user(
        email="buyer@test.local", password=PASSWORD, account_type=AccountType.DOCTOR
    )
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def category(db):
    return Category.objects.create(name_ar="ملابس", name_en="Apparel")


def make_product(category, sku="CC-001", price="100.00"):
    from django.core.management import call_command

    from access.models import AccessPolicy

    if not AccessPolicy.objects.exists():
        call_command("seed_access_policies", verbosity=0)
    return Product.objects.create(
        sku=sku,
        name_ar="قميص",
        name_en="Top",
        category=category,
        base_price=Decimal(price),
        access_policy=AccessPolicy.objects.get(code="public"),
    )


def make_color(product, location, name="Blue", *, stock=10, price=None):
    color = color_services.create_color(
        product,
        name_ar=f"ar-{name}",
        name_en=name,
        hex="#1E40AF",
        price_override=None if price is None else Decimal(price),
    )
    if stock:
        inventory_services.receive(
            product, stock, Decimal("50.00"), location=location, variant=color.variants.get()
        )
    return color


@pytest.fixture
def product(category):
    return make_product(category)


@pytest.fixture
def blue(product, location):
    return make_color(product, location, "Blue")


@pytest.fixture
def cart(user):
    return services.get_active_cart(user=user)


@pytest.mark.django_db
class TestVariantRules:
    def test_a_colour_goes_in_the_cart(self, cart, product, blue, user):
        line = services.add_line(cart, product, 2, variant=blue.variants.get(), user=user)

        assert line.variant_id == blue.variants.get().pk

    def test_a_product_with_colours_needs_one(self, cart, product, blue, user):
        with pytest.raises(BusinessError) as failure:
            services.add_line(cart, product, 1, user=user)

        assert failure.value.code == "VALIDATION_ERROR"
        assert cart.lines.count() == 0

    def test_a_variant_of_another_product_is_refused(
        self, cart, product, blue, category, location, user
    ):
        other = make_product(category, "CC-002", "10.00")
        foreign = make_color(other, location, "Red")

        with pytest.raises(BusinessError) as failure:
            services.add_line(cart, product, 1, variant=foreign.variants.get(), user=user)

        assert failure.value.code == "VALIDATION_ERROR"

    def test_a_hidden_colour_cannot_be_added(self, cart, product, blue, user):
        color_services.update_color(blue, is_active=False)

        with pytest.raises(BusinessError) as failure:
            services.add_line(cart, product, 1, variant=blue.variants.get(), user=user)

        assert failure.value.code == "PRODUCT_UNAVAILABLE"

    def test_a_variant_flag_flipped_alone_is_caught_too(self, cart, product, blue, user):
        """The Django panel can flip the colour without its variant — `is_sellable` checks both."""
        type(blue).objects.filter(pk=blue.pk).update(is_active=False)

        with pytest.raises(BusinessError):
            services.add_line(
                cart, product, 1, variant=ProductVariant.objects.get(color=blue), user=user
            )

    def test_a_plain_product_still_needs_no_variant(self, cart, category, location, user):
        plain = make_product(category, "CC-PLAIN")
        inventory_services.receive(plain, 5, Decimal("10.00"), location=location)

        assert services.add_line(cart, plain, 1, user=user).variant_id is None

    def test_stock_is_checked_per_colour(self, cart, product, blue, location, user):
        red = make_color(product, location, "Red", stock=1)

        services.add_line(cart, product, 1, variant=red.variants.get(), user=user)
        with pytest.raises(BusinessError) as failure:
            services.add_line(cart, product, 1, variant=red.variants.get(), user=user)

        assert failure.value.code == "INSUFFICIENT_STOCK"


@pytest.mark.django_db
class TestRevalidation:
    def test_a_colour_hidden_after_it_was_added_flags_the_line(self, cart, product, blue, user):
        services.add_line(cart, product, 1, variant=blue.variants.get(), user=user)
        color_services.update_color(blue, is_active=False)

        snapshot = services.revalidate(cart, user=user)

        assert snapshot.has_issues
        assert snapshot.issues[0].code == "PRODUCT_UNAVAILABLE"
        assert not snapshot.is_checkoutable

    def test_a_deleted_colour_flags_the_line(self, cart, product, blue, user):
        services.add_line(cart, product, 1, variant=blue.variants.get(), user=user)
        color_services.delete_color(blue)

        assert services.revalidate(cart, user=user).issues[0].code == "PRODUCT_UNAVAILABLE"

    def test_an_old_line_without_a_variant_is_flagged_once_the_product_gains_colours(
        self, cart, product, location, user
    ):
        inventory_services.receive(product, 5, Decimal("10.00"), location=location)
        services.add_line(cart, product, 1, user=user)  # fine today: no colours yet
        make_color(product, location, "Blue")

        snapshot = services.revalidate(cart, user=user)

        assert snapshot.issues[0].code == "VALIDATION_ERROR"

    def test_the_colour_price_reaches_the_line(self, cart, product, location, user):
        green = make_color(product, location, "Green", price="130.00")
        services.add_line(cart, product, 2, variant=green.variants.get(), user=user)

        (_item, priced) = services.revalidate(cart, user=user).lines[0]

        assert priced.unit_price == Decimal("130.00")
        assert priced.applied_rules == ("color_price",)


@pytest.mark.django_db
class TestApi:
    def lines_url(self):
        return reverse("v1:cart:lines")

    def post(self, client, product, variant=None, quantity=1):
        body = {"product": str(product.pk), "quantity": quantity}
        if variant is not None:
            body["variant"] = str(variant.pk)
        return client.post(self.lines_url(), body, format="json")

    def test_the_payload_names_the_colour(self, user, product, blue):
        client = APIClient()
        client.force_authenticate(user=user)

        response = self.post(client, product, blue.variants.get())

        assert response.status_code == 201, response.data
        line = response.data["lines"][0]
        assert line["variant_id"] == str(blue.variants.get().pk)
        assert line["variant_sku"] == "CC-001-BLUE"
        assert line["color"] == {
            "id": str(blue.pk),
            "name_ar": "ar-Blue",
            "name_en": "Blue",
            "hex": "#1E40AF",
        }

    def test_a_foreign_variant_is_a_400(self, user, product, blue, category, location):
        foreign = make_color(make_product(category, "CC-002"), location, "Red")
        client = APIClient()
        client.force_authenticate(user=user)

        assert self.post(client, product, foreign.variants.get()).status_code == 400

    def test_a_missing_colour_is_a_400(self, user, product, blue):
        client = APIClient()
        client.force_authenticate(user=user)

        assert self.post(client, product).status_code == 400

    def test_a_guest_can_add_a_colour(self, product, blue):
        client = APIClient()

        response = client.post(
            self.lines_url(),
            {"product": str(product.pk), "variant": str(blue.variants.get().pk), "quantity": 1},
            format="json",
            HTTP_X_CART_SESSION=GUEST_KEY,
        )

        assert response.status_code == 201, response.data

    def test_the_line_image_is_the_colours_own_else_the_products(
        self, user, product, blue, location
    ):
        red = make_color(product, location, "Red")
        base = ProductImage.objects.create(
            product=product, image=png_upload("base.png"), is_primary=True
        )
        own = ProductImage.objects.create(
            product=product, color=blue, image=png_upload("blue.png"), is_primary=True
        )
        client = APIClient()
        client.force_authenticate(user=user)
        self.post(client, product, blue.variants.get())
        response = self.post(client, product, red.variants.get())

        by_color = {line["color"]["name_en"]: line["image"] for line in response.data["lines"]}

        assert by_color["Blue"].endswith(own.image.name.split("/")[-1])
        assert by_color["Red"].endswith(base.image.name.split("/")[-1]), "بلا صور: صورة المنتج"

    def test_colours_add_no_queries_per_line(self, user, product, blue, location):
        """
        ⚠️  The colour, its variant and its photo are loaded in bulk. (The pricing engine's own
            per-line lookups — price list, promotions — are a pre-existing cost, and are
            deliberately left out of the count.)
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def non_pricing(captured):
            return [q["sql"] for q in captured if "pricing_" not in q["sql"]]

        client = APIClient()
        client.force_authenticate(user=user)
        self.post(client, product, blue.variants.get())
        client.get(reverse("v1:cart:detail"))  # warm
        with CaptureQueriesContext(connection) as few:
            client.get(reverse("v1:cart:detail"))

        for name in ("Red", "Green", "Black", "Pink"):
            color = make_color(product, location, name)
            ProductImage.objects.create(
                product=product, color=color, image=png_upload(f"{name}.png"), is_primary=True
            )
            self.post(client, product, color.variants.get())
        with CaptureQueriesContext(connection) as many:
            response = client.get(reverse("v1:cart:detail"))

        assert len(response.data["lines"]) == 5
        from collections import Counter

        def shapes(captured):
            return Counter(sql.split(" FROM ")[1].split()[0] for sql in non_pricing(captured))

        grown = {
            table: count - shapes(few.captured_queries).get(table, 0)
            for table, count in shapes(many.captured_queries).items()
            if count != shapes(few.captured_queries).get(table, 0)
        }
        # The colour, its variant and its photo come in bulk: none of those tables may be
        # queried once per line.
        colour_tables = {
            '"catalog_productcolor"',
            '"catalog_productimage"',
            '"catalog_productvariant"',
        }
        assert not (set(grown) & colour_tables), grown
