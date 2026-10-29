"""
Cart endpoints.

⚠️  Every response passes through `revalidate()`.

    A cart lives for days: the product may be discontinued, the price may
    change, the stock may run out. Re-rendering from stored data means a
    customer looking at a state that died yesterday.
"""

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from cart import serializers as s
from cart import services
from cart.models import CartLine
from cart.throttles import CouponApplyThrottle
from catalog.models import Product, ProductVariant
from core.errors import BusinessError, ErrorCode

#: The guest cart header — before registration
GUEST_HEADER = "HTTP_X_CART_SESSION"


class CartMixin:
    """
    ⚠️  A visitor shops before registering.

        Forcing them to create an account first loses the sale. The cart is tied
        to a session key the client sends, and merged on login.
    """

    permission_classes = [AllowAny]

    def get_cart(self):
        request = self.request
        if request.user.is_authenticated:
            return services.get_active_cart(user=request.user)

        # ⚠️  Validated, not trusted: it is client input that becomes a database
        #     value (a UUID in its canonical spelling, or a 400).
        session_key = services.normalise_session_key(request.META.get(GUEST_HEADER, ""))
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
                get_object_or_404(
                    ProductVariant.objects.select_related("color"), pk=data["variant"]
                )
                if data.get("variant")
                else None
            ),
            user=request.user if request.user.is_authenticated else None,
        )
        return self.snapshot_response(cart, http_status=status.HTTP_201_CREATED)


class CartLineDetailAPI(CartMixin, APIView):
    serializer_class = s.SetQuantitySerializer

    def _line(self, cart, pk) -> CartLine:
        # ⚠️  Filtered by cart — no line belonging to someone else reaches here
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
    # ⚠️  Visitors may use coupons, so the box is open to anyone: the project-wide throttles
    #     stay (setting this attribute replaces the defaults) and one more bounds code guessing.
    throttle_classes = [AnonRateThrottle, UserRateThrottle, CouponApplyThrottle]

    def post(self, request):
        """
        ⚠️  A rejected coupon returns `200`, not `400`.

            The customer is trying codes — rejection is an expected state, not
            an error. The response carries the reason in `coupon.reason` for the
            frontend to display.
        """
        serializer = s.ApplyCouponSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart = self.get_cart()
        # ⚠️  The `apply_coupon` snapshot is used directly.
        #
        #     A rejected code is not saved on the cart, so re-validating here
        #     loses the rejection reason and the customer sees a generic error instead.
        snapshot = services.apply_coupon(cart, serializer.validated_data["code"])
        return Response(s.CartSnapshotSerializer(snapshot, context={"request": request}).data)

    def delete(self, request):
        cart = self.get_cart()
        services.remove_coupon(cart)
        return self.snapshot_response(cart)


class CartBundleAPI(CartMixin, APIView):
    """
    Add a study bundle.

    ⚠️  The response carries what was added **and what could not be**.

        One item out of ten being out of stock does not block the other nine —
        and the customer sees what is missing.
    """

    serializer_class = s.AddBundleSerializer

    # ⚠️  **A bundle needs an account** (owner decision) — a visitor may *see*
    #     every bundle, but adding one to the cart means signing in first.
    #     `CartMixin` allows anyone; this overrides it, and `add_bundle` refuses
    #     a missing user again below it so a future caller cannot skip the gate.
    permission_classes = [IsAuthenticated]

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
    Merge the guest cart after login.

    Called once from the frontend following a successful login.
    """

    def post(self, request):
        session_key = request.data.get("session_key", "")
        if not session_key:
            raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="session_key مطلوب")

        cart = services.merge_guest_cart(request.user, services.normalise_session_key(session_key))
        snapshot = services.revalidate(cart, user=request.user)
        return Response(s.CartSnapshotSerializer(snapshot, context={"request": request}).data)
