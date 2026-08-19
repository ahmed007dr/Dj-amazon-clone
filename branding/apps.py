from django.apps import AppConfig


class BrandingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "branding"
    verbose_name = "الهوية البصرية"

    def ready(self):
        # ⚠️  Cache invalidation by signal, not by a manual call.
        #
        #     The identity is edited from four paths: the admin API · the Django
        #     panel · the seed · the shell. A manual call means any forgotten path
        #     leaves the site on stale colours for up to half a day, with no error
        #     and no trace — and the signal covers all of them with no upkeep.
        from branding import signals  # noqa: F401
