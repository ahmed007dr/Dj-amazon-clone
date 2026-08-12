"""
استعلامات الكتالوج.

⚠️  كل دالة هنا مسؤولة عن **ألا تُنتج N+1**.

    قائمة منتجات تعرض: الاسم · الفئة · البراند · الصورة · التقييم ·
    السعر · التوفر. بلا `select_related`/`prefetch_related` تصير
    كل صفحة عشرات الاستعلامات.
"""

from __future__ import annotations

from django.db.models import Prefetch, Q

from access.services import accessible_filter
from catalog.models import Category, Product, ProductImage, ProductVariant


def product_base_queryset():
    """
    الأساس المشترك — يُحمّل كل ما تعرضه بطاقة المنتج دفعة واحدة.

    `rating` من `reviews.ProductRating` عبر `select_related` —
    وهو ما يستبدل الـ properties القديمة التي كانت تستعلم لكل صف.
    """
    primary_images = ProductImage.objects.filter(is_primary=True)

    return Product.objects.select_related(
        "category",
        "brand",
        "manufacturer",
        "access_policy",
        "tax_class",
        "rating",
    ).prefetch_related(
        Prefetch("images", queryset=primary_images, to_attr="primary_images"),
    )


def published_products(user=None):
    """المنتجات المنشورة المتاحة لهذا المستخدم."""
    queryset = product_base_queryset().filter(is_active=True)

    if user is not None:
        queryset = queryset.filter(accessible_filter(user))

    return queryset


def product_detail_queryset(user=None):
    """صفحة المنتج — تُحمّل الصور والنسخ كاملة."""
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
    منتجات فئة.

    ⚠️  `include_descendants` افتراضيًا `True`.

        فتح «مستلزمات طبية» يجب أن يُظهر ما تحتها كله — عرض ما
        أُسند للفئة الأب مباشرةً فقط يعطي صفحة شبه فارغة.

        المسار المادي يجعلها استعلامًا واحدًا بـ `startswith`.
    """
    queryset = published_products(user)

    if include_descendants:
        return queryset.filter(
            Q(category=category) | Q(category__path__startswith=f"{category.path}/")
        )

    return queryset.filter(category=category)


def search_products(term: str, user=None):
    """
    بحث نصي.

    ⚠️  يبحث في اللغتين والمادة الفعّالة و SKU والباركود معًا.

        الصيدلي يبحث بالمادة الفعّالة لا بالاسم التجاري، والكاشير
        يبحث بالباركود. بحث في الاسم وحده يفشل عندهما.

        FTS الحقيقي يأتي مع PostgreSQL — هذا كافٍ للتطوير على SQLite.
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
    """شجرة القائمة — استعلام واحد ثم بناء الشجرة في الذاكرة."""
    return Category.objects.filter(is_active=True, show_in_menu=True).order_by(
        "path", "display_order"
    )


def build_category_tree(categories) -> list[dict]:
    """
    يحوّل قائمة مسطّحة إلى شجرة متداخلة.

    ⚠️  في الذاكرة لا بقاعدة البيانات — استعلام واحد بدل استعلام
        لكل مستوى.
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
