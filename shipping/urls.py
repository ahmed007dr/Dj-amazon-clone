"""Shipping routes — /api/v1/shipping/"""

from django.urls import path

from shipping import api

app_name = "shipping"

urlpatterns = [
    path("quote/", api.ShippingQuoteAPI.as_view(), name="quote"),
    path("methods/", api.ShippingMethodListAPI.as_view(), name="methods"),
    # Tracking by number rather than by id — the number gets shared and the response carries no
    # personal data
    path("track/<str:number>/", api.TrackShipmentAPI.as_view(), name="track"),
    path("admin/shipments/", api.AdminShipmentListAPI.as_view(), name="admin-shipments"),
    path(
        "admin/shipments/<uuid:pk>/transition/",
        api.AdminTransitionShipmentAPI.as_view(),
        name="admin-transition",
    ),
    # ── Configuration ──────────────────────────────────────
    #
    # ⚠️  The fee table used to be editable from the Django panel alone — which
    #     means whoever sets the delivery price had to be handed the whole
    #     database to do it. These routes put the same table behind the shipping
    #     permission, where the person who runs the deliveries already is.
    path("admin/coverage/", api.ShippingCoverageAPI.as_view(), name="admin-coverage"),
    path("admin/zones/", api.AdminZoneListCreateAPI.as_view(), name="admin-zones"),
    path("admin/zones/<uuid:pk>/", api.AdminZoneDetailAPI.as_view(), name="admin-zone-detail"),
    path("admin/methods/", api.AdminMethodListCreateAPI.as_view(), name="admin-methods"),
    path(
        "admin/methods/<uuid:pk>/",
        api.AdminMethodDetailAPI.as_view(),
        name="admin-method-detail",
    ),
    path("admin/rates/", api.AdminRateListCreateAPI.as_view(), name="admin-rates"),
    path("admin/rates/<uuid:pk>/", api.AdminRateDetailAPI.as_view(), name="admin-rate-detail"),
]
