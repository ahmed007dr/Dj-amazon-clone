from django.apps import AppConfig


class AcademicConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "academic"

    def ready(self):
        # Registers the receiver that mirrors the account's verification
        from academic import signals  # noqa: F401
