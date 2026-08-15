"""
صور المنتجات — الرفع والترتيب والحذف.

⚠️  **الفحص على توقيع الملف لا على ترويسته.**

    `core.files.validate_upload` يقرأ أول بايتات الملف. رفع
    `shell.php` بترويسة `image/png` كان يمرّ الفحص السطحي بالكامل.

⚠️  و«الصورة الرئيسية» واحدة لكل منتج — يفرضه قيد في قاعدة
    البيانات. تعيين ثانية يجب أن يُنزع الأولى في نفس المعاملة،
    وإلا رفض القيد العملية برسالة تكامل لا يفهمها أحد.
"""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Product, ProductImage
from catalog.serializers import ProductImageSerializer
from core.errors import BusinessError, ErrorCode
from core.models.audit import AuditAction, AuditLog
from core.permissions import IsAdminAccount

#: ⚠️  حد أعلى لعدد الصور.
#:
#:     منتج بمئة صورة يجعل صفحته تُحمّل عشرات الميجابايت على هاتف،
#:     ويجعل استعلام القائمة يجرّ صفوفًا لا تُعرض. ثمانية تكفي لأي
#:     منتج طبي.
MAX_IMAGES_PER_PRODUCT = 8


class ProductImageListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [IsAdminAccount]
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
                detail=_("الحد الأقصى {count} صور لكل منتج").format(
                    count=MAX_IMAGES_PER_PRODUCT
                ),
                status_code=409,
            )

        # ⚠️  أول صورة تصير الرئيسية تلقائيًا.
        #
        #     منتج بصور بلا رئيسية يظهر بلا صورة في كل قائمة —
        #     والأدمن يرى صوره مرفوعة فلا يفهم السبب.
        is_first = existing == 0

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
    permission_classes = [IsAdminAccount]
    serializer_class = ProductImageSerializer
    lookup_url_kwarg = "image_pk"

    def get_queryset(self):
        # ⚠️  مُصفّى بالمنتج — لا تُحذف صورة منتج آخر بتخمين معرّفها
        return ProductImage.objects.filter(product_id=self.kwargs["pk"])

    @transaction.atomic
    def perform_destroy(self, instance):
        """
        ⚠️  حذف الصورة الرئيسية يرقّي التالية.

            تركه يجعل المنتج بلا صورة رئيسية رغم امتلاكه صورًا،
            فيختفي من كل قائمة بصريًا بلا سبب ظاهر.
        """
        was_primary = instance.is_primary
        product_id = instance.product_id
        instance.delete()

        if was_primary:
            replacement = (
                ProductImage.objects.filter(product_id=product_id)
                .order_by("display_order")
                .first()
            )
            if replacement is not None:
                replacement.is_primary = True
                replacement.save(update_fields=["is_primary"])


class SetPrimaryImageAPI(APIView):
    """
    تعيين الصورة الرئيسية.

    ⚠️  النزع والتعيين في **معاملة واحدة**.

        القيد الفريد يمنع صورتين رئيسيتين؛ والتعيين قبل النزع
        يرفضه بخطأ تكامل خام يظهر للأدمن كـ ٥٠٠.
    """

    permission_classes = [IsAdminAccount]

    @transaction.atomic
    def post(self, request, pk, image_pk):
        image = get_object_or_404(ProductImage, pk=image_pk, product_id=pk)

        ProductImage.objects.filter(product_id=pk, is_primary=True).exclude(
            pk=image.pk
        ).update(is_primary=False)

        image.is_primary = True
        image.save(update_fields=["is_primary"])

        return Response(ProductImageSerializer(image).data)


class ReorderImagesAPI(APIView):
    """
    إعادة ترتيب صور المنتج.

    ⚠️  الترتيب يحدد ما يظهر في المعرض أولًا بعد الرئيسية — وهو
        قرار عرض لا تفصيل تقني.
    """

    permission_classes = [IsAdminAccount]

    @transaction.atomic
    def post(self, request, pk):
        order = request.data.get("order")

        if not isinstance(order, list) or not order:
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR, detail=_("أرسل `order` كقائمة معرّفات")
            )

        owned = set(
            ProductImage.objects.filter(product_id=pk).values_list("id", flat=True)
        )

        for index, image_id in enumerate(order):
            # ⚠️  التصفية بالمنتج داخل الحلقة: معرّف صورة منتج آخر
            #     كان سيعيد ترتيبها من هنا.
            ProductImage.objects.filter(pk=image_id, product_id=pk).update(
                display_order=index * 10
            )

        unknown = [str(image_id) for image_id in order if str(image_id) not in map(str, owned)]
        if unknown:
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR,
                detail=_("معرّفات لا تخصّ هذا المنتج: {ids}").format(ids=", ".join(unknown)),
            )

        return Response(
            ProductImageSerializer(
                ProductImage.objects.filter(product_id=pk).order_by("display_order"),
                many=True,
            ).data,
            status=status.HTTP_200_OK,
        )
