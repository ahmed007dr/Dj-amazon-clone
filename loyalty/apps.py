from django.apps import AppConfig


class LoyaltyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "loyalty"
    verbose_name = "الولاء والإحالة"

    def ready(self):
        from loyalty import listeners  # noqa: F401
