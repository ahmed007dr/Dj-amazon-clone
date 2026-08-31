"""
Catalogue endpoints.

⚠️  Every public list passes through `PolicyAwareQuerySetMixin`.

    A restricted product appears in no results, in no count, and does not open
    by direct link — and the filtering is in the queryset, not in the serializer.
"""

from django.db.models import Q
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from access import services as access_services
from access.preview import PreviewAwareMixin
from access.services import PolicyAwareQuerySetMixin
from catalog import selectors
from catalog import serializers as s
from catalog.models import (
    Brand,
    Category,
    DosageForm,
    Manufacturer,
    Product,
    ProductKind,
    RegulatoryClass,
    StorageCondition,
)
from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from core.models.tax import TaxClass
from core.permissions import CanManageCatalog


class PublicCatalogMixin(PreviewAwareMixin, PolicyAwareQuerySetMixin):
    """
    The shared base for every public catalogue endpoint.

    The inheritance order is deliberate: `PreviewAwareMixin` first so it
    overrides `get_access_user`, then `PolicyAwareQuerySetMixin`, which calls it.
    """

    permission_classes = [AllowAny]
    policy_field = "access_policy"


# ═══════════════════════════════════════════════════════════
#  Products — public
# ═══════════════════════════════════════════════════════════


class ProductListAPI(PublicCatalogMixin, generics.ListAPIView):
    """
    ⚠️  **What has run out does not appear here at all.**

        Not greyed out and not marked "unavailable" — absent, and absent from
        the count and the pagination with it. Filtering in the serializer would
        have read the row and then hidden it: the count stays wrong, a page of
        twenty returns eleven, and the customer paging through sees the gaps.

    ⚠️  **And there is no parameter that brings them back.**

        An `in_stock=false` switch on an `AllowAny` endpoint is not an
        exception to the rule, it is the rule deleted: anyone appending it to
        the URL sees exactly what we undertook to hide. Whoever needs the full
        catalogue — restocking, an export, an audit — goes through
        `admin/products/`, which is behind `CanManageCatalog` and filters
        nothing by design.
    """

    serializer_class = s.ProductListSerializer

    def get_base_queryset(self):
        # ⚠️  `get_base_queryset`, not `get_queryset` —
        #     overriding the latter silently disables policy filtering.
        queryset = selectors.product_base_queryset().filter(is_active=True)
        params = self.request.query_params

        queryset = selectors.in_stock_only(queryset)

        if term := params.get("search"):
            queryset = queryset.filter(
                Q(name_ar__icontains=term)
                | Q(name_en__icontains=term)
                | Q(active_ingredient_ar__icontains=term)
                | Q(active_ingredient_en__icontains=term)
                | Q(sku__iexact=term)
                | Q(barcode__iexact=term)
            )

        if category_slug := params.get("category"):
            category = Category.objects.filter(slug=category_slug).first()
            if category is not None:
                queryset = queryset.filter(
                    Q(category=category) | Q(category__path__startswith=f"{category.path}/")
                )
            else:
                queryset = queryset.none()

        if brand_slug := params.get("brand"):
            queryset = queryset.filter(brand__slug=brand_slug)
        if kind := params.get("kind"):
            queryset = queryset.filter(kind=kind)
        if params.get("featured") == "true":
            queryset = queryset.filter(is_featured=True)

        if price_min := params.get("price_min"):
            queryset = queryset.filter(base_price__gte=price_min)
        if price_max := params.get("price_max"):
            queryset = queryset.filter(base_price__lte=price_max)

        ordering = params.get("ordering", "-created_at")
        allowed = {
            "created_at",
            "-created_at",
            "base_price",
            "-base_price",
            "name_ar",
            "-name_ar",
            "rating__average",
            "-rating__average",
        }
        if ordering in allowed:
            queryset = queryset.order_by(ordering)

        return queryset


class ProductDetailAPI(PublicCatalogMixin, generics.RetrieveAPIView):
    """
    ⚠️  The identifier is the `slug`, not a UUID — a product page needs SEO. (ADR-27)

        And a restricted one returns `404`, not `403`: the difference between
        them exposes the list of restricted products by scanning URLs.
    """

    serializer_class = s.ProductDetailSerializer
    lookup_field = "slug"

    def get_base_queryset(self):
        return selectors.product_detail_queryset().filter(is_active=True)


