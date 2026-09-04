"""
Product images — upload, ordering and deletion.

⚠️  **The check is on the file signature, not on its header.**

    `core.files.validate_upload` reads the file's first bytes. Uploading
    `shell.php` with an `image/png` header used to pass a surface check entirely.

⚠️  And there is one "primary image" per product — enforced by a database
    constraint. Setting a second must unset the first in the same transaction,
    or the constraint rejects the operation with an integrity message nobody understands.
"""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog import watermark
from catalog.models import Product, ProductImage
from catalog.serializers import ProductImageSerializer
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from core.permissions import CanManageCatalog

#: ⚠️  An upper bound on the number of images.
#:
#:     A product with a hundred images makes its page download tens of megabytes
#:     on a phone, and makes the list query drag rows that are never displayed.
#:     Eight is enough for any medical product.
MAX_IMAGES_PER_PRODUCT = 8


def _watermark_if_present(serializer) -> None:
    """
    ⚠️  Runs on the **validated** file, after `validate_upload` has already
        rejected anything that is not really an image — never on raw input.
    """
    uploaded = serializer.validated_data.get("image")
    if uploaded is None:
        return

    marked = watermark.apply(uploaded)
    if marked is not None:
        serializer.validated_data["image"] = marked


class ProductImageListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [CanManageCatalog]
    serializer_class = ProductImageSerializer
    pagination_class = None

    def get_queryset(self):
        return ProductImage.objects.filter(product_id=self.kwargs["pk"])

    def get_product(self) -> Product:
        return get_object_or_404(Product.all_objects, pk=self.kwargs["pk"])

    @transaction.atomic
    def perform_create(self, serializer):
        product = self.get_product()
        existing = ProductImage.objects.filter(product=product).count()

        if existing >= MAX_IMAGES_PER_PRODUCT:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail=_("الحد الأقصى {count} صور لكل منتج").format(count=MAX_IMAGES_PER_PRODUCT),
                status_code=409,
            )

        # ⚠️  The first image automatically becomes the primary.
        #
        #     A product with images but no primary shows up with no image in every
        #     list — and the admin, seeing their images uploaded, cannot work out why.
        is_first = existing == 0

        _watermark_if_present(serializer)

        image = serializer.save(
            product=product,
            display_order=existing * 10,
            is_primary=is_first,
        )

        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.CREATE,
            object_repr=f"صورة منتج {product.sku}",
            changes={"image_id": str(image.pk), "is_primary": is_first},
        )


class ProductImageDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [CanManageCatalog]
    serializer_class = ProductImageSerializer
    lookup_url_kwarg = "image_pk"

    def get_queryset(self):
        # ⚠️  Filtered by product — no deleting another product's image by guessing its id
        return ProductImage.objects.filter(product_id=self.kwargs["pk"])

    def perform_update(self, serializer):
        # ⚠️  Only when the request actually replaces the file — most updates
        #     here are just the alt text, and re-watermarking an unchanged
        #     image would stack a second mark on top of the first.
        _watermark_if_present(serializer)
        serializer.save()

    @transaction.atomic
    def perform_destroy(self, instance):
        """
        ⚠️  Deleting the primary image promotes the next one.

            Leaving it leaves the product with no primary image despite having
            images, so it disappears visually from every list for no evident reason.
        """
        was_primary = instance.is_primary
        product_id = instance.product_id
        instance.delete()

        if was_primary:
            replacement = (
                ProductImage.objects.filter(product_id=product_id).order_by("display_order").first()
            )
            if replacement is not None:
                replacement.is_primary = True
                replacement.save(update_fields=["is_primary"])


class SetPrimaryImageAPI(APIView):
    """
    Set the primary image.

    ⚠️  Unset and set in **a single transaction**.

        The unique constraint forbids two primary images; setting before
        unsetting is rejected with a raw integrity error that reaches the admin as a 500.
    """

    permission_classes = [CanManageCatalog]

    @transaction.atomic
    def post(self, request, pk, image_pk):
        image = get_object_or_404(ProductImage, pk=image_pk, product_id=pk)

        ProductImage.objects.filter(product_id=pk, is_primary=True).exclude(pk=image.pk).update(
            is_primary=False
        )

        image.is_primary = True
        image.save(update_fields=["is_primary"])

        return Response(ProductImageSerializer(image).data)


class ReorderImagesAPI(APIView):
    """
    Reorder a product's images.

    ⚠️  The order determines what appears first in the gallery after the primary
        — a presentation decision, not a technical detail.
    """

    permission_classes = [CanManageCatalog]

    @transaction.atomic
    def post(self, request, pk):
        order = request.data.get("order")

        if not isinstance(order, list) or not order:
            raise BusinessError(ErrorCode.VALIDATION_ERROR, detail=_("أرسل `order` كقائمة معرّفات"))

        owned = {
            str(image_id)
            for image_id in ProductImage.objects.filter(product_id=pk).values_list("id", flat=True)
        }

        # ⚠️  **Validate before mutating, not after.**
        #
        #     The reverse order used to write and then raise, relying on the
        #     transaction to roll back. That works today — and turns into a silent
        #     partial write the day `@transaction.atomic` is removed for another reason.
        unknown = [str(image_id) for image_id in order if str(image_id) not in owned]
        if unknown:
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR,
                detail=_("معرّفات لا تخصّ هذا المنتج: {ids}").format(ids=", ".join(unknown)),
            )

        for index, image_id in enumerate(order):
            # ⚠️  Filtering by product remains despite the check above — a cheap
            #     second barrier at the point of writing itself.
            ProductImage.objects.filter(pk=image_id, product_id=pk).update(display_order=index * 10)

        return Response(
            ProductImageSerializer(
                ProductImage.objects.filter(product_id=pk).order_by("display_order"),
                many=True,
            ).data,
            status=status.HTTP_200_OK,
        )
