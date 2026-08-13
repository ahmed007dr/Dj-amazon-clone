"""مسارات المخزون — /api/v1/inventory/"""

from django.urls import path

from inventory import api

app_name = "inventory"

urlpatterns = [
    # عام — التوفر فقط، بلا كشف الأرقام الدقيقة
    path("availability/", api.AvailabilityAPI.as_view(), name="availability"),
    # المواقع
    path("locations/", api.StockLocationListCreateAPI.as_view(), name="locations"),
    path("locations/<uuid:pk>/", api.StockLocationDetailAPI.as_view(), name="location-detail"),
    # الأرصدة والدفعات
    path("stock/", api.StockListAPI.as_view(), name="stock"),
    path("stock/<int:pk>/", api.StockDetailAPI.as_view(), name="stock-detail"),
    path("batches/", api.BatchListAPI.as_view(), name="batches"),
    # السجل والتنبيهات
    path("movements/", api.StockMovementListAPI.as_view(), name="movements"),
    path("alerts/", api.StockAlertListAPI.as_view(), name="alerts"),
    path("reservations/", api.ReservationListAPI.as_view(), name="reservations"),
    # الأوامر
    path("receive/", api.ReceiveStockAPI.as_view(), name="receive"),
    path("adjust/", api.AdjustStockAPI.as_view(), name="adjust"),
    path("transfer/", api.TransferStockAPI.as_view(), name="transfer"),
    path("damage/", api.MarkDamagedAPI.as_view(), name="damage"),
    path("maintenance/", api.RunMaintenanceAPI.as_view(), name="maintenance"),
]