class ProductByBarcodeAPI(PublicCatalogMixin, generics.RetrieveAPIView):
    """
    Barcode lookup — for the point-of-sale scanner.

    A separate endpoint because the path differs and the response is lighter.
    """

    serializer_class = s.ProductDetailSerializer
    lookup_field = "barcode"

    def get_base_queryset(self):
        return selectors.product_detail_queryset().filter(is_active=True)


# ═══════════════════════════════════════════════════════════
#  Categories and brands
# ═══════════════════════════════════════════════════════════


class CategoryTreeAPI(APIView):
    """
    The complete menu tree.

    ⚠️  One query, then the tree is built in memory.
        Building it with queries = one query per node.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        categories = list(selectors.menu_categories())
        tree = selectors.build_category_tree(categories)

        return Response(
            [
                s.CategorySerializer(node["object"], context={"tree_node": node}).data
                for node in tree
            ]
        )


class CategoryDetailAPI(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = s.CategorySerializer
    lookup_field = "slug"
    queryset = Category.objects.filter(is_active=True)


class BrandListAPI(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = s.BrandSerializer
    pagination_class = None

    def get_queryset(self):
        queryset = Brand.objects.filter(is_active=True).select_related("manufacturer")
        if self.request.query_params.get("featured") == "true":
            queryset = queryset.filter(is_featured=True)
        return queryset


class BrandDetailAPI(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = s.BrandSerializer
    lookup_field = "slug"
    queryset = Brand.objects.filter(is_active=True).select_related("manufacturer")


class ManufacturerListAPI(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = s.ManufacturerSerializer
    pagination_class = None
    queryset = Manufacturer.objects.filter(is_active=True)


# ═══════════════════════════════════════════════════════════
#  Admin
# ═══════════════════════════════════════════════════════════


class AdminProductListCreateAPI(generics.ListCreateAPIView):
    """
    ⚠️  **No policy filtering** — the admin manages every product, including the
        restricted ones. That is why this does not inherit `PublicCatalogMixin`.
    """

    permission_classes = [CanManageCatalog]
    serializer_class = s.AdminProductSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = Product.all_objects.select_related(
            "category", "brand", "manufacturer", "access_policy"
        )
        params = self.request.query_params

        if params.get("include_deleted") != "true":
            queryset = queryset.filter(deleted_at__isnull=True)
        if search := params.get("search"):
            queryset = queryset.filter(
                Q(name_ar__icontains=search)
                | Q(name_en__icontains=search)
                | Q(sku__icontains=search)
                | Q(barcode__iexact=search)
            )

        # ⚠️  `is_active` is what the frontend sends.
        #
        #     The server used to read `inactive` alone, so the status filter passed
        #     through with no effect: the screen showed "active" while the results
        #     included the discontinued. A filter that does not filter is worse than none — it gets
        #     believed.
        if (is_active := params.get("is_active")) in ("true", "false"):
            queryset = queryset.filter(is_active=is_active == "true")

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        product = serializer.save()
        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.CREATE,
            object_repr=f"منتج {product.sku}",
            changes={"name_ar": product.name_ar, "sku": product.sku},
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )


class AdminProductDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [CanManageCatalog]
    serializer_class = s.AdminProductSerializer
    queryset = Product.all_objects.all()

    def perform_destroy(self, instance):
        """
        Always a soft delete.

        ⚠️  A sold product is referenced by historical orders and stock
            movements — deleting it for real breaks every past report.
        """
        instance.delete()

        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.DELETE,
            object_repr=f"منتج {instance.sku}",
            changes={"name_ar": instance.name_ar, "soft": True},
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )


class RestoreProductAPI(APIView):
    """
    Restore a soft-deleted product.

    ⚠️  A soft delete with no restore is a permanent delete from the user's point of view.

        The row remains in the database, but bringing it back used to need a
        developer or the Django panel — and the first question after an
        accidental delete is "how do I get it back?".
    """

    permission_classes = [CanManageCatalog]

    def post(self, request, pk):
        product = Product.all_objects.filter(pk=pk).first()
        if product is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        if product.deleted_at is None:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail="هذا المنتج غير محذوف",
                status_code=409,
            )

        product.restore()

        AuditLog.objects.create(
            actor=request.user,
            action=AuditAction.RESTORE,
            object_repr=f"منتج {product.sku}",
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        return Response(s.AdminProductSerializer(product).data)


class ProductFormOptionsAPI(APIView):
    """
    Everything the create-product screen needs — in one call.

    ⚠️  **The lists come from the server, never duplicated in the frontend.**

        Hard-coding dosage forms or regulatory classifications in frontend code
        means a value added on the server never reaches the admin, and a value
        removed leaves an option that fails on save. There is one source.

    ⚠️  And **the categories are flattened with their full path**, not a tree.

        A select list does not render a tree; and "Tablets" alone is ambiguous
        when it exists under both "Medicines" and "Supplements". The path settles which.

    ⚠️  And it includes categories not visible in the public menu.

        The public categories endpoint filters by `show_in_menu`, which is a
        **display** classification, not a permission one: a category hidden from
        the store menu is still a valid category for a product. Relying on it
        here stopped the admin choosing categories that exist.

    ⚠️  And `access_policies` is **part of the form, not an advanced setting**.

        It is the answer to "who sees this product?" — public, students, verified
        professionals or pharmacies. Dropping it from the create screen makes
        every new product silently inherit the default: a restricted medicine
        published to everyone, discovered only when someone not entitled to it buys it.
    """

    permission_classes = [CanManageCatalog]

    def get(self, request):
        return Response(
            {
                "kinds": _choices(ProductKind),
                "regulatory_classes": _choices(RegulatoryClass),
                "dosage_forms": _choices(DosageForm),
                "storage_conditions": _choices(StorageCondition),
                "categories": _flat_categories(),
                "brands": [
                    {"id": str(brand.id), "name_ar": brand.name_ar, "name_en": brand.name_en}
                    for brand in Brand.objects.filter(is_active=True).order_by("name_ar")
                ],
                "manufacturers": [
                    {"id": str(maker.id), "name_ar": maker.name_ar, "name_en": maker.name_en}
                    for maker in Manufacturer.objects.filter(is_active=True).order_by("name_ar")
                ],
                # ⚠️  Through `access.services`, not `access.models` — a domain's public
                #     interface is its services.
                "access_policies": [
                    {
                        "id": str(policy.id),
                        "code": policy.code,
                        "name_ar": policy.name_ar,
                        "name_en": policy.name_en,
                        "level": policy.level,
                        "is_default": policy.is_default,
                        # ⚠️  Both conditions are displayed alongside the name: "verified
                        #     professionals" alone does not say that an unverified doctor is
                        #     blocked.
                        "requires_verification": policy.requires_verification,
                        "allowed_account_types": policy.allowed_account_types,
                        "description_ar": policy.description_ar,
                        "description_en": policy.description_en,
                    }
                    for policy in access_services.selectable_policies()
                ],
                "tax_classes": [
                    {
                        "id": str(tax_class.id),
                        "name_ar": tax_class.name_ar,
                        "name_en": tax_class.name_en,
                        "rate": str(tax_class.rate),
                        "is_default": tax_class.is_default,
                    }
                    for tax_class in TaxClass.objects.filter(is_active=True).order_by(
                        "-is_default", "code"
                    )
                ],
            }
        )


def _choices(choices_class) -> list[dict]:
    """
    ⚠️  The Arabic label comes from `TextChoices`, not from a dictionary in the
        frontend — so there are never two places naming the same value differently.
    """
    return [{"value": value, "label": str(label)} for value, label in choices_class.choices]


def _flat_categories() -> list[dict]:
    """The active categories, flattened, each with its readable path."""
    categories = list(Category.objects.filter(is_active=True).order_by("path", "display_order"))
    names = {category.pk: category for category in categories}

    def label(category) -> str:
        parts, node, guard = [], category, 0
        # ⚠️  A depth guard: a corrupt path with a parent pointing at itself hangs
        #     the request forever with no trace in any log.
        while node is not None and guard < 8:
            parts.append(node.name_ar)
            node = names.get(node.parent_id)
            guard += 1
        return " ← ".join(reversed(parts))

    return [
        {
            "id": str(category.id),
            "name_ar": category.name_ar,
            "name_en": category.name_en,
            "path_label": label(category),
        }
        for category in categories
    ]


# ═══════════════════════════════════════════════════════════
#  Admin — reference classification
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  Deletion in all three is **refused when in use**, never carried out silently.
#
#      The `PROTECT` relations already prevent it in the database, but the error
#      arrives there as a 500 crash rather than a message. The check here turns
#      it into "this category has 12 products" — which is what the admin needs to decide.


class _ReferenceAdmin:
    """The shared base: admin permission, no pagination, and audit logging."""

    permission_classes = [CanManageCatalog]
    pagination_class = None

    #: Appears in the audit log
    label = ""

    def _audit(self, instance, action):
        AuditLog.objects.create(
            actor=self.request.user,
            action=action,
            object_repr=f"{self.label} {instance.name_ar}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )


class AdminCategoryListCreateAPI(_ReferenceAdmin, generics.ListCreateAPIView):
    """
    ⚠️  Flat, not a tree — and ordering by path makes it read as a tree.

        A nested tree needs flattening in the frontend for every select list,
        and the `path` gives the tree ordering for free.

    ⚠️  And it includes those not visible in the public menu: `show_in_menu` is a
        **display** classification, not a permission.
    """

    serializer_class = s.AdminCategorySerializer
    label = "فئة"

    def get_queryset(self):
        queryset = Category.objects.select_related("parent").order_by("path", "display_order")

        if (active := self.request.query_params.get("is_active")) in ("true", "false"):
            queryset = queryset.filter(is_active=active == "true")
        if search := self.request.query_params.get("search"):
            queryset = queryset.filter(Q(name_ar__icontains=search) | Q(name_en__icontains=search))
        return queryset

    def perform_create(self, serializer):
        self._audit(serializer.save(), AuditAction.CREATE)


class AdminCategoryDetailAPI(_ReferenceAdmin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = s.AdminCategorySerializer
    queryset = Category.objects.select_related("parent")
    label = "فئة"

    def perform_update(self, serializer):
        self._audit(serializer.save(), AuditAction.SETTING_CHANGE)

    def perform_destroy(self, instance):
        """
        ⚠️  A category in use is not deleted — and the message **counts** what blocks it.

            "Cannot delete" alone makes the admin hunt for the reason by trial.
        """
        products = instance.products.count()
        children = instance.children.count()

        if products or children:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail=(
                    f"لهذه الفئة {products} منتجًا و{children} فئة فرعية — "
                    "انقلها أو أوقف الفئة بدل حذفها"
                ),
                status_code=409,
            )

        self._audit(instance, AuditAction.DELETE)
        instance.delete()


class AdminManufacturerListCreateAPI(_ReferenceAdmin, generics.ListCreateAPIView):
    serializer_class = s.AdminManufacturerSerializer
    label = "شركة مصنّعة"

    def get_queryset(self):
        queryset = Manufacturer.objects.order_by("name_ar")
        if search := self.request.query_params.get("search"):
            queryset = queryset.filter(Q(name_ar__icontains=search) | Q(name_en__icontains=search))
        return queryset

    def perform_create(self, serializer):
        self._audit(serializer.save(), AuditAction.CREATE)


class AdminManufacturerDetailAPI(_ReferenceAdmin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = s.AdminManufacturerSerializer
    queryset = Manufacturer.objects.all()
    label = "شركة مصنّعة"

    def perform_update(self, serializer):
        self._audit(serializer.save(), AuditAction.SETTING_CHANGE)

    def perform_destroy(self, instance):
        brands = instance.brands.count()
        if brands:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail=f"لهذه الشركة {brands} براند — أوقفها بدل حذفها",
                status_code=409,
            )

        self._audit(instance, AuditAction.DELETE)
        instance.delete()


class AdminBrandListCreateAPI(_ReferenceAdmin, generics.ListCreateAPIView):
    serializer_class = s.AdminBrandSerializer
    label = "براند"

    def get_queryset(self):
        queryset = Brand.objects.select_related("manufacturer").order_by("display_order", "name_ar")
        if search := self.request.query_params.get("search"):
            queryset = queryset.filter(Q(name_ar__icontains=search) | Q(name_en__icontains=search))
        return queryset

    def perform_create(self, serializer):
        self._audit(serializer.save(), AuditAction.CREATE)


class AdminBrandDetailAPI(_ReferenceAdmin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = s.AdminBrandSerializer
    queryset = Brand.objects.select_related("manufacturer")
    label = "براند"

    def perform_update(self, serializer):
        self._audit(serializer.save(), AuditAction.SETTING_CHANGE)

    def perform_destroy(self, instance):
        products = instance.products.count()
        if products:
            raise BusinessError(
                ErrorCode.CONFLICT,
                detail=f"لهذا البراند {products} منتجًا — أوقفه بدل حذفه",
                status_code=409,
            )

        self._audit(instance, AuditAction.DELETE)
        instance.delete()
