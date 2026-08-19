from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "notifications"

    def ready(self):
        # ⚠️  The listeners are wired here rather than at ordinary import time.
        #     `notifications` listens and is never called — and wiring in `ready`
        #     guarantees every domain is loaded before the listeners are registered.
        from notifications import listeners  # noqa: F401
