"""
واجهات السلة.

⚠️  كل استجابة تمر بـ `revalidate()`.

    السلة تعيش أيامًا: المنتج قد يُوقَف والسعر يتغيّر والمخزون
    ينفد. إعادة العرض من البيانات المخزَّنة تعني عميلًا يرى حالة
    ماتت أمس.
"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from cart import serializers as s
from cart import services
from cart.models import CartLine
from catalog.models import Product, ProductVariant
from core.errors import BusinessError, ErrorCode

#: ترويسة سلة الزائر — قبل التسجيل
GUEST_HEADER = "HTTP_X_CART_SESSION"


class CartMixin:
    """
    ⚠️  الزائر يتسوّق قبل التسجيل.

        إجباره على إنشاء حساب أولًا يفقد المبيعة. السلة تُربط
        بمفتاح جلسة يرسله العميل، وتُدمج عند الدخول.
    """

    permission_classes = [AllowAny]

    def get_cart(self):
        request = self.request
        if request.user.is_authenticated:
            return services.get_active_cart(user=request.user)

        session_key = request.META.get(GUEST_HEADER, "").strip()
        if not session_key:
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR,
                detail="ترويسة X-Cart-Session مطلوبة لسلة الزائر",
            )
        return services.get_active_cart(session_key=session_key)

    def snapshot_response(self, cart, *, http_status=status.HTTP_200_OK):
        request = self.request
        snapshot = services.revalidate(
            cart,
            user=request.user if request.user.is_authenticated else None,
            governorate=request.query_params.get("governorate", ""),
            shipping_method_code=request.query_params.get("shipping_method", ""),
        )
        return Response(
            s.CartSnapshotSerializer(snapshot, context={"request": request}).data,
            status=http_status,
        )


class CartDetailAPI(CartMixin, APIView):
    def get(self, request):
        return self.snapshot_response(self.get_cart())

    def delete(self, request):
        cart = self.get_cart()
        services.clear(cart)
        return self.snapshot_response(cart)


class CartLinesAPI(CartMixin, APIView):
    serializer_class = s.AddLineSerializer

    def post(self, request):
        serializer = s.AddLineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        cart = self.get_cart()
        services.add_line(
            cart,
            get_object_or_404(Product, pk=data["product"]),
            data["quantity"],
            variant=(
                get_object_or_404(ProductVariant, pk=data["variant"])
                if data.get("variant")
                else None
            ),
            user=request.user if request.user.is_authenticated else None,
        )
        return self.snapshot_response(cart, http_status=status.HTTP_201_CREATED)


class CartLineDetailAPI(CartMixin, APIView):
    serializer_class = s.SetQuantitySerializer

    def _line(self, cart, pk) -> CartLine:
        # ⚠️  الفلترة بالسلة — لا سطر لغير صاحبه يصل هنا
        line = CartLine.objects.filter(pk=pk, cart=cart).first()
        if line is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)
        return line

    def patch(self, request, pk):
        serializer = s.SetQuantitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart = self.get_cart()
        services.set_quantity(cart, self._line(cart, pk), serializer.validated_data["quantity"])
        return self.snapshot_response(cart)

    def delete(self, request, pk):
        cart = self.get_cart()
        services.remove_line(cart, self._line(cart, pk))
        return self.snapshot_response(cart)


class CartCouponAPI(CartMixin, APIView):
    serializer_class = s.ApplyCouponSerializer

    def post(self, request):
        """
        ⚠️  الكوبون المرفوض يعيد `200` لا `400`.

            العميل يجرّب أكوادًا — الرفض حالة متوقعة لا خطأ.
            الاستجابة تحمل السبب في `coupon.reason` ليعرضه الفرونت.
        """
        serializer = s.ApplyCouponSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart = self.get_cart()
        # ⚠️  تُستخدم لقطة `apply_coupon` مباشرةً.
        #
        #     الكود المرفوض لا يُحفظ في السلة، فإعادة التحقق هنا
        #     تفقد سبب الرفض ويرى العميل خطأً عامًا بدل السبب.
        snapshot = services.apply_coupon(cart, serializer.validated_data["code"])
        return Response(s.CartSnapshotSerializer(snapshot, context={"request": request}).data)

    def delete(self, request):
        cart = self.get_cart()
        services.remove_coupon(cart)
        return self.snapshot_response(cart)


class CartBundleAPI(CartMixin, APIView):
    """
    إضافة حزمة دراسية.

    ⚠️  الاستجابة تحمل ما أُضيف **وما تعذّر**.

        صنف نافد من عشرة لا يمنع التسعة — والعميل يرى ما نقص.
    """

    serializer_class = s.AddBundleSerializer

    def post(self, request):
        from academic.models import StudyBundle

        serializer = s.AddBundleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        cart = self.get_cart()
        result = services.add_bundle(
            cart,
            get_object_or_404(StudyBundle, pk=data["bundle"], is_active=True),
            user=request.user if request.user.is_authenticated else None,
            essentials_only=data["essentials_only"],
        )

        snapshot = services.revalidate(
            cart, user=request.user if request.user.is_authenticated else None
        )
        return Response(
            {
                "bundle_result": result,
                "cart": s.CartSnapshotSerializer(snapshot, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )


class CartMergeAPI(APIView):
    """
    دمج سلة الزائر بعد الدخول.

    يُستدعى مرة واحدة من الفرونت عقب تسجيل الدخول الناجح.
    """

    def post(self, request):
        session_key = request.data.get("session_key", "").strip()
        if not session_key:
            raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="session_key مطلوب")

        cart = services.merge_guest_cart(request.user, session_key)
        snapshot = services.revalidate(cart, user=request.user)
        return Response(s.CartSnapshotSerializer(snapshot, context={"request": request}).data)
