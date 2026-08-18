"""مسارات حركة الاستخدام — /api/v1/analytics/"""

from django.urls import path

from analytics import api

app_name = "analytics"

urlpatterns = [
    path("live/", api.LiveAPI.as_view(), name="live"),
    path("traffic/", api.TrafficAPI.as_view(), name="traffic"),
    path("peak-hours/", api.TrafficPeakHoursAPI.as_view(), name="peak-hours"),
]
