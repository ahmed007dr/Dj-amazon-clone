"""
Product images — upload, ordering and deletion.

⚠️  **The check is on the file signature, not on its header.**

    `core.files.validate_upload` reads the file's first bytes. Uploading
    `shell.php` with an `image/png` header used to pass a surface check entirely.

⚠️  And there is one "primary image" per product — enforced by a database
    constraint. Setting a second must unset the first in the same transaction,
    or the constraint rejects the operation with an integrity message nobody understands.
"""

from uuid import UUID

from django.db import models, transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog import audit, watermark
from catalog.models import Product, ProductColor, ProductImage
from catalog.serializers import ProductImageSerializer
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction
from core.permissions import CanManageCatalog

#: ⚠️  An upper bound on the number of images.
#:
#:     A product with a hundred images makes its page download tens of megabytes
#:     on a phone, and makes the list query drag rows that are never displayed.
#:     Eight is enough for any medical product.
MAX_IMAGES_PER_PRODUCT = 8


def _parse_uuid(raw):
    """A UUID or `None` — a malformed id is "no such colour", never a 500."""
    try:
        return UUID(str(raw))
    except (ValueError, AttributeError, TypeError):
        return None


def _requested_color(request, product) -> ProductColor | None:
    """
    The colour an upload / reorder is aimed at — `None` = the product's **base** gallery.

    ⚠️  A colour must belong to *this* product.

        The id arrives in a form field, so without the check a colour of another
        product could be named and its gallery filled from the wrong screen.
    """
    raw = request.data.get("color") if hasattr(request, "data") else None
    if raw in (None, "", "null", "base"):
        return None

    color_id = _parse_uuid(raw)
    color = (
        ProductColor.objects.filter(pk=color_id, product=product).first()
        if color_id is not None
        else None
    )
    if color is None:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR, detail=_("هذا اللون لا يخص هذا المنتج"), status_code=400
        )
    return color


def _scope(product_id, color) -> "models.QuerySet":
    """The images of one scope: a colour's own, or the product's base gallery."""
    queryset = ProductImage.objects.filter(product_id=product_id)
    return queryset.filter(color=color) if color is not None else queryset.filter(color__isnull=True)


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
        """
        ⚠️  One scope at a time. No `?color=` means the **base** gallery.

            `?color=<id>` is that colour's own gallery and `?color=all` every image
            of the product. The default keeps this endpoint answering what it always
            did for a product without colours, and stops a colour's photos appearing
            in the main-images panel.
        """
        queryset = ProductImage.objects.filter(product_id=self.kwargs["pk"])
        raw = self.request.query_params.get("color", "")

        if raw == "all":
            return queryset
        if raw in ("", "base"):
            return queryset.filter(color__isnull=True)

        color_id = _parse_uuid(raw)
        return queryset.filter(color_id=color_id) if color_id is not None else queryset.none()

    def get_product(self) -> Product:
        return get_object_or_404(Product.all_objects, pk=self.kwargs["pk"])

    @transaction.atomic
    def perform_create(self, serializer):
        product = self.get_product()
        color = _requested_color(self.request, product)
        existing = _scope(product.pk, color).count()

        # ⚠️  The cap is **per scope**: eight base images and eight per colour.
        if existing >= MAX_IMAGES_PER_PRODUCT:
            message = (
                _("الحد الأقصى {count} صور لكل لون")
                if color is not None
                else _("الحد الأقصى {count} صور لكل منتج")
            )
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail=message.format(count=MAX_IMAGES_PER_PRODUCT),
                status_code=409,
            )

        # ⚠️  The first image **of its scope** automatically becomes that scope's primary.
        #
        #     A product with images but no primary shows up with no image in every
        #     list — and the admin, seeing their images uploaded, cannot work out why.
        #     The same holds per colour: its swatch gallery opens on its primary.
        is_first = existing == 0

        _watermark_if_present(serializer)

        image = serializer.save(
            product=product,
            color=color,
            display_order=existing * 10,
            is_primary=is_first,
        )

        # ⚠️  Through `catalog.audit`, so the entry carries the product's content
        #     type + id and shows up on that product's History timeline.
        audit.log_product_change(
            self.request,
            product,
            AuditAction.CREATE,
            {
                "image_id": str(image.pk),
                "is_primary": is_first,
                **({"color": color.name_en} if color is not None else {}),
            },
            object_repr=f"صورة منتج {product.sku}",
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
        color_id = instance.color_id
        image_id = str(instance.pk)
        instance.delete()

        # Deleting a picture is a content change someone will ask about later.
        product = Product.all_objects.filter(pk=product_id).first()
        if product is not None:
            audit.log_product_change(
                self.request,
                product,
                AuditAction.DELETE,
                {"image_id": image_id, "was_primary": was_primary},
                object_repr=f"صورة منتج {product.sku}",
            )

        if was_primary:
            # ⚠️  The replacement comes from the **same scope** — promoting a colour's
            #     photo to the base gallery's primary (or the reverse) would trip the
            #     per-scope unique constraint and show the wrong picture on every list.
            replacement = (
                ProductImage.objects.filter(product_id=product_id, color_id=color_id)
                .order_by("display_order")
                .first()
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

        # ⚠️  Only within the image's own scope (base gallery or one colour): the
        #     primary of the base gallery and the primary of each colour coexist.
        ProductImage.objects.filter(
            product_id=pk, color_id=image.color_id, is_primary=True
        ).exclude(pk=image.pk).update(is_primary=False)

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

        # ⚠️  An optional `color` names the scope being reordered (absent = the base
        #     gallery). Ids from another scope are "not yours" like any foreign id.
        product = get_object_or_404(Product.all_objects, pk=pk)
        color = _requested_color(request, product)
        scope = _scope(pk, color)

        owned = {str(image_id) for image_id in scope.values_list("id", flat=True)}

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
            scope.filter(pk=image_id).update(display_order=index * 10)

        return Response(
            ProductImageSerializer(scope.order_by("display_order"), many=True).data,
            status=status.HTTP_200_OK,
        )
