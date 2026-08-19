"""Catalogue routes — /api/v1/catalog/"""

from django.urls import path

from catalog import api, image_api

app_name = "catalog"

urlpatterns = [
    # Products — public. The identifier is the slug, not a UUID (ADR-27)
    path("products/", api.ProductListAPI.as_view(), name="products"),
    path("products/<slug:slug>/", api.ProductDetailAPI.as_view(), name="product-detail"),
    path(
        "barcode/<str:barcode>/",
        api.ProductByBarcodeAPI.as_view(),
        name="product-by-barcode",
    ),
    # Classification
    path("categories/", api.CategoryTreeAPI.as_view(), name="categories"),
    path("categories/<slug:slug>/", api.CategoryDetailAPI.as_view(), name="category-detail"),
    # Brands and manufacturers
    path("brands/", api.BrandListAPI.as_view(), name="brands"),
    path("brands/<slug:slug>/", api.BrandDetailAPI.as_view(), name="brand-detail"),
    path("manufacturers/", api.ManufacturerListAPI.as_view(), name="manufacturers"),
    # Admin — no policy filtering
    # ── Reference classification — a precondition for adding any product ──
    # ⚠️  The category is mandatory on `Product`; a store with no categories
    #     screen cannot add its first item from its panel.
    path("admin/categories/", api.AdminCategoryListCreateAPI.as_view(), name="admin-categories"),
    path(
        "admin/categories/<uuid:pk>/",
        api.AdminCategoryDetailAPI.as_view(),
        name="admin-category-detail",
    ),
    path("admin/brands/", api.AdminBrandListCreateAPI.as_view(), name="admin-brands"),
    path(
        "admin/brands/<uuid:pk>/",
        api.AdminBrandDetailAPI.as_view(),
        name="admin-brand-detail",
    ),
    path(
        "admin/manufacturers/",
        api.AdminManufacturerListCreateAPI.as_view(),
        name="admin-manufacturers",
    ),
    path(
        "admin/manufacturers/<uuid:pk>/",
        api.AdminManufacturerDetailAPI.as_view(),
        name="admin-manufacturer-detail",
    ),
    # Creation form options — one call fills every dropdown
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
    # Product images — upload, ordering and deletion
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
