"""Admin panel for the academic domain."""

from django.contrib import admin

from academic.models import (
    BundleItem,
    Department,
    Faculty,
    StudentProfile,
    StudyBundle,
    University,
)
from core.admin import DeletedListFilter, DomainModelAdmin, SlugAdminMixin


class FacultyInline(admin.TabularInline):
    model = Faculty
    extra = 0
    fields = ("name_ar", "name_en", "code", "years_count", "is_active")
    show_change_link = True


class DepartmentInline(admin.TabularInline):
    model = Department
    extra = 0
    fields = ("name_ar", "name_en", "code", "is_active")
    show_change_link = True


class BundleItemInline(admin.TabularInline):
    model = BundleItem
    extra = 0
    fields = ("product", "variant", "quantity", "is_essential", "display_order")
    autocomplete_fields = ("product", "variant")
    show_change_link = True


@admin.register(University)
class UniversityAdmin(SlugAdminMixin, DomainModelAdmin):
    list_display = ("code", "name_ar", "city", "governorate", "is_active", "is_deleted")
    list_filter = ("governorate", "is_active", DeletedListFilter)
    search_fields = ("code", "name_ar", "name_en", "city")
    ordering = ("name_ar",)
    inlines = (FacultyInline,)


@admin.register(Faculty)
class FacultyAdmin(SlugAdminMixin, DomainModelAdmin):
    list_display = ("name_ar", "university", "code", "years_count", "is_active", "is_deleted")
    list_filter = ("university", "is_active", DeletedListFilter)
    list_select_related = ("university",)
    search_fields = ("code", "name_ar", "name_en", "university__name_ar")
    autocomplete_fields = ("university",)
    inlines = (DepartmentInline,)


@admin.register(Department)
class DepartmentAdmin(SlugAdminMixin, DomainModelAdmin):
    list_display = ("name_ar", "faculty", "code", "is_active", "is_deleted")
    list_filter = ("faculty__university", "is_active", DeletedListFilter)
    list_select_related = ("faculty",)
    search_fields = ("code", "name_ar", "name_en", "faculty__name_ar")
    autocomplete_fields = ("faculty",)


@admin.register(StudentProfile)
class StudentProfileAdmin(DomainModelAdmin):
    list_display = (
        "user",
        "university",
        "faculty",
        "academic_year",
        "student_number",
        "is_verified",
        "is_deleted",
    )
    list_filter = ("is_verified", "academic_year", "university", DeletedListFilter)
    list_select_related = ("user", "university", "faculty", "department")
    search_fields = ("user__email", "student_number", "faculty__name_ar")
    autocomplete_fields = ("user", "university", "faculty", "department")
    date_hierarchy = "created_at"


@admin.register(StudyBundle)
class StudyBundleAdmin(SlugAdminMixin, DomainModelAdmin):
    list_display = (
        "name_ar",
        "faculty",
        "department",
        "academic_year",
        "kind",
        "display_order",
        "is_active",
        "is_deleted",
    )
    list_filter = ("kind", "academic_year", "faculty", "is_active", DeletedListFilter)
    list_select_related = ("faculty", "department")
    search_fields = ("name_ar", "name_en", "faculty__name_ar")
    autocomplete_fields = ("faculty", "department")
    inlines = (BundleItemInline,)


@admin.register(BundleItem)
class BundleItemAdmin(DomainModelAdmin):
    list_display = ("bundle", "product", "variant", "quantity", "is_essential", "is_deleted")
    list_filter = ("is_essential", "bundle__faculty", DeletedListFilter)
    list_select_related = ("bundle", "product", "variant")
    search_fields = ("bundle__name_ar", "product__name_ar", "product__sku")
    autocomplete_fields = ("bundle", "product", "variant")
