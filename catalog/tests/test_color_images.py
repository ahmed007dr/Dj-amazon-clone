"""
Images scoped by colour.

⚠️  A product now has several galleries: the **base** one and one per colour. The
    rules that used to be per product — the cap of eight, "the first image becomes
    the primary", "deleting the primary promotes the next", the unique-primary
    constraint — are now per gallery. Each test below pins one of them, because
    each used to be a product-wide rule that a colour's first upload would break.
"""

import uuid

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse

from catalog.image_api import MAX_IMAGES_PER_PRODUCT
from catalog.models import ProductImage
from catalog.tests.color_support import (
    add_color,
    make_admin_client,
    make_customer_client,
    make_product,
)
from conftest import png_upload


@pytest.fixture
def product(db):
    return make_product()


@pytest.fixture
def blue(product):
    return add_color(product, "Blue")


@pytest.fixture
def green(product):
    return add_color(product, "Green", hex="#15803D")


@pytest.fixture
def admin_client(db):
    return make_admin_client()


def images_url(product):
    return reverse("v1:catalog:admin-product-images", args=[product.pk])


def upload(client, product, color=None, name="photo.png"):
    body = {"image": png_upload(name)}
    if color is not None:
        body["color"] = str(color.pk)
    return client.post(images_url(product), body, format="multipart")


def primary_ids(product, color=None):
    queryset = ProductImage.objects.filter(product=product, is_primary=True)
    queryset = (
        queryset.filter(color=color) if color is not None else queryset.filter(color__isnull=True)
    )
    return list(queryset.values_list("pk", flat=True))


@pytest.mark.django_db
class TestUploadIntoAScope:
    def test_a_colours_first_image_is_its_own_primary(self, admin_client, product, blue):
        base = upload(admin_client, product)
        own = upload(admin_client, product, blue)

        assert base.status_code == 201 and own.status_code == 201
        assert base.data["is_primary"] is True and base.data["color"] is None
        assert own.data["is_primary"] is True, "أول صورة للون هي رئيسيته حتى لو للمنتج صور"
        assert str(own.data["color"]) == str(blue.pk)

    def test_the_second_image_of_a_scope_is_not_primary(self, admin_client, product, blue):
        upload(admin_client, product, blue, "a.png")
        second = upload(admin_client, product, blue, "b.png")

        assert second.data["is_primary"] is False
        assert second.data["display_order"] == 10

    def test_each_gallery_keeps_exactly_one_primary(self, admin_client, product, blue, green):
        for color in (None, blue, green):
            upload(admin_client, product, color, "a.png")
            upload(admin_client, product, color, "b.png")

        for color in (None, blue, green):
            assert len(primary_ids(product, color)) == 1

    def test_the_cap_is_per_gallery(self, admin_client, product, blue):
        for index in range(MAX_IMAGES_PER_PRODUCT):
            assert upload(admin_client, product, name=f"base-{index}.png").status_code == 201

        # The base gallery is full — the colour's is not
        assert upload(admin_client, product, name="extra.png").status_code == 409
        assert upload(admin_client, product, blue, "own.png").status_code == 201

    def test_a_full_colour_gallery_is_refused_with_its_own_message(
        self, admin_client, product, blue
    ):
        for index in range(MAX_IMAGES_PER_PRODUCT):
            upload(admin_client, product, blue, f"c-{index}.png")

        refused = upload(admin_client, product, blue, "one-too-many.png")

        assert refused.status_code == 409
        assert ProductImage.objects.filter(color=blue).count() == MAX_IMAGES_PER_PRODUCT

    def test_another_products_colour_is_refused(self, admin_client, product):
        foreign = add_color(make_product("CLR-002"), "Red")

        response = upload(admin_client, product, foreign)

        assert response.status_code == 400
        assert not ProductImage.objects.exists()

    def test_an_unknown_or_malformed_colour_is_a_400_not_a_500(self, admin_client, product):
        for bad in (str(uuid.uuid4()), "not-a-uuid"):
            response = admin_client.post(
                images_url(product), {"image": png_upload(), "color": bad}, format="multipart"
            )
            assert response.status_code == 400

    def test_a_deleted_colour_cannot_receive_images(self, admin_client, product, blue):
        blue.delete()

        assert upload(admin_client, product, blue).status_code == 400

    def test_a_customer_cannot_upload(self, product, blue):
        assert upload(make_customer_client(), product, blue).status_code == 403


