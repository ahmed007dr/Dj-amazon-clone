from django.apps import AppConfig


class PricingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pricing"

    def ready(self):
        # ⚠️  `pricing` registers itself with `catalog`; `catalog` never imports `pricing`.
        #     Same inversion as `inventory`'s stock filter — see `core/color_facts.py`.
        from core.color_facts import register_color_facts
        from pricing.color_prices import color_price_facts

        register_color_facts("pricing.color_price", color_price_facts)

        # The same inversion for the product card and page: what *this viewer* pays.
        from core.price_facts import register_price_provider
        from pricing.catalog_prices import listing_price_facts

        register_price_provider("pricing.listing", listing_price_facts)
