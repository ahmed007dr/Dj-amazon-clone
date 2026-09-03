"""
Catalogue queries.

⚠️  Every function here is responsible for **not producing N+1**.

    A product list displays: name · category · brand · image · rating · price ·
    availability. Without `select_related`/`prefetch_related` every page becomes
    dozens of queries.
"""

from __future__ import annotations

from django.db.models import Prefetch, Q

from access.services import accessible_filter
from catalog.models import Category, Product, ProductImage, ProductVariant
from core.visibility import product_visibility_filter


def primary_image_prefetch(prefix: str = "") -> Prefetch:
    """
    The prefetch that fills `product.primary_images` — the attribute every
    serializer reads to render a thumbnail.

    ⚠️  `to_attr` means the attribute simply **does not exist** without this
        prefetch, and `getattr(product, "primary_images", None)` then reads as
        "this product has no image" instead of "nobody loaded them". Any
        queryset whose products get serialised must apply it — `prefix` lets a
        caller reach the products through a relation, e.g. `"product__"` from a
        cart line.
    """
    return Prefetch(
        f"{prefix}images",
        queryset=ProductImage.objects.filter(is_primary=True),
        to_attr="primary_images",
    )


def product_base_queryset():
    """
    The shared base — it loads everything the product card displays in one go.

    `rating` comes from `reviews.ProductRating` through `select_related` — which
    is what replaced the legacy properties that queried per row.
    """
    return Product.objects.select_related(
        "category",
        "brand",
        "manufacturer",
        "access_policy",
        "tax_class",
        "rating",
    ).prefetch_related(
        primary_image_prefetch(),
    )


def in_stock_only(queryset, **context):
    """
    Drop the products whose available quantity is zero.

    ⚠️  The filter comes from **`core.visibility`, not from `inventory`**.

        `inventory` sits above `catalog` in the layer diagram, so importing it
        here inverts the direction and `import-linter` rejects it. `inventory`
        registers its filter at start-up and the catalogue asks the registry for
        whatever was registered — see `core/visibility.py` for why the
        indirection is the point rather than a workaround.

    ⚠️  And it is a **query** every time, never a cached list.

        The admin receives a shipment and the item must return to the storefront
        on the next request. Caching the set of what is in stock means a product
        that arrived this morning stays hidden until something expires the entry
        — and the person who received it has no way to tell why.
    """
    return queryset.filter(product_visibility_filter(**context))


def published_products(user=None, *, include_out_of_stock: bool = False, **context):
    """
    The published products available to this user.

    ⚠️  **Out of stock is out of the list by default.**

        A card offering an item that cannot be bought costs the customer two
        clicks and an error message, and it costs the shop the trust that the
        listing means anything. `include_out_of_stock=True` is for the paths
        that must see everything — the admin panel, and reporting.
    """
    queryset = product_base_queryset().filter(is_active=True)

    if user is not None:
        queryset = queryset.filter(accessible_filter(user))

    if not include_out_of_stock:
        queryset = in_stock_only(queryset, **context)

    return queryset


def product_detail_queryset(user=None):
    """The product page — it loads the images and variants in full."""
    active_variants = ProductVariant.objects.filter(is_active=True)

    queryset = (
        product_base_queryset()
        .filter(is_active=True)
        .prefetch_related(
            "images",
            Prefetch("variants", queryset=active_variants),
        )
    )

    if user is not None:
        queryset = queryset.filter(accessible_filter(user))

    return queryset


def products_in_category(category: Category, user=None, *, include_descendants=True):
    """
    A category's products.

    ⚠️  `include_descendants` defaults to `True`.

        Opening "Medical supplies" must show everything beneath it — displaying
        only what was assigned directly to the parent category gives a nearly
        empty page.

        The materialised path makes this a single `startswith` query.
    """
    queryset = published_products(user)

    if include_descendants:
        return queryset.filter(
            Q(category=category) | Q(category__path__startswith=f"{category.path}/")
        )

    return queryset.filter(category=category)


def search_products(term: str, user=None):
    """
    Text search.

    ⚠️  It searches both languages, the active ingredient, the SKU and the barcode together.

        A pharmacist searches by active ingredient rather than trade name, and a
        cashier searches by barcode. Searching the name alone fails both.

        Real FTS arrives with PostgreSQL — this is sufficient for development on SQLite.
    """
    term = (term or "").strip()
    if not term:
        return published_products(user)

    return published_products(user).filter(
        Q(name_ar__icontains=term)
        | Q(name_en__icontains=term)
        | Q(active_ingredient_ar__icontains=term)
        | Q(active_ingredient_en__icontains=term)
        | Q(sku__iexact=term)
        | Q(barcode__iexact=term)
        | Q(short_description_ar__icontains=term)
        | Q(short_description_en__icontains=term)
    )


def menu_categories():
    """The menu tree — one query, then the tree is built in memory."""
    return Category.objects.filter(is_active=True, show_in_menu=True).order_by(
        "path", "display_order"
    )


def build_category_tree(categories) -> list[dict]:
    """
    Converts a flat list into a nested tree.

    ⚠️  In memory, not in the database — one query instead of one query per level.
    """
    nodes: dict = {}
    roots: list = []

    for category in categories:
        nodes[category.pk] = {"object": category, "children": []}

    for category in categories:
        node = nodes[category.pk]
        parent = nodes.get(category.parent_id)
        if parent is not None:
            parent["children"].append(node)
        else:
            roots.append(node)

    return roots
