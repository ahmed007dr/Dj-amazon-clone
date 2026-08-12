"""مسارات الكتالوج — /api/v1/catalog/"""

from django.urls import path

from catalog import api

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
    path("admin/products/", api.AdminProductListCreateAPI.as_view(), name="admin-products"),
    path(
        "admin/products/<uuid:pk>/",
        api.AdminProductDetailAPI.as_view(),
        name="admin-product-detail",
    ),
]
