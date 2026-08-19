"""Access policy routes — /api/v1/access/"""

from django.urls import path

from access import api

app_name = "access"

urlpatterns = [
    path("policies/", api.AccessPolicyListCreateAPI.as_view(), name="policies"),
    path("policies/<uuid:pk>/", api.AccessPolicyDetailAPI.as_view(), name="policy-detail"),
    path("matrix/", api.PolicyMatrixAPI.as_view(), name="matrix"),
    path("preview-status/", api.PreviewStatusAPI.as_view(), name="preview-status"),
]
