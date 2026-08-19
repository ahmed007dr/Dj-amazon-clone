"""Shipping routes — /api/v1/shipping/"""

from django.urls import path

from shipping import api

app_name = "shipping"

urlpatterns = [
    path("quote/", api.ShippingQuoteAPI.as_view(), name="quote"),
    path("methods/", api.ShippingMethodListAPI.as_view(), name="methods"),
    # Tracking by number rather than by id — the number gets shared and the response carries no personal data
    path("track/<str:number>/", api.TrackShipmentAPI.as_view(), name="track"),
    path("admin/shipments/", api.AdminShipmentListAPI.as_view(), name="admin-shipments"),
    path(
        "admin/shipments/<uuid:pk>/transition/",
        api.AdminTransitionShipmentAPI.as_view(),
        name="admin-transition",
    ),
]
