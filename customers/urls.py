"""Customer domain routes — /api/v1/customers/"""

from django.urls import path

from customers import api

app_name = "customers"

urlpatterns = [
    path("me/", api.MyProfileAPI.as_view(), name="me"),
    # Addresses
    path("addresses/", api.AddressListCreateAPI.as_view(), name="addresses"),
    path("addresses/<uuid:pk>/", api.AddressDetailAPI.as_view(), name="address-detail"),
    path(
        "addresses/<uuid:pk>/set-default/",
        api.AddressSetDefaultAPI.as_view(),
        name="address-set-default",
    ),
    # Documents
    path("documents/", api.DocumentListCreateAPI.as_view(), name="documents"),
    path(
        "documents/<uuid:pk>/signed-url/",
        api.DocumentSignedUrlAPI.as_view(),
        name="document-signed-url",
    ),
    # The signature is in the path — not the document id
    path(
        "documents/download/<str:signature>/",
        api.DocumentDownloadAPI.as_view(),
        name="document-download",
    ),
    path(
        "documents/<uuid:pk>/",
        api.DocumentDeleteAPI.as_view(),
        name="document-delete",
    ),
]
