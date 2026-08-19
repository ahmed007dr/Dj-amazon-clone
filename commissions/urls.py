"""Commission routes — /api/v1/commissions/"""

from django.urls import path

from commissions import api

app_name = "commissions"

urlpatterns = [
    path("me/", api.MyCommissionsAPI.as_view(), name="me"),
    path("me/<uuid:pk>/explain/", api.MyCommissionExplainAPI.as_view(), name="me-explain"),
    path("admin/schemes/", api.AdminSchemeListCreateAPI.as_view(), name="admin-schemes"),
    path("admin/", api.AdminCommissionListAPI.as_view(), name="admin-list"),
    path("admin/calculate/", api.AdminCalculateMonthAPI.as_view(), name="admin-calculate"),
    path(
        "admin/<uuid:pk>/decision/", api.AdminCommissionDecisionAPI.as_view(), name="admin-decision"
    ),
    path("admin/<uuid:pk>/explain/", api.AdminExplainAPI.as_view(), name="admin-explain"),
]
