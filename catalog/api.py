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
                | Q(barcode__iexact=search)
            )

        # ⚠️  `is_active` هو ما ترسله الواجهة.
        #
        #     كان الخادم يقرأ `inactive` وحده، فيمرّ فلتر الحالة
        #     بلا أثر: الشاشة تعرض «مفعّل» والنتائج تشمل الموقوف.
        #     الفلتر الذي لا يفلتر أسوأ من غيابه — لأنه يُصدَّق.
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

        AuditLog.objects.create(
            actor=self.request.user,
            action=AuditAction.DELETE,
            object_repr=f"منتج {instance.sku}",
            changes={"name_ar": instance.name_ar, "soft": True},
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )


class RestoreProductAPI(APIView):
    """
    إرجاع منتج محذوف ناعمًا.

    ⚠️  الحذف الناعم بلا استرجاع حذفٌ نهائي من منظور المستخدم.

        الصف باقٍ في قاعدة البيانات، لكن إعادته كانت تحتاج مطوّرًا
        أو لوحة Django — وأول سؤال بعد حذف بالخطأ هو «كيف أرجعه؟».
    """

    permission_classes = [IsAdminAccount]

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
    كل ما تحتاجه شاشة إنشاء منتج — في نداء واحد.

    ⚠️  **القوائم من الخادم لا مكرّرة في الواجهة.**

        تثبيت الأشكال الدوائية أو التصنيفات التنظيمية في كود
        الواجهة يجعل إضافة قيمة في الخادم لا تظهر للأدمن، وحذفها
        يترك خيارًا يفشل عند الحفظ. المصدر واحد.

    ⚠️  و**الفئات مسطّحة بمسارها الكامل** لا شجرة.

        قائمة اختيار لا تعرض شجرة؛ و«أقراص» وحدها غامضة حين توجد
        تحت «أدوية» و«مكمّلات» معًا. المسار يحسم أيّهما.

    ⚠️  وتشمل الفئات غير الظاهرة في القائمة العامة.

        نقطة الفئات العامة تُصفّي بـ `show_in_menu`، وهو تصنيف
        **عرضي** لا تصنيف صلاحية: فئة مخفية عن قائمة المتجر تبقى
        فئة صالحة لمنتج. الاعتماد عليها هنا كان يمنع الأدمن من
        اختيار فئات موجودة.

    ⚠️  و`access_policies` **جزء من النموذج لا إعداد متقدّم**.

        هي جواب السؤال «مَن يرى هذا المنتج؟» — عام أم طلاب أم
        مهنيون موثّقون أم صيدليات. حذفها من شاشة الإنشاء يجعل كل
        منتج جديد يرث الافتراضية بصمت: دواء مقيّد يُنشر للجميع،
        ولا يُكتشف إلا حين يشتريه من لا يحقّ له.
    """

    permission_classes = [IsAdminAccount]

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
                # ⚠️  عبر `access.services` لا `access.models` — الواجهة
                #     العامة لكل نطاق هي خدماته.
                "access_policies": [
                    {
                        "id": str(policy.id),
                        "code": policy.code,
                        "name_ar": policy.name_ar,
                        "name_en": policy.name_en,
                        "level": policy.level,
                        "is_default": policy.is_default,
                        # ⚠️  الشرطان يُعرضان مع الاسم: «مهنيون موثّقون»
                        #     وحدها لا تقول إن الطبيب غير الموثّق ممنوع.
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
    ⚠️  التسمية العربية من `TextChoices` لا من قاموس في الواجهة —
        فلا يوجد موضعان يختلفان في تسمية نفس القيمة.
    """
    return [{"value": value, "label": str(label)} for value, label in choices_class.choices]


def _flat_categories() -> list[dict]:
    """الفئات النشطة مسطّحة، ولكل واحدة مسارها المقروء."""
    categories = list(Category.objects.filter(is_active=True).order_by("path", "display_order"))
    names = {category.pk: category for category in categories}

    def label(category) -> str:
        parts, node, guard = [], category, 0
        # ⚠️  حارس العمق: مسار تالف بأب يشير إلى نفسه يعلّق الطلب
        #     إلى الأبد بلا أثر في أي سجل.
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
#  الأدمن — التصنيف المرجعي
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  الحذف في الثلاثة **يُرفض عند الاستعمال** لا يُنفَّذ بصمت.
#
#      العلاقات `PROTECT` تمنعه في قاعدة البيانات أصلًا، لكن الخطأ
#      يصل عندها كانهيار ٥٠٠ لا كرسالة. الفحص هنا يحوّله إلى «هذه
#      الفئة بها ١٢ منتجًا» — وهو ما يحتاجه الأدمن ليقرّر.


class _ReferenceAdmin:
    """الأساس المشترك: صلاحية الأدمن، وبلا ترقيم، وتسجيل تدقيق."""

    permission_classes = [IsAdminAccount]
    pagination_class = None

    #: يظهر في سجل التدقيق
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
    ⚠️  مسطّحة لا شجرة — والترتيب بالمسار يجعلها تُقرأ كشجرة.

        الشجرة المتداخلة تحتاج تسطيحًا في الواجهة لكل قائمة اختيار،
        والمسار (`path`) يعطي الترتيب الشجري مجانًا.

    ⚠️  وتشمل غير الظاهرة في القائمة العامة: `show_in_menu` تصنيف
        **عرضي** لا صلاحية.
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
        ⚠️  الفئة المستعمَلة لا تُحذف — والرسالة **تعدّ** ما يمنعها.

            «لا يمكن الحذف» وحدها تجعل الأدمن يبحث عن السبب بالتجربة.
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
