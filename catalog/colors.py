"""
Product colours — creating, changing and retiring them.

⚠️  Everything that touches a colour goes through here: the admin API, the
    importer, the seed and the `backfill_product_colors` command. Writing
    `ProductColor` rows directly from a second place is how a colour ends up
    with no variant (it cannot be bought) or a variant whose name no longer
    matches its colour.

A colour owns **one variant, created with it**. Stock, the cart, order lines and
the counter all speak `ProductVariant`, so a colour that is one-to-one with a
variant works in every one of them with no further change. A product that
*also* has size variants keeps them: they stay `color=NULL` and keep working —
a colour never rewrites a variant it did not create.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.utils.text import slugify

from catalog.models import Product, ProductColor, ProductImage, ProductVariant
from core.errors import BusinessError, ErrorCode

#: Matches `ProductVariant.sku.max_length`
SKU_MAX_LENGTH = 64


# ═══════════════════════════════════════════════════════════
#  Variant SKUs
# ═══════════════════════════════════════════════════════════


def generate_variant_sku(product: Product, name_en: str, hex_: str = "") -> str:
    """
    `<product sku>-<COLOUR>`, unique even against soft-deleted variants.

    ⚠️  `ProductVariant.sku` is `unique=True` **without** a `deleted_at` condition.

        Delete "Blue" and add "Blue" again and the natural SKU is still held by
        the dead row — so the check looks at `all_objects`, and a counter is
        appended until it is free.

    An Arabic-only name slugifies to nothing, so the hex digits stand in for it.
    """
    suffix = slugify(name_en or "", allow_unicode=False).upper() or hex_.lstrip("#").upper() or "C"
    stem = f"{product.sku}-{suffix}"[:SKU_MAX_LENGTH]

    candidate = stem
    counter = 2
    while ProductVariant.all_objects.filter(sku=candidate).exists():
        tail = f"-{counter}"
        candidate = f"{stem[: SKU_MAX_LENGTH - len(tail)]}{tail}"
        counter += 1
    return candidate


# ═══════════════════════════════════════════════════════════
#  Reading
# ═══════════════════════════════════════════════════════════


def variant_snapshot(variant: ProductVariant | None) -> dict:
    """
    What a sale must remember about the variant — and its colour — it sold.

    Keys are the `OrderLine` snapshot columns, so a caller does
    `OrderLine(**variant_snapshot(variant), ...)`. All blank for a plain product.

    ⚠️  A copy, not a reference. The colour may be renamed, repriced or deleted next
        month; the invoice keeps saying what the customer was actually sold.
        Reads `variant.color` — callers `select_related("color")` to keep it free.
    """
    if variant is None:
        return {
            "variant_sku": "",
            "variant_name_ar": "",
            "variant_name_en": "",
            "color_name_ar": "",
            "color_name_en": "",
            "color_hex": "",
        }

    color = variant.color if variant.color_id else None
    return {
        "variant_sku": variant.sku,
        "variant_name_ar": variant.name_ar,
        "variant_name_en": variant.name_en,
        "color_name_ar": color.name_ar if color else "",
        "color_name_en": color.name_en if color else "",
        "color_hex": color.hex if color else "",
    }


def colors_of(product: Product, *, include_inactive: bool = True):
    """The product's living colours in display order."""
    queryset = ProductColor.objects.filter(product=product)
    if not include_inactive:
        queryset = queryset.filter(is_active=True)
    return queryset


def next_display_order(product: Product) -> int:
    top = ProductColor.objects.filter(product=product).aggregate(top=Max("display_order"))["top"]
    return 0 if top is None else top + 10


def assert_variant_choice(product: Product, variant: ProductVariant | None) -> None:
    """
    The variant a buyer picked must be this product's, still on sale — and **present**
    whenever the product offers any. Used by the cart and by the counter.

    ⚠️  Three things the UI used to be the only guard for:

        * the API fetched the variant by id alone, so a variant of an entirely
          different (cheaper) product could ride along on this product's line;
        * a product with colours could be added with no colour, and the unassigned
          stock behind it is not what the customer would receive;
        * a colour the admin has since hidden stayed purchasable from an old tab.
    """
    from catalog.selectors import has_sellable_variants

    if variant is not None:
        if variant.product_id != product.pk:
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR, detail="الخيار المختار لا يخص هذا المنتج"
            )
        if not variant.is_sellable:
            raise BusinessError(
                ErrorCode.PRODUCT_UNAVAILABLE, detail="هذا اللون أو الخيار لم يعد متاحًا"
            )
        return

    if has_sellable_variants(product):
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="اختر اللون أو الخيار أولًا")


