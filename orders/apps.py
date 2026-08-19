from django.apps import AppConfig


class OrdersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "orders"

    def ready(self):
        # ⚠️  Imported here rather than at the top of the file — the listeners touch
        #     the `orders` and `payments` models, and the app registry is not yet
        #     complete at module import time.
        from orders import listeners  # noqa: F401
