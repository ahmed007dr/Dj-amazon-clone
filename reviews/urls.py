"""مسارات التقييمات — /api/v1/reviews/"""

from django.urls import path

from reviews import api

app_name = "reviews"

urlpatterns = [
    # عام — بالـ slug مثل الكتالوج
    path(
        "products/<slug:slug>/",
        api.ProductReviewListAPI.as_view(),
        name="product-reviews",
    ),
    path(
        "products/<slug:slug>/rating/",
        api.ProductRatingAPI.as_view(),
        name="product-rating",
    ),
    # تقييماتي
    path("mine/", api.MyReviewListCreateAPI.as_view(), name="mine"),
    path("mine/<uuid:pk>/", api.MyReviewDetailAPI.as_view(), name="mine-detail"),
    path("<uuid:pk>/helpful/", api.ReviewHelpfulAPI.as_view(), name="helpful"),
    # الأدمن
    path("admin/", api.AdminReviewListAPI.as_view(), name="admin-reviews"),
    path("admin/<uuid:pk>/moderate/", api.ModerateReviewAPI.as_view(), name="moderate"),
]
