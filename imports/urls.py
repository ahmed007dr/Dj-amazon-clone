"""Bulk import routes — /api/v1/imports/"""

from django.urls import path

from imports import api

app_name = "imports"

urlpatterns = [
    # ── The template and the guide behind it ───────────────
    path("template/", api.ImportTemplateAPI.as_view(), name="template"),
    path("spec/", api.ImportSpecAPI.as_view(), name="spec"),
    # ── Jobs ───────────────────────────────────────────────
    path("jobs/", api.ImportJobListCreateAPI.as_view(), name="jobs"),
    path("jobs/<uuid:pk>/", api.ImportJobDetailAPI.as_view(), name="job-detail"),
    # ── The lifecycle: validate → execute → advance → publish ──
    #
    # ⚠️  `advance` serves both the dry run and the execution deliberately.
    #     Two loops would be two places to get the resume logic wrong, and the
    #     frontend would need to know which one it is driving — which it does not.
    path("jobs/<uuid:pk>/validate/", api.ValidateImportAPI.as_view(), name="job-validate"),
    path("jobs/<uuid:pk>/execute/", api.ExecuteImportAPI.as_view(), name="job-execute"),
    path("jobs/<uuid:pk>/advance/", api.AdvanceImportAPI.as_view(), name="job-advance"),
    path("jobs/<uuid:pk>/cancel/", api.CancelImportAPI.as_view(), name="job-cancel"),
    path("jobs/<uuid:pk>/publish/", api.PublishImportAPI.as_view(), name="job-publish"),
    # ── The report ─────────────────────────────────────────
    path("jobs/<uuid:pk>/errors/", api.ImportErrorListAPI.as_view(), name="job-errors"),
    path("jobs/<uuid:pk>/errors/file/", api.ImportErrorFileAPI.as_view(), name="job-error-file"),
]
