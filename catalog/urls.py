"""مسارات الكتالوج — /api/v1/catalog/"""

from django.urls import path

from catalog import api, image_api

app_name = "catalog"

urlpatterns = [
    # المنتجات — عام. المعرّف slug لا UUID (ADR-27)
    path("products/", api.ProductListAPI.as_view(), name="products"),
    path("products/<slug:slug>/", api.ProductDetailAPI.as_view(), name="product-detail"),
    path(
        "barcode/<str:barcode>/",
        api.ProductByBarcodeAPI.as_view(),
        name="product-by-barcode",
    ),
    # التصنيف
    path("categories/", api.CategoryTreeAPI.as_view(), name="categories"),
    path("categories/<slug:slug>/", api.CategoryDetailAPI.as_view(), name="category-detail"),
    # البراندات والمصنّعون
    path("brands/", api.BrandListAPI.as_view(), name="brands"),
    path("brands/<slug:slug>/", api.BrandDetailAPI.as_view(), name="brand-detail"),
    path("manufacturers/", api.ManufacturerListAPI.as_view(), name="manufacturers"),
    # الأدمن — بلا فلترة سياسات
    # خيارات نموذج الإنشاء — نداء واحد يملأ كل القوائم المنسدلة
    path(
        "admin/products/options/",
        api.ProductFormOptionsAPI.as_view(),
        name="admin-product-options",
    ),
    path("admin/products/", api.AdminProductListCreateAPI.as_view(), name="admin-products"),
    path(
        "admin/products/<uuid:pk>/",
        api.AdminProductDetailAPI.as_view(),
        name="admin-product-detail",
    ),
    path(
        "admin/products/<uuid:pk>/restore/",
        api.RestoreProductAPI.as_view(),
        name="admin-product-restore",
    ),
    # صور المنتج — الرفع والترتيب والحذف
    path(
        "admin/products/<uuid:pk>/images/",
        image_api.ProductImageListCreateAPI.as_view(),
        name="admin-product-images",
    ),
    path(
        "admin/products/<uuid:pk>/images/reorder/",
        image_api.ReorderImagesAPI.as_view(),
        name="admin-product-images-reorder",
    ),
    path(
        "admin/products/<uuid:pk>/images/<uuid:image_pk>/",
        image_api.ProductImageDetailAPI.as_view(),
        name="admin-product-image-detail",
    ),
    path(
        "admin/products/<uuid:pk>/images/<uuid:image_pk>/primary/",
        image_api.SetPrimaryImageAPI.as_view(),
        name="admin-product-image-primary",
    ),
]