@pytest.mark.django_db
class TestListing:
    def test_the_default_is_the_base_gallery(self, admin_client, product, blue):
        upload(admin_client, product, name="base.png")
        upload(admin_client, product, blue, "own.png")

        rows = admin_client.get(images_url(product)).data

        assert len(rows) == 1 and rows[0]["color"] is None

    def test_a_colour_filter_shows_its_own(self, admin_client, product, blue, green):
        upload(admin_client, product, blue, "b.png")
        upload(admin_client, product, green, "g.png")

        rows = admin_client.get(images_url(product), {"color": str(blue.pk)}).data

        assert [str(row["color"]) for row in rows] == [str(blue.pk)]

    def test_all_returns_every_gallery(self, admin_client, product, blue):
        upload(admin_client, product, name="base.png")
        upload(admin_client, product, blue, "own.png")

        assert len(admin_client.get(images_url(product), {"color": "all"}).data) == 2

    def test_a_malformed_filter_is_empty_not_an_error(self, admin_client, product):
        response = admin_client.get(images_url(product), {"color": "nonsense"})

        assert response.status_code == 200 and response.data == []


@pytest.mark.django_db
class TestPrimaryAndOrder:
    def test_setting_a_primary_only_unsets_within_its_scope(self, admin_client, product, blue):
        base_primary = str(upload(admin_client, product, name="base.png").data["id"])
        upload(admin_client, product, blue, "a.png")
        second = str(upload(admin_client, product, blue, "b.png").data["id"])

        response = admin_client.post(
            reverse("v1:catalog:admin-product-image-primary", args=[product.pk, second])
        )

        assert response.status_code == 200
        assert [str(pk) for pk in primary_ids(product, blue)] == [second]
        assert [str(pk) for pk in primary_ids(product)] == [base_primary], "الرئيسية العامة لم تُمَسّ"

    def test_deleting_a_colours_primary_promotes_within_that_colour(
        self, admin_client, product, blue
    ):
        base = str(upload(admin_client, product, name="base.png").data["id"])
        first = str(upload(admin_client, product, blue, "a.png").data["id"])
        second = str(upload(admin_client, product, blue, "b.png").data["id"])

        response = admin_client.delete(
            reverse("v1:catalog:admin-product-image-detail", args=[product.pk, first])
        )

        assert response.status_code == 204
        assert [str(pk) for pk in primary_ids(product, blue)] == [second]
        assert [str(pk) for pk in primary_ids(product)] == [base]

    def test_deleting_the_base_primary_never_promotes_a_colour_image(
        self, admin_client, product, blue
    ):
        """
        ⚠️  The replacement search used to be "any image of the product". With colours
            that would pick the blue photo and trip the per-scope unique constraint.
        """
        base = str(upload(admin_client, product, name="base.png").data["id"])
        upload(admin_client, product, blue, "own.png")

        admin_client.delete(
            reverse("v1:catalog:admin-product-image-detail", args=[product.pk, base])
        )

        assert primary_ids(product) == []
        assert len(primary_ids(product, blue)) == 1

    def test_reorder_works_inside_a_colour(self, admin_client, product, blue):
        first = str(upload(admin_client, product, blue, "a.png").data["id"])
        second = str(upload(admin_client, product, blue, "b.png").data["id"])

        response = admin_client.post(
            reverse("v1:catalog:admin-product-images-reorder", args=[product.pk]),
            {"order": [second, first], "color": str(blue.pk)},
            format="json",
        )

        assert response.status_code == 200
        assert [str(row["id"]) for row in response.data] == [second, first]

    def test_reorder_refuses_ids_from_another_scope(self, admin_client, product, blue):
        base = str(upload(admin_client, product, name="base.png").data["id"])
        own = str(upload(admin_client, product, blue, "own.png").data["id"])

        # The colour's id sent without naming the colour is "not in the base gallery"
        response = admin_client.post(
            reverse("v1:catalog:admin-product-images-reorder", args=[product.pk]),
            {"order": [own, base]},
            format="json",
        )

        assert response.status_code == 400


@pytest.mark.django_db
class TestConstraints:
    def test_the_database_allows_one_primary_per_scope_and_no_more(self, product, blue, green):
        def image(color, primary):
            return ProductImage.objects.create(
                product=product, color=color, image=png_upload(), is_primary=primary
            )

        image(None, True)
        image(blue, True)
        image(green, True)

        for color in (None, blue, green):
            with pytest.raises(IntegrityError), transaction.atomic():
                image(color, True)

    def test_a_soft_deleted_primary_frees_the_slot(self, product, blue):
        first = ProductImage.objects.create(
            product=product, color=blue, image=png_upload(), is_primary=True
        )
        first.delete()

        ProductImage.objects.create(
            product=product, color=blue, image=png_upload(), is_primary=True
        )
