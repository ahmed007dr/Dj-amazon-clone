from django.apps import AppConfig


class EmployeesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "employees"
    verbose_name = "الموظفون"

    def ready(self):
        from employees import signals  # noqa: F401
