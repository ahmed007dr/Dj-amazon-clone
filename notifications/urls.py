"""مسارات الإشعارات — /api/v1/notifications/"""

from django.urls import path

from notifications import api

app_name = "notifications"

urlpatterns = [
    path("", api.NotificationListAPI.as_view(), name="list"),
    path("unread-count/", api.UnreadCountAPI.as_view(), name="unread-count"),
    path("<uuid:pk>/read/", api.MarkReadAPI.as_view(), name="mark-read"),
    path("read-all/", api.MarkAllReadAPI.as_view(), name="mark-all-read"),
    path("preferences/", api.PreferenceListAPI.as_view(), name="preferences"),
]
