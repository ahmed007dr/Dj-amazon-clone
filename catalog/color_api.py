"""
Product colours — the admin endpoints.

    /catalog/admin/products/<pk>/colors/                 list · create
    /catalog/admin/products/<pk>/colors/<color>/         read · update · delete
    /catalog/admin/products/<pk>/colors/reorder/         set the display order

⚠️  Every write is audited **on the product's timeline** (`catalog.audit`) —
    a colour is part of the product, and "who changed the price of the red one?"
    is a question about the product.

⚠️  A colour's images are managed through the image endpoints with `?color=` /
    a `color` form field (see `image_api`), not from here.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog import audit, colors
from catalog.color_serializers import AdminProductColorSerializer
from catalog.models import Product, ProductColor, ProductImage
from core.color_facts import color_facts
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction
from core.permissions import CanManageCatalog

#: The provider whose facts the admin list reads (`inventory.apps`)
STOCK_PROVIDER = "inventory.color_stock"


def _object_repr(product: Product) -> str:
    return f"لون منتج {product.sku}"


def _annotated(queryset):
    """The colour rows with what the admin list shows, in a fixed handful of queries."""
    # ⚠️  An explicit `order_by`: an aggregate annotation drops `Meta.ordering`, and the
    #     swatches would come back in whatever order the database felt like.
    return queryset.annotate(
        image_count=Count("images", filter=Q(images__deleted_at__isnull=True), distinct=True)
    ).order_by("display_order", "created_at").prefetch_related(
        Prefetch(
            "images",
            queryset=ProductImage.objects.filter(is_primary=True),
            to_attr="primary_images",
        ),
        Prefetch("variants", to_attr="color_variants"),
    )


class _ProductColorMixin:
    permission_classes = [CanManageCatalog]
    pagination_class = None

    def get_product(self) -> Product:
        # ⚠️  A deleted product's colours are not editable — restore it first.
        if not hasattr(self, "_product"):
            self._product = get_object_or_404(Product, pk=self.kwargs["pk"])
        return self._product

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "product": self.get_product()}

    def color_queryset(self):
        return _annotated(ProductColor.objects.filter(product=self.get_product()))

    def facts_for(self, color_list) -> dict:
        return color_facts(self.get_product(), color_list, only=[STOCK_PROVIDER])

    def serializer_for(self, color_or_list, *, many=False):
        items = color_or_list if many else [color_or_list]
        context = {
            "request": self.request,
            "product": self.get_product(),
            "color_facts": self.facts_for(items),
        }
        return AdminProductColorSerializer(color_or_list, many=many, context=context)

    def reload(self, color: ProductColor) -> ProductColor:
        return self.color_queryset().get(pk=color.pk)


class ProductColorListCreateAPI(_ProductColorMixin, generics.ListCreateAPIView):
    serializer_class = AdminProductColorSerializer

    def get_queryset(self):
        return self.color_queryset()

    def list(self, request, *args, **kwargs):
        items = list(self.get_queryset())
        return Response(self.serializer_for(items, many=True).data)

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        product = self.get_product()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        color = colors.create_color(
            product,
            name_ar=data["name_ar"],
            name_en=data["name_en"],
            hex=data["hex"],
            price_override=data.get("price_override"),
            display_order=data.get("display_order"),
            is_active=data.get("is_active", True),
        )

        audit.log_product_change(
            request,
            product,
            AuditAction.CREATE,
            {
                "color": color.name_en,
                "hex": color.hex,
                "price_override": None if color.price_override is None else str(color.price_override),
            },
            object_repr=_object_repr(product),
        )
        audit.stamp_updated(product, request.user)

        return Response(
            self.serializer_for(self.reload(color)).data, status=status.HTTP_201_CREATED
        )


class ProductColorDetailAPI(_ProductColorMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AdminProductColorSerializer
    lookup_url_kwarg = "color_pk"

    def get_queryset(self):
        return self.color_queryset()

    def retrieve(self, request, *args, **kwargs):
        return Response(self.serializer_for(self.get_object()).data)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        diff = colors.update_color(instance, **serializer.validated_data)

        if diff:
            product = self.get_product()
            # ⚠️  A price move is a `PRICE_CHANGE` — the action finance filters the log by.
            price = {k: v for k, v in diff.items() if k == "price_override"}
            other = {k: v for k, v in diff.items() if k != "price_override"}
            label = {"color": instance.name_en}
            if price:
                audit.log_product_change(
                    request,
                    product,
                    AuditAction.PRICE_CHANGE,
                    {**label, **price},
                    object_repr=_object_repr(product),
                )
            if other:
                audit.log_product_change(
                    request,
                    product,
                    AuditAction.UPDATE,
                    {**label, **other},
                    object_repr=_object_repr(product),
                )
            audit.stamp_updated(product, request.user)

        return Response(self.serializer_for(self.reload(instance)).data)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        """
        ⚠️  A colour that still holds stock is deleted only with `?force=true`.

            Deleting is soft and the stock stays on the books, but it stops being
            sellable — the admin should see that number before agreeing, not find
            it in the stock report a week later.
        """
        instance = self.get_object()
        product = self.get_product()

        quantity = (self.facts_for([instance]).get(str(instance.pk)) or {}).get("quantity") or 0
        if quantity and request.query_params.get("force") != "true":
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail=(
                    f"على هذا اللون {quantity} وحدة في المخزون — "
                    "ستبقى في المخزون لكنها لن تُباع. أكّد الحذف للمتابعة."
                ),
                status_code=409,
            )

        result = colors.delete_color(instance)
        audit.log_product_change(
            request,
            product,
            AuditAction.DELETE,
            {
                "color": instance.name_en,
                "soft": True,
                "stock_left": quantity,
                "images_removed": result.images_removed,
            },
            object_repr=_object_repr(product),
        )
        audit.stamp_updated(product, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ReorderColorsAPI(_ProductColorMixin, APIView):
    """Set the swatch order from an id list — the order the storefront shows them in."""

    @transaction.atomic
    def post(self, request, pk):
        order = request.data.get("order")
        if not isinstance(order, list) or not order:
            raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="أرسل `order` كقائمة معرّفات")

        product = self.get_product()
        colors.reorder_colors(product, order)

        audit.log_product_change(
            request,
            product,
            AuditAction.UPDATE,
            {"colors_reordered": [str(pk) for pk in order]},
            object_repr=_object_repr(product),
        )
        items = list(self.color_queryset())
        return Response(self.serializer_for(items, many=True).data, status=status.HTTP_200_OK)
