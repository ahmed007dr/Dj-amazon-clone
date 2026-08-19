"""Staff portal routes — /api/v1/employees/"""

from django.urls import path

from employees import api

app_name = "employees"

urlpatterns = [
    # ── The employee portal — "me and my customers", no employee id ──
    path("me/", api.MyProfileAPI.as_view(), name="me"),
    path("dashboard/", api.MyDashboardAPI.as_view(), name="dashboard"),
    path("customers/", api.MyCustomersAPI.as_view(), name="customers"),
    path(
        "customers/<uuid:pk>/orders/",
        api.MyCustomerOrdersAPI.as_view(),
        name="customer-orders",
    ),
    path("orders/", api.CreateOrderForCustomerAPI.as_view(), name="create-order"),
    # ── Admin ──────────────────────────────────────────────
    path("admin/roles/", api.AdminRoleListCreateAPI.as_view(), name="admin-roles"),
    # ⚠️  Before `<uuid:pk>` deliberately: the literal precedes the variable.
    path(
        "admin/permissions/",
        api.AdminPermissionCatalogueAPI.as_view(),
        name="admin-permissions",
    ),
    path(
        "admin/roles/<uuid:pk>/",
        api.AdminRoleDetailAPI.as_view(),
        name="admin-role-detail",
    ),
    path("admin/staff/", api.AdminEmployeeListAPI.as_view(), name="admin-staff"),
    path("admin/staff/<uuid:pk>/", api.AdminEmployeeDetailAPI.as_view(), name="admin-staff-detail"),
    path(
        "admin/staff/<uuid:pk>/performance/",
        api.AdminEmployeePerformanceAPI.as_view(),
        name="admin-performance",
    ),
    path("admin/assignments/", api.AdminAssignmentListAPI.as_view(), name="admin-assignments"),
    path("admin/assignments/assign/", api.AdminAssignCustomerAPI.as_view(), name="admin-assign"),
    path(
        "admin/assignments/<uuid:pk>/end/",
        api.AdminEndAssignmentAPI.as_view(),
        name="admin-end-assignment",
    ),
    path(
        "admin/unassigned/",
        api.AdminUnassignedCustomersAPI.as_view(),
        name="admin-unassigned",
    ),
]
