"""Reporting routes — /api/v1/reports/"""

from django.urls import path

from reporting import api
from reporting.export import api as export_api

app_name = "reporting"

urlpatterns = [
    path("overview/", api.OverviewAPI.as_view(), name="overview"),
    path("sales/", api.SalesReportAPI.as_view(), name="sales"),
    path("inventory/", api.InventoryReportAPI.as_view(), name="inventory"),
    path("customers/", api.CustomersReportAPI.as_view(), name="customers"),
    path("performance/", api.PerformanceReportAPI.as_view(), name="performance"),
    path("peak-hours/", api.PeakHoursAPI.as_view(), name="peak-hours"),
    # ── Row-level export ───────────────────────────────────
    # ⚠️  Under `reports/` rather than in a domain, because one screen must list
    #     stock beside customers beside revenue — and no single domain owns that
    #     list. `reporting` already reads every domain and writes to none, which
    #     is exactly what an export is.
    path("exports/", export_api.ExportCatalogueAPI.as_view(), name="exports"),
    path("exports/<slug:key>/", export_api.ExportDownloadAPI.as_view(), name="export-download"),
]
