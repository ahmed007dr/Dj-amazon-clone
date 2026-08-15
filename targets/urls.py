"""مسارات الأهداف — /api/v1/targets/"""

from django.urls import path

from targets import api

app_name = "targets"

urlpatterns = [
    path("me/", api.MyTargetAPI.as_view(), name="me"),
    path("admin/", api.AdminTargetListCreateAPI.as_view(), name="admin-list"),
    path("admin/bulk/", api.AdminBulkTargetsAPI.as_view(), name="admin-bulk"),
    path("admin/<uuid:pk>/", api.AdminTargetDetailAPI.as_view(), name="admin-detail"),
    path("admin/<uuid:pk>/activate/", api.AdminActivateTargetAPI.as_view(), name="admin-activate"),
    path("admin/<uuid:pk>/close/", api.AdminCloseTargetAPI.as_view(), name="admin-close"),
]
