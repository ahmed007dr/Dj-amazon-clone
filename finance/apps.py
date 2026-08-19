from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "finance"
    verbose_name = "المالية"

    def ready(self):
        # ⚠️  Imported here rather than at the top of the file.
        #
        #     The listeners touch the `orders` and `pos` models, and the app
        #     registry is not yet complete at module import time.
        from finance import listeners  # noqa: F401
