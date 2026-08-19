"""
Pricing routes — /api/v1/pricing/

⚠️  **All of them under `admin/` and all of them for the admin.**

    The price reaches the customer already computed inside the product, the cart
    and the order; there is no public endpoint here. Exposing the price lists
    hands a competitor your entire pricing structure.
"""

from django.urls import path

from pricing import api

app_name = "pricing"

urlpatterns = [
    # Price lists
    path("admin/lists/", api.PriceListListCreateAPI.as_view(), name="lists"),
    path("admin/lists/<uuid:pk>/", api.PriceListDetailAPI.as_view(), name="list-detail"),
    # Pricing rules — a product's price in a list at a minimum quantity
    path("admin/rules/", api.PriceRuleListCreateAPI.as_view(), name="rules"),
    path("admin/rules/<uuid:pk>/", api.PriceRuleDetailAPI.as_view(), name="rule-detail"),
    # Promotional discounts — they appear in the catalogue with no code
    path("admin/overrides/", api.PriceOverrideListCreateAPI.as_view(), name="overrides"),
    path(
        "admin/overrides/<uuid:pk>/",
        api.PriceOverrideDetailAPI.as_view(),
        name="override-detail",
    ),
]
