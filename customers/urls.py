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
    # Admin — reviewing verification documents (`CanManageAcademic`)
    path("admin/documents/", api.AdminDocumentListAPI.as_view(), name="admin-documents"),
    path(
        "admin/documents/counts/",
        api.AdminDocumentCountsAPI.as_view(),
        name="admin-document-counts",
    ),
    path(
        "admin/documents/bulk-approve/",
        api.AdminDocumentBulkApproveAPI.as_view(),
        name="admin-document-bulk-approve",
    ),
    path(
        "admin/documents/<uuid:pk>/file/",
        api.AdminDocumentFileAPI.as_view(),
        name="admin-document-file",
    ),
    path(
        "admin/documents/<uuid:pk>/approve/",
        api.AdminDocumentApproveAPI.as_view(),
        name="admin-document-approve",
    ),
    path(
        "admin/documents/<uuid:pk>/reject/",
        api.AdminDocumentRejectAPI.as_view(),
        name="admin-document-reject",
    ),
    # Admin — deciding a student without a document (`CanManageAcademic`)
    path(
        "admin/students/<uuid:user_id>/verify/",
        api.AdminStudentVerifyAPI.as_view(),
        name="admin-student-verify",
    ),
    path(
        "admin/students/<uuid:user_id>/reject/",
        api.AdminStudentRejectAPI.as_view(),
        name="admin-student-reject",
    ),
]
