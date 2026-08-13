"""مسارات النطاق الأكاديمي — /api/v1/academic/"""

from django.urls import path

from academic import api

app_name = "academic"

urlpatterns = [
    # عام — الطالب يختار جامعته قبل إنشاء الحساب
    path("universities/", api.UniversityTreeAPI.as_view(), name="universities"),
    path("bundles/<slug:slug>/", api.BundleDetailAPI.as_view(), name="bundle-detail"),
    # الطالب
    path("me/", api.MyStudentProfileAPI.as_view(), name="me"),
    path("me/bundles/", api.MyBundlesAPI.as_view(), name="my-bundles"),
    # الأدمن
    path("admin/students/", api.AdminStudentListAPI.as_view(), name="admin-students"),
    path(
        "admin/faculties/<uuid:pk>/promote/",
        api.AdminPromoteStudentsAPI.as_view(),
        name="admin-promote",
    ),
]
