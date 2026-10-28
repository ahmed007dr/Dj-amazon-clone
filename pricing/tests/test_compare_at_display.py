"""
"Price before discount" against **the price this viewer pays**.

⚠️  The old price is shown only while it is strictly above the viewer's price, so the same
    product reads differently to a guest, a student on the student list and a customer
    whose list happens to charge more than the old figure.

    Lives in `pricing/tests` because it joins the catalogue's field with the engine's
    answer, and `catalog` may not import `pricing`.
"""

from decimal import Decimal

import pytest
from django.apps import apps
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from access.models import AccessPolicy
from accounts.models import AccountType, User
from catalog import colors as color_services
from catalog.models import Category, Product, ProductVariant
from pricing.models import PriceList, PriceRule

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


@pytest.fixture
def location(db):
    return apps.get_model("inventory", "StockLocation").objects.create(
        code="main", name_ar="الرئيسي", name_en="Main", is_default=True
    )


@pytest.fixture
def product(db, location):
    from django.core.management import call_command

    call_command("seed_access_policies", verbosity=0)
    category = Category.objects.create(name_ar="مستلزمات", name_en="Supplies")
    item = Product.objects.create(
        sku="CMP-P",
        name_ar="سماعة",
        name_en="Stethoscope",
        category=category,
        base_price=Decimal("100.00"),
        compare_at_price=Decimal("130.00"),
        access_policy=AccessPolicy.objects.get(code="public"),
    )
    apps.get_model("inventory", "Stock").objects.create(
        product=item, location=location, quantity_physical=10
    )
    return item


@pytest.fixture
def student_list(db):
    return PriceList.objects.create(
        code="students",
        name_ar="طلاب",
        name_en="Students",
        account_types=[AccountType.STUDENT],
        priority=10,
    )


@pytest.fixture
def student_client(db):
    student = User.objects.create_user(
        email="cmp-student@test.local", password=PASSWORD, account_type=AccountType.STUDENT
    )
    student.is_active = True
    student.save()
    client = APIClient()
    client.force_authenticate(user=student)
    return client


def list_row(client, product):
    response = client.get(reverse("v1:catalog:products"))
    assert response.status_code == 200
    return next(row for row in response.data["results"] if row["sku"] == product.sku)


def detail(client, product):
    return client.get(reverse("v1:catalog:product-detail", args=[product.slug])).data


class TestStudentPrice:
    def test_the_student_sees_the_student_price_and_a_bigger_saving(
        self, product, student_list, student_client
    ):
        PriceRule.objects.create(
            price_list=student_list, product=product, unit_price=Decimal("65.00")
        )

        guest = list_row(APIClient(), product)
        student = list_row(student_client, product)

        assert (guest["price"], guest["compare_at_price"], guest["discount_percent"]) == (
            "100.00",
            "130.00",
            23,
        )
        assert (student["price"], student["compare_at_price"], student["discount_percent"]) == (
            "65.00",
            "130.00",
            50,
        )
        # the reference price is still there, unchanged
        assert student["base_price"] == "100.00"

    def test_a_list_that_charges_more_than_the_old_price_shows_nothing(
        self, product, student_list, student_client
    ):
        """⚠️  Striking 130 beside 140 would be a lie, so the server sends `null`."""
        PriceRule.objects.create(
            price_list=student_list, product=product, unit_price=Decimal("140.00")
        )

        row = list_row(student_client, product)

        assert row["price"] == "140.00"
        assert row["compare_at_price"] is None
        assert row["discount_percent"] is None
        assert detail(student_client, product)["compare_at_price"] is None

    def test_the_detail_agrees_with_the_list(self, product, student_list, student_client):
        PriceRule.objects.create(
            price_list=student_list, product=product, unit_price=Decimal("65.00")
        )

        data = detail(student_client, product)

        assert (data["price"], data["compare_at_price"], data["discount_percent"]) == (
            "65.00",
            "130.00",
            50,
        )

    def test_a_price_list_rule_is_a_fixed_number_of_queries(
        self, product, student_list, student_client, location
    ):
        PriceRule.objects.create(
            price_list=student_list, product=product, unit_price=Decimal("65.00")
        )
        # A throw-away call first: the very first request warms process-level caches
        student_client.get(reverse("v1:catalog:products"))
        with CaptureQueriesContext(connection) as small:
            student_client.get(reverse("v1:catalog:products"))

        for i in range(10):
            extra = Product.objects.create(
                sku=f"CMP-X{i}",
                name_ar=f"س{i}",
                name_en=f"X{i}",
                category=product.category,
                base_price=Decimal("50.00"),
                access_policy=product.access_policy,
            )
            apps.get_model("inventory", "Stock").objects.create(
                product=extra, location=location, quantity_physical=5
            )
            PriceRule.objects.create(
                price_list=student_list, product=extra, unit_price=Decimal("40.00")
            )
        with CaptureQueriesContext(connection) as large:
            response = student_client.get(reverse("v1:catalog:products"))

        assert len(response.data["results"]) == 11
        assert len(large) == len(small)


class TestColourPrice:
    def test_a_student_price_beats_the_colour_price_and_the_old_price_is_judged_against_it(
        self, product, student_list, student_client
    ):
        green = color_services.create_color(
            product,
            name_ar="أخضر",
            name_en="Green",
            hex="#15803D",
            price_override=Decimal("90.00"),
            compare_at_price=Decimal("120.00"),
        )
        PriceRule.objects.create(
            price_list=student_list, product=product, unit_price=Decimal("60.00")
        )

        guest = next(c for c in detail(APIClient(), product)["colors"] if c["id"] == str(green.pk))
        student = next(
            c for c in detail(student_client, product)["colors"] if c["id"] == str(green.pk)
        )

        assert (guest["price"], guest["compare_at_price"], guest["discount_percent"]) == (
            "90.00",
            "120.00",
            25,
        )
        assert (student["price"], student["compare_at_price"], student["discount_percent"]) == (
            "60.00",
            "120.00",
            50,
        )

    def test_the_variant_row_of_a_colour_carries_the_colour_price(self, product):
        green = color_services.create_color(
            product,
            name_ar="أخضر",
            name_en="Green",
            hex="#15803D",
            price_override=Decimal("90.00"),
            compare_at_price=Decimal("120.00"),
        )

        rows = detail(APIClient(), product)["variants"]
        row = next(r for r in rows if r["id"] == str(green.variants.get().pk))

        assert (row["price"], row["compare_at_price"], row["discount_percent"]) == (
            "90.00",
            "120.00",
            25,
        )

    def test_a_plain_size_variant_follows_the_price_list_too(
        self, product, student_list, student_client
    ):
        xl = ProductVariant.objects.create(
            product=product,
            sku="CMP-P-XL",
            name_ar="كبير",
            name_en="XL",
            price_adjustment=Decimal("10.00"),
        )
        PriceRule.objects.create(
            price_list=student_list, product=product, unit_price=Decimal("65.00")
        )

        row = next(r for r in detail(student_client, product)["variants"] if r["id"] == str(xl.pk))

        # 65 + 10 now, 130 + 10 before
        assert (row["price"], row["compare_at_price"]) == ("75.00", "140.00")
        assert row["discount_percent"] == 46
