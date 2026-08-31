from django.apps import AppConfig


class InventoryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "inventory"

    def ready(self):
        # ⚠️  Imported here rather than at the top of the file — the filter builds a
        #     queryset over `Stock`, and the app registry is not complete at module
        #     import time.
        from core.visibility import register_product_filter
        from inventory.services import IN_STOCK_FILTER, in_stock_filter

        # ⚠️  **`inventory` registers itself with `catalog`; `catalog` never asks for
        #     `inventory`.**
        #
        #     The layer contract puts `inventory` above `catalog`, so the catalogue
        #     cannot import the stock table to hide what has run out. Registering the
        #     filter from this side inverts the direction the way `payments.events`
        #     does one layer up — see the full reasoning in `core/visibility.py`.
        register_product_filter(IN_STOCK_FILTER, in_stock_filter)