# ═══════════════════════════════════════════════════════════
#  Writing
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def create_color(
    product: Product,
    *,
    name_ar: str,
    name_en: str,
    hex: str = "#9CA3AF",  # noqa: A002 — the column's own name
    price_override: Decimal | None = None,
    display_order: int | None = None,
    is_active: bool = True,
) -> ProductColor:
    """
    Add a colour **and its variant** in one transaction.

    ⚠️  Never one without the other: a colour with no variant shows a swatch the
        customer can pick and the cart then refuses.
    """
    color = ProductColor.objects.create(
        product=product,
        name_ar=name_ar,
        name_en=name_en,
        hex=hex,
        price_override=price_override,
        display_order=next_display_order(product) if display_order is None else display_order,
        is_active=is_active,
    )
    ensure_variant(color)
    return color


def ensure_variant(color: ProductColor) -> ProductVariant:
    """
    The colour's first living variant — created if it has none.

    Idempotent, so the importer and the backfill command can call it for colours
    that already exist without minting a second variant.
    """
    variant = color.variants.order_by("display_order", "created_at").first()
    if variant is not None:
        return variant

    return ProductVariant.objects.create(
        product=color.product,
        color=color,
        sku=generate_variant_sku(color.product, color.name_en, color.hex),
        name_ar=color.name_ar,
        name_en=color.name_en,
        attributes={"color": color.name_en},
        display_order=color.display_order,
        is_active=color.is_active,
    )


@transaction.atomic
def update_color(color: ProductColor, **changes) -> dict:
    """
    Apply `changes` and keep the colour's variants in step. Returns `{field: {old, new}}`.

    * `is_active` is copied to the variants — a hidden colour must not stay
      purchasable through a stale cart (`ProductVariant.is_sellable` checks it too).
    * A rename is copied to the variants that still carry the **old** names. One a
      human renamed by hand ("Blue — Large") is theirs and is left alone.
    """
    allowed = {"name_ar", "name_en", "hex", "price_override", "display_order", "is_active"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValueError(f"حقول غير مسموحة: {sorted(unknown)}")

    before = {name: getattr(color, name) for name in changes}
    old_names = (color.name_ar, color.name_en)

    for name, value in changes.items():
        setattr(color, name, value)
    color.save()

    diff = {
        name: {"old": _plain(before[name]), "new": _plain(getattr(color, name))}
        for name in changes
        if before[name] != getattr(color, name)
    }

    variants = color.variants.all()
    if "is_active" in diff:
        variants.update(is_active=color.is_active)

    if "name_ar" in diff or "name_en" in diff:
        for variant in variants:
            if variant.name_ar == old_names[0]:
                variant.name_ar = color.name_ar
            if variant.name_en == old_names[1]:
                variant.name_en = color.name_en
            attributes = dict(variant.attributes or {})
            if attributes.get("color") == old_names[1]:
                attributes["color"] = color.name_en
            variant.attributes = attributes
            variant.save(update_fields=["name_ar", "name_en", "attributes", "updated_at"])

    return diff


def _plain(value):
    return str(value) if isinstance(value, Decimal) else value


@dataclass(frozen=True)
class DeleteResult:
    variants_deactivated: int
    images_removed: int


@transaction.atomic
def delete_color(color: ProductColor) -> DeleteResult:
    """
    Soft-delete a colour, deactivate its variants and remove its images.

    ⚠️  The variants are **deactivated, not deleted.**

        Stock rows, batches and order lines point at them (all `PROTECT`), and
        an old invoice must still say which colour it was. Deactivating takes
        them off sale; the history stays whole.

    ⚠️  Whatever stock they still hold stays in the books, unsellable — which is
        why the API asks for confirmation when there is some.
    """
    deactivated = ProductVariant.objects.filter(color=color, is_active=True).update(is_active=False)
    removed = ProductImage.objects.filter(color=color).count()
    ProductImage.objects.filter(color=color).delete()  # a queryset soft delete
    color.delete()
    return DeleteResult(variants_deactivated=deactivated, images_removed=removed)


@transaction.atomic
def reorder_colors(product: Product, ordered_ids: list) -> list[ProductColor]:
    """
    Set the display order from an id list. Every id must be one of the product's colours.

    ⚠️  Validated before anything is written — see `image_api.ReorderImagesAPI`.
    """
    owned = {str(pk) for pk in ProductColor.objects.filter(product=product).values_list("pk", flat=True)}
    unknown = [str(pk) for pk in ordered_ids if str(pk) not in owned]
    if unknown:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            detail="معرّفات ألوان لا تخص هذا المنتج: " + ", ".join(unknown),
        )

    for index, pk in enumerate(ordered_ids):
        color = ProductColor.objects.filter(pk=pk, product=product).first()
        if color is None:
            continue
        position = index * 10
        ProductColor.objects.filter(pk=pk).update(display_order=position)
        # The auto-variant orders with its colour, so "first variant" stays the colour's.
        ProductVariant.objects.filter(color=color).update(display_order=position)

    return list(ProductColor.objects.filter(product=product))
