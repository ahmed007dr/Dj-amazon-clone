"""مسارات نطاق العملاء — /api/v1/customers/"""

from django.urls import path

from customers import api

app_name = "customers"

urlpatterns = [
    path("me/", api.MyProfileAPI.as_view(), name="me"),
    # العناوين
    path("addresses/", api.AddressListCreateAPI.as_view(), name="addresses"),
    path("addresses/<uuid:pk>/", api.AddressDetailAPI.as_view(), name="address-detail"),
    path(
        "addresses/<uuid:pk>/set-default/",
        api.AddressSetDefaultAPI.as_view(),
        name="address-set-default",
    ),
    # الوثائق
    path("documents/", api.DocumentListCreateAPI.as_view(), name="documents"),
    path(
        "documents/<uuid:pk>/signed-url/",
        api.DocumentSignedUrlAPI.as_view(),
        name="document-signed-url",
    ),
    # التوقيع في المسار — لا معرّف الوثيقة
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
