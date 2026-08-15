"""مسارات التقارير — /api/v1/reports/"""

from django.urls import path

from reporting import api

app_name = "reporting"

urlpatterns = [
    path("overview/", api.OverviewAPI.as_view(), name="overview"),
    path("sales/", api.SalesReportAPI.as_view(), name="sales"),
    path("inventory/", api.InventoryReportAPI.as_view(), name="inventory"),
    path("customers/", api.CustomersReportAPI.as_view(), name="customers"),
    path("performance/", api.PerformanceReportAPI.as_view(), name="performance"),
]
