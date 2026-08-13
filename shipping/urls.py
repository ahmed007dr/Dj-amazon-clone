"""مسارات الشحن — /api/v1/shipping/"""

from django.urls import path

from shipping import api

app_name = "shipping"

urlpatterns = [
    path("quote/", api.ShippingQuoteAPI.as_view(), name="quote"),
    path("methods/", api.ShippingMethodListAPI.as_view(), name="methods"),
    # التتبع بالرقم لا بالمعرّف — الرقم يُشارَك والاستجابة بلا بيانات شخصية
    path("track/<str:number>/", api.TrackShipmentAPI.as_view(), name="track"),
    path("admin/shipments/", api.AdminShipmentListAPI.as_view(), name="admin-shipments"),
    path(
        "admin/shipments/<uuid:pk>/transition/",
        api.AdminTransitionShipmentAPI.as_view(),
        name="admin-transition",
    ),
]
