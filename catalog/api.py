"""
واجهات الكتالوج.

⚠️  كل قائمة عامة تمر بـ `PolicyAwareQuerySetMixin`.

    المنتج المقيّد لا يظهر في النتائج ولا في العدد ولا يُفتح
    بالرابط المباشر — والفلترة في الـ queryset لا في الـ serializer.
"""

from django.db.models import Q
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from access.preview import PreviewAwareMixin
from access.services import PolicyAwareQuerySetMixin
from catalog import selectors
from catalog import serializers as s
from catalog.models import Brand, Category, Manufacturer, Product
from core.api.pagination import AdminPageNumberPagination
from core.permissions import IsAdminAccount


class PublicCatalogMixin(PreviewAwareMixin, PolicyAwareQuerySetMixin):
    """
    الأساس المشترك لكل نقطة عامة في الكتالوج.

    ترتيب الوراثة مقصود: `PreviewAwareMixin` أولًا ليتجاوز
    `get_access_user`، ثم `PolicyAwareQuerySetMixin` الذي يستدعيها.
    """

    permission_classes = [AllowAny]
    policy_field = "access_policy"


# ═══════════════════════════════════════════════════════════
#  المنتجات — عام
# ═══════════════════════════════════════════════════════════


class ProductListAPI(PublicCatalogMixin, generics.ListAPIView):
    serializer_class = s.ProductListSerializer

    def get_base_queryset(self):
        # ⚠️  `get_base_queryset` لا `get_queryset` —
        #     تجاوز الثاني يعطّل فلترة السياسات بصمت.
        queryset = selectors.product_base_queryset().filter(is_active=True)
        params = self.request.query_params

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
    ⚠️  المعرّف `slug` لا UUID — صفحة المنتج تحتاج SEO. (ADR-27)

        والمقيّد يعيد `404` لا `403`: الفارق بينهما يكشف قائمة
        المنتجات المقيّدة بمسح الروابط.
    """

    serializer_class = s.ProductDetailSerializer
    lookup_field = "slug"

    def get_base_queryset(self):
        return selectors.product_detail_queryset().filter(is_active=True)


class ProductByBarcodeAPI(PublicCatalogMixin, generics.RetrieveAPIView):
    """
    بحث بالباركود — لماسح نقطة البيع.

    نقطة منفصلة لأن المسار يختلف والاستجابة أخف.
    """

    serializer_class = s.ProductDetailSerializer
    lookup_field = "barcode"

    def get_base_queryset(self):
        return selectors.product_detail_queryset().filter(is_active=True)


# ═══════════════════════════════════════════════════════════
#  التصنيف والبراندات
# ═══════════════════════════════════════════════════════════


class CategoryTreeAPI(APIView):
    """
    شجرة القائمة كاملة.

    ⚠️  استعلام واحد ثم بناء الشجرة في الذاكرة.
        بناؤها بالاستعلامات = استعلام لكل عقدة.
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
#  الأدمن
# ═══════════════════════════════════════════════════════════


class AdminProductListCreateAPI(generics.ListCreateAPIView):
    """
    ⚠️  **بلا فلترة سياسات** — الأدمن يدير كل المنتجات بما فيها
        المقيّدة. لهذا لا يرث `PublicCatalogMixin`.
    """

    permission_classes = [IsAdminAccount]
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
            )
        if params.get("inactive") == "true":
            queryset = queryset.filter(is_active=False)

        return queryset.order_by("-created_at")


class AdminProductDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminAccount]
    serializer_class = s.AdminProductSerializer
    queryset = Product.all_objects.all()

    def perform_destroy(self, instance):
        """
        حذف ناعم دائمًا.

        ⚠️  المنتج المباع تشير إليه طلبات تاريخية وحركات مخزون —
            حذفه فعليًا يكسر كل تقرير ماضٍ.
        """
        instance.delete()
