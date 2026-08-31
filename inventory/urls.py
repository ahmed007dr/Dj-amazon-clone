"""Inventory routes — /api/v1/inventory/"""

from django.urls import path

from inventory import api

app_name = "inventory"

urlpatterns = [
    # Public — availability only, without exposing exact figures
    path("availability/", api.AvailabilityAPI.as_view(), name="availability"),
    # Locations
    path("locations/", api.StockLocationListCreateAPI.as_view(), name="locations"),
    path("locations/<uuid:pk>/", api.StockLocationDetailAPI.as_view(), name="location-detail"),
    # Balances and batches
    path("stock/", api.StockListAPI.as_view(), name="stock"),
    # ⚠️  Beside the balances, not inside them: `stock/` lists rows and these
    #     products have none — see `UnstockedProductListAPI`.
    path("unstocked/", api.UnstockedProductListAPI.as_view(), name="unstocked"),
    path("stock/<int:pk>/", api.StockDetailAPI.as_view(), name="stock-detail"),
    path("batches/", api.BatchListAPI.as_view(), name="batches"),
    # The log and alerts
    path("movements/", api.StockMovementListAPI.as_view(), name="movements"),
    path("alerts/", api.StockAlertListAPI.as_view(), name="alerts"),
    path("reservations/", api.ReservationListAPI.as_view(), name="reservations"),
    # Commands
    path("receive/", api.ReceiveStockAPI.as_view(), name="receive"),
    path("adjust/", api.AdjustStockAPI.as_view(), name="adjust"),
    path("transfer/", api.TransferStockAPI.as_view(), name="transfer"),
    path("damage/", api.MarkDamagedAPI.as_view(), name="damage"),
    path("maintenance/", api.RunMaintenanceAPI.as_view(), name="maintenance"),
    # ── Stock counting ─────────────────────────────────────
    path("counts/", api.StockCountListAPI.as_view(), name="counts"),
    path("counts/open/", api.OpenStockCountAPI.as_view(), name="count-open"),
    path("counts/<uuid:pk>/", api.StockCountDetailAPI.as_view(), name="count-detail"),
    path("counts/<uuid:pk>/record/", api.RecordCountedAPI.as_view(), name="count-record"),
    path("counts/<uuid:pk>/apply/", api.ApplyStockCountAPI.as_view(), name="count-apply"),
    path("counts/<uuid:pk>/cancel/", api.CancelStockCountAPI.as_view(), name="count-cancel"),
]
