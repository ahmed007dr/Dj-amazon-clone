from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = _("البنية التحتية")

    def ready(self):
        # ⚠️  Imported here rather than at the top of the file — registering the checks
        #     reads settings, and reading them before the apps are ready freezes values
        #     that are not yet complete.
        from core import checks  # noqa: F401
