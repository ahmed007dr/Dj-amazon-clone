"""Academic domain routes — /api/v1/academic/"""

from django.urls import path

from academic import api

app_name = "academic"

urlpatterns = [
    # Public — a student picks their university before creating an account
    path("universities/", api.UniversityTreeAPI.as_view(), name="universities"),
    path("bundles/<slug:slug>/", api.BundleDetailAPI.as_view(), name="bundle-detail"),
    # Student
    path("me/", api.MyStudentProfileAPI.as_view(), name="me"),
    path("me/bundles/", api.MyBundlesAPI.as_view(), name="my-bundles"),
    # Admin
    path("admin/students/", api.AdminStudentListAPI.as_view(), name="admin-students"),
    path(
        "admin/faculties/<uuid:pk>/promote/",
        api.AdminPromoteStudentsAPI.as_view(),
        name="admin-promote",
    ),
]

# ═══════════════════════════════════════════════════════════
#  Admin — the academic tree and bundles
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  The tree is **a precondition for registering any student**: they pick
#      their university and faculty before creating an account.

urlpatterns += [
    path(
        "admin/universities/",
        api.AdminUniversityListCreateAPI.as_view(),
        name="admin-universities",
    ),
    path(
        "admin/universities/<uuid:pk>/",
        api.AdminUniversityDetailAPI.as_view(),
        name="admin-university-detail",
    ),
    path("admin/faculties/", api.AdminFacultyListCreateAPI.as_view(), name="admin-faculties"),
    path(
        "admin/faculties/<uuid:pk>/",
        api.AdminFacultyDetailAPI.as_view(),
        name="admin-faculty-detail",
    ),
    path(
        "admin/departments/",
        api.AdminDepartmentListCreateAPI.as_view(),
        name="admin-departments",
    ),
    path(
        "admin/departments/<uuid:pk>/",
        api.AdminDepartmentDetailAPI.as_view(),
        name="admin-department-detail",
    ),
    path("admin/bundles/", api.AdminBundleListCreateAPI.as_view(), name="admin-bundles"),
    path(
        "admin/bundles/<uuid:pk>/",
        api.AdminBundleDetailAPI.as_view(),
        name="admin-bundle-detail",
    ),
    # Bundle items — filtering by their bundle is mandatory
    path(
        "admin/bundles/<uuid:pk>/items/",
        api.AdminBundleItemListCreateAPI.as_view(),
        name="admin-bundle-items",
    ),
    path(
        "admin/bundles/<uuid:pk>/items/<uuid:item_pk>/",
        api.AdminBundleItemDetailAPI.as_view(),
        name="admin-bundle-item-detail",
    ),
]
