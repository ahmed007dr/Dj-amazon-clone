"""
Product images — upload, validation and ordering.

⚠️  **File upload is an entry point, not a data field.**

    The most dangerous thing about this screen is not the image ordering but
    what it accepts: a file stored under `MEDIA_ROOT` is later served to any
    visitor. That is why half the tests here are about rejection, not success.
"""

from decimal import Decimal

import pytest

from core.testing import grant_all_domains
from django.apps import apps
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from catalog.models import Category, Product, ProductImage
from conftest import PDF_BYTES, png_upload, real_png_bytes, upload

PASSWORD = "Str0ng-Test-Pass!23"


@pytest.fixture
def product(db):
    category = Category.objects.create(name_ar="مستلزمات", name_en="Supplies")
    return Product.objects.create(
        sku="IMG-001",
        name_ar="قفازات",
        name_en="Gloves",
        category=category,
        base_price=Decimal("50.00"),
    )


@pytest.fixture
def other_product(db, product):
    return Product.objects.create(
        sku="IMG-002",
        name_ar="كمامات",
        name_en="Masks",
        category=product.category,
        base_price=Decimal("30.00"),
    )


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_user(
        email="img-admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    admin.is_active = True
    admin.save()
    apps.get_model("administration", "AdminProfile").objects.create(user=admin)
    grant_all_domains(admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture
def customer_client(db):
    user = User.objects.create_user(
        email="img-customer@test.local", password=PASSWORD, account_type=AccountType.DOCTOR
    )
    user.is_active = True
    user.save()
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def images_url(product):
    return reverse("v1:catalog:admin-product-images", args=[product.pk])


def post_image(client, product, name="photo.png"):
    return client.post(
        images_url(product),
        {"image": png_upload(name), "alt_text_ar": "صورة", "alt_text_en": "Photo"},
        format="multipart",
    )


# ═══════════════════════════════════════════════════════════
#  File validation
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestUploadValidation:
    def test_valid_png_is_accepted(self, admin_client, product):
        response = post_image(admin_client, product)

        assert response.status_code == 201, response.data
        assert ProductImage.objects.filter(product=product).count() == 1

    def test_forged_content_type_is_rejected(self, admin_client, product):
        """
        ⚠️  **This is the actual attack.**

            An executable script with an `image/png` header used to pass the old
            check entirely, because the header is written by the uploader. The
            signature at the start of the file cannot be changed without
            changing the file.
        """
        response = admin_client.post(
            images_url(product),
            {"image": upload("evil.png", b"<?php system($_GET[0]); ?>", "image/png")},
            format="multipart",
        )

        assert response.status_code == 400
        assert ProductImage.objects.filter(product=product).count() == 0

    def test_pdf_is_rejected_even_though_documents_allow_it(self, admin_client, product):
        """A product page displays images — the image list is narrower than the document list."""
        response = admin_client.post(
            images_url(product),
            {"image": upload("brochure.pdf", PDF_BYTES, "application/pdf")},
            format="multipart",
        )

        assert response.status_code == 400

    def test_empty_file_is_rejected(self, admin_client, product):
        response = admin_client.post(
            images_url(product),
            {"image": upload("empty.png", b"", "image/png")},
            format="multipart",
        )

        assert response.status_code == 400

    def test_oversized_image_is_rejected(self, admin_client, product):
        big = real_png_bytes() + b"0" * (6 * 1024 * 1024)
        response = admin_client.post(
            images_url(product),
            {"image": upload("huge.png", big, "image/png")},
            format="multipart",
        )

        assert response.status_code == 400

    def test_max_images_per_product_is_enforced(self, admin_client, product):
        from catalog.image_api import MAX_IMAGES_PER_PRODUCT

        for index in range(MAX_IMAGES_PER_PRODUCT):
            assert post_image(admin_client, product, f"p{index}.png").status_code == 201

        response = post_image(admin_client, product, "extra.png")
        assert response.status_code == 409


# ═══════════════════════════════════════════════════════════
#  Permissions
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestImagePermissions:
    def test_customer_cannot_upload(self, customer_client, product):
        assert post_image(customer_client, product).status_code == 403

    def test_anonymous_cannot_upload(self, product):
        assert post_image(APIClient(), product).status_code in (401, 403)

    def test_cannot_delete_image_of_another_product(self, admin_client, product, other_product):
        """
        ⚠️  The path carries two ids — and filtering must use both together.

            Relying on the image id alone lets any admin delete any product's
            image through another product's path, so the operation's trace in
            the log is lost.
        """
        post_image(admin_client, product)
        image = ProductImage.objects.get(product=product)

        response = admin_client.delete(
            reverse("v1:catalog:admin-product-image-detail", args=[other_product.pk, image.pk])
        )

        assert response.status_code == 404
        assert ProductImage.objects.filter(pk=image.pk).exists()


# ═══════════════════════════════════════════════════════════
#  The primary image
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPrimaryImage:
    def test_first_image_becomes_primary(self, admin_client, product):
        post_image(admin_client, product)

        assert ProductImage.objects.get(product=product).is_primary is True

    def test_second_image_is_not_primary(self, admin_client, product):
        post_image(admin_client, product, "a.png")
        post_image(admin_client, product, "b.png")

        assert ProductImage.objects.filter(product=product, is_primary=True).count() == 1

    def test_setting_primary_moves_it(self, admin_client, product):
        post_image(admin_client, product, "a.png")
        post_image(admin_client, product, "b.png")
        second = ProductImage.objects.filter(product=product, is_primary=False).first()

        response = admin_client.post(
            reverse("v1:catalog:admin-product-image-primary", args=[product.pk, second.pk])
        )

        assert response.status_code == 200
        second.refresh_from_db()
        assert second.is_primary is True
        assert ProductImage.objects.filter(product=product, is_primary=True).count() == 1

    def test_is_primary_cannot_be_forced_on_upload(self, admin_client, product):
        """
        ⚠️  A read-only field — otherwise the upload breaks the unique constraint with a 500.
        """
        post_image(admin_client, product, "a.png")

        response = admin_client.post(
            images_url(product),
            {"image": png_upload("b.png"), "is_primary": True},
            format="multipart",
        )

        assert response.status_code == 201
        assert ProductImage.objects.filter(product=product, is_primary=True).count() == 1

    def test_deleting_primary_promotes_the_next(self, admin_client, product):
        """
        ⚠️  A product with images but no primary disappears visually from every list.
        """
        post_image(admin_client, product, "a.png")
        post_image(admin_client, product, "b.png")
        primary = ProductImage.objects.get(product=product, is_primary=True)

        response = admin_client.delete(
            reverse("v1:catalog:admin-product-image-detail", args=[product.pk, primary.pk])
        )

        assert response.status_code == 204
        remaining = ProductImage.objects.filter(product=product)
        assert remaining.count() == 1
        assert remaining.first().is_primary is True

    def test_deleting_the_only_image_leaves_no_orphan(self, admin_client, product):
        post_image(admin_client, product)
        image = ProductImage.objects.get(product=product)

        admin_client.delete(
            reverse("v1:catalog:admin-product-image-detail", args=[product.pk, image.pk])
        )

        assert ProductImage.objects.filter(product=product).count() == 0


# ═══════════════════════════════════════════════════════════
#  Ordering
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestReorder:
    def _three(self, admin_client, product):
        for name in ("a.png", "b.png", "c.png"):
            post_image(admin_client, product, name)
        return list(ProductImage.objects.filter(product=product).order_by("display_order"))

    def test_reorder_applies_new_order(self, admin_client, product):
        images = self._three(admin_client, product)
        reversed_ids = [str(image.pk) for image in reversed(images)]

        response = admin_client.post(
            reverse("v1:catalog:admin-product-images-reorder", args=[product.pk]),
            {"order": reversed_ids},
            format="json",
        )

        assert response.status_code == 200
        result = list(
            ProductImage.objects.filter(product=product)
            .order_by("display_order")
            .values_list("id", flat=True)
        )
        assert [str(pk) for pk in result] == reversed_ids

    def test_reorder_rejects_images_of_another_product(self, admin_client, product, other_product):
        """
        ⚠️  A foreign id in the list would have silently reordered another product's images.
        """
        self._three(admin_client, product)
        post_image(admin_client, other_product, "x.png")
        foreign = ProductImage.objects.get(product=other_product)

        response = admin_client.post(
            reverse("v1:catalog:admin-product-images-reorder", args=[product.pk]),
            {"order": [str(foreign.pk)]},
            format="json",
        )

        assert response.status_code == 400

    def test_reorder_rejects_empty_payload(self, admin_client, product):
        response = admin_client.post(
            reverse("v1:catalog:admin-product-images-reorder", args=[product.pk]),
            {"order": []},
            format="json",
        )

        assert response.status_code == 400


# ═══════════════════════════════════════════════════════════
#  Storage
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestStorage:
    def test_stored_name_does_not_leak_the_uploaded_name(self, admin_client, product):
        """
        ⚠️  The original filename carries information and is guessable.

            `media/products/gloves-price-list.png` tells a visitor what we never
            meant to tell them, and a sequential path is tried with a loop.
        """
        post_image(admin_client, product, name="internal-pricing-sheet.png")
        image = ProductImage.objects.get(product=product)

        assert "internal-pricing-sheet" not in image.image.name
