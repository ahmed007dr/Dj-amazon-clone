"""
`backfill_product_colors` — proposes colours from free-text variant attributes.

⚠️  Dry run by default: nothing is guessed silently, and applying it creates no
    variant (stock, carts and order history keep pointing where they did).
"""

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from catalog.models import ProductColor, ProductVariant
from catalog.tests.color_support import add_color, make_product


@pytest.fixture
def legacy(db):
    product = make_product("LEG-1")
    for sku, size, color in (
        ("LEG-1-M-BLU", "M", "Blue"),
        ("LEG-1-L-BLU", "L", " blue "),
        ("LEG-1-M-GRN", "M", "أخضر"),
        ("LEG-1-M-NONE", "M", ""),
    ):
        ProductVariant.objects.create(
            product=product,
            sku=sku,
            name_ar=sku,
            name_en=sku,
            attributes={"size": size, "color": color} if color else {"size": size},
            price_adjustment=Decimal("0.00"),
        )
    return product


def run(*args):
    out = StringIO()
    call_command("backfill_product_colors", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
class TestBackfill:
    def test_the_default_is_a_dry_run(self, legacy):
        output = run()

        assert "LEG-1" in output and "--apply" in output
        assert not ProductColor.objects.exists()
        assert not ProductVariant.objects.filter(color__isnull=False).exists()

    def test_apply_links_the_existing_variants_and_creates_none(self, legacy):
        before = ProductVariant.objects.count()

        run("--apply")

        assert ProductVariant.objects.count() == before
        blue = ProductColor.objects.get(product=legacy, name_en="Blue")
        assert set(blue.variants.values_list("sku", flat=True)) == {"LEG-1-M-BLU", "LEG-1-L-BLU"}
        assert blue.hex == "#1E40AF"
        green = ProductColor.objects.get(product=legacy, name_ar="أخضر")
        assert green.hex == "#15803D"
        assert ProductVariant.objects.get(sku="LEG-1-M-NONE").color_id is None

    def test_it_is_idempotent(self, legacy):
        run("--apply")
        run("--apply")

        assert ProductColor.objects.filter(product=legacy).count() == 2

    def test_an_unknown_colour_gets_the_neutral_grey(self, db):
        product = make_product("LEG-2")
        ProductVariant.objects.create(
            product=product, sku="LEG-2-X", name_ar="x", name_en="x", attributes={"color": "Mauve"}
        )

        run("--apply")

        assert ProductColor.objects.get(product=product).hex == "#9CA3AF"

    def test_a_sku_filter_limits_the_scope(self, legacy):
        other = make_product("LEG-3")
        ProductVariant.objects.create(
            product=other, sku="LEG-3-X", name_ar="x", name_en="x", attributes={"color": "Red"}
        )

        run("--apply", "--sku", "LEG-3")

        assert ProductColor.objects.filter(product=other).count() == 1
        assert not ProductColor.objects.filter(product=legacy).exists()

    def test_an_existing_colour_is_reused_not_duplicated(self, legacy):
        add_color(legacy, "Blue")

        run("--apply")

        assert ProductColor.objects.filter(product=legacy, name_en="Blue").count() == 1
