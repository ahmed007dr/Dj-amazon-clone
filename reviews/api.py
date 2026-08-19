"""
واجهات التقييمات.
"""

from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.pagination import AdminPageNumberPagination
from core.errors import BusinessError, ErrorCode
from core.permissions import CanModerateReviews
from reviews import serializers as s
from reviews import services
from reviews.models import ProductRating, Review, ReviewStatus


class ProductReviewListAPI(generics.ListAPIView):
    """
    تقييمات منتج — **المنشورة فقط**.

    ⚠️  المعلّقة والمرفوضة لا تظهر لأحد غير صاحبها والأدمن.
    """

    permission_classes = [AllowAny]
    serializer_class = s.ReviewSerializer

    def get_queryset(self):
        return (
            Review.objects.filter(product__slug=self.kwargs["slug"], status=ReviewStatus.APPROVED)
            .select_related("user")
            .order_by("-helpful_count", "-created_at")
        )


class ProductRatingAPI(APIView):
    """التجميع — من الجدول المُخزَّن لا من حساب لحظي."""

    permission_classes = [AllowAny]

    def get(self, request, slug):
        rating = ProductRating.objects.filter(product__slug=slug).first()

        if rating is None:
            return Response({"average": "0.00", "count": 0, "distribution": {}})

        return Response(
            {
                "average": str(rating.average),
                "count": rating.count,
                "distribution": rating.distribution,
            }
        )


class MyReviewListCreateAPI(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return s.ReviewWriteSerializer
        return s.ReviewSerializer

    def get_queryset(self):
        # ⚠️  الفلترة بالمالك — لا تقييمات الغير
        return Review.objects.filter(user=self.request.user).select_related("product", "user")

    def perform_create(self, serializer):
        review = serializer.save(user=self.request.user, status=ReviewStatus.PENDING)
        # لا إعادة حساب — التقييم المعلّق لا يدخل المتوسط
        return review


class MyReviewDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = s.ReviewWriteSerializer

    def get_queryset(self):
        return Review.objects.filter(user=self.request.user)

    def perform_update(self, serializer):
        """
        ⚠️  تعديل تقييم منشور يعيده إلى المراجعة.

        بدونها يكتب المستخدم نصًا لائقًا، يُعتمد، ثم يستبدله بما
        شاء — والمراجعة تصير بلا معنى.
        """
        review = serializer.save(status=ReviewStatus.PENDING)
        services.recalculate_rating(review.product_id)

    def perform_destroy(self, instance):
        product_id = instance.product_id
        instance.delete()
        services.recalculate_rating(product_id)


class ReviewHelpfulAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        review = Review.objects.filter(pk=pk, status=ReviewStatus.APPROVED).first()
        if review is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        if review.user_id == request.user.pk:
            raise BusinessError(
                ErrorCode.PERMISSION_DENIED,
                detail="لا يمكنك التصويت على تقييمك",
                status_code=403,
            )

        review, voted = services.toggle_helpful(review, request.user)
        return Response({"voted": voted, "helpful_count": review.helpful_count})


# ═══════════════════════════════════════════════════════════
#  الأدمن
# ═══════════════════════════════════════════════════════════


class AdminReviewListAPI(generics.ListAPIView):
    permission_classes = [CanModerateReviews]
    serializer_class = s.AdminReviewSerializer
    pagination_class = AdminPageNumberPagination

    def get_queryset(self):
        queryset = Review.objects.select_related("user", "product")

        if status_filter := self.request.query_params.get("status"):
            queryset = queryset.filter(status=status_filter)
        if product := self.request.query_params.get("product"):
            queryset = queryset.filter(product_id=product)

        return queryset.order_by("-created_at")


class ModerateReviewAPI(APIView):
    permission_classes = [CanModerateReviews]
    serializer_class = s.ModerateReviewSerializer

    def post(self, request, pk):
        serializer = s.ModerateReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        review = Review.objects.filter(pk=pk).first()
        if review is None:
            raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

        review = services.moderate(
            review,
            approved=serializer.validated_data["approved"],
            moderator=request.user,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(s.AdminReviewSerializer(review).data)
