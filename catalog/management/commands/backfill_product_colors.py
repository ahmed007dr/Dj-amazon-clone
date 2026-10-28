"""
Propose — and optionally create — product colours from variants that already say
their colour in free text.

    python manage.py backfill_product_colors              # a dry run: prints the plan
    python manage.py backfill_product_colors --apply      # creates the colours, links the variants
    python manage.py backfill_product_colors --sku SCR-SET

⚠️  **Dry run by default, and never run implicitly by a migration.**

    Variants imported before colours existed carry `attributes={"color": "blue"}` —
    free text typed by whoever made the sheet ("blue", "Blue ", "أزرق"). Turning
    that into a `ProductColor` attaches a swatch, a gallery and possibly a price to a
    string match, so a person looks at the plan first. Nothing is guessed silently.

What `--apply` does, per product and per distinct colour text:

  * creates one `ProductColor` (names from the text, a hex from a small table of
    common names — grey `#9CA3AF` when unknown, to be fixed in the panel);
  * **links the product's existing variants** of that colour to it. It creates no new
    variant, so stock, carts and order history are untouched.

Variants that already have a colour, and products whose colour text is empty, are left
alone. Re-running is safe: a colour that already exists by name is reused.
"""

from __future__ import annotations

from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import ProductColor, ProductVariant

#: Common colour names → `#RRGGBB`. Anything else gets the neutral default.
KNOWN_HEX = {
    "blue": "#1E40AF",
    "أزرق": "#1E40AF",
    "navy": "#1E3A5F",
    "كحلي": "#1E3A5F",
    "green": "#15803D",
    "أخضر": "#15803D",
    "red": "#B91C1C",
    "أحمر": "#B91C1C",
    "white": "#FFFFFF",
    "أبيض": "#FFFFFF",
    "black": "#111827",
    "أسود": "#111827",
    "grey": "#6B7280",
    "gray": "#6B7280",
    "رمادي": "#6B7280",
    "pink": "#DB2777",
    "وردي": "#DB2777",
    "purple": "#7E22CE",
    "بنفسجي": "#7E22CE",
    "teal": "#0F766E",
    "yellow": "#CA8A04",
    "أصفر": "#CA8A04",
    "orange": "#EA580C",
    "برتقالي": "#EA580C",
    "brown": "#92400E",
    "بني": "#92400E",
}

DEFAULT_HEX = "#9CA3AF"


def _key(text: str) -> str:
    return " ".join(str(text).split()).casefold()


def plan(queryset=None) -> list[dict]:
    """
    The proposed colours: `[{product, name, variants: [...], hex}]`, one per product
    and distinct colour text. Pure reading — used by both the dry run and `--apply`.
    """
    variants = (
        queryset
        if queryset is not None
        else ProductVariant.objects.filter(color__isnull=True).select_related("product")
    )

    groups: dict[tuple, dict] = {}
    for variant in variants.order_by("product__sku", "display_order", "sku"):
        text = str((variant.attributes or {}).get("color") or "").strip()
        if not text:
            continue
        group = groups.setdefault(
            (variant.product_id, _key(text)),
            {"product": variant.product, "spellings": Counter(), "variants": []},
        )
        group["spellings"][" ".join(text.split())] += 1
        group["variants"].append(variant)

    proposals = []
    for group in groups.values():
        # The spelling most variants use; on a tie the capitalised one ("Blue" over "blue")
        spellings = group["spellings"]
        name = max(spellings, key=lambda text: (spellings[text], text[:1].isupper()))
        proposals.append(
            {
                "product": group["product"],
                "variants": group["variants"],
                "name": name,
                # No translation is guessed: both names start as the text typed, and the
                # admin corrects the other language in the panel.
                "name_ar": name,
                "name_en": name,
                "hex": KNOWN_HEX.get(_key(name), DEFAULT_HEX),
            }
        )
    return proposals


@transaction.atomic
def apply_plan(proposals: list[dict]) -> dict:
    created = linked = reused = 0
    for proposal in proposals:
        product = proposal["product"]
        color = (
            ProductColor.objects.filter(
                product=product, name_en__iexact=proposal["name_en"]
            ).first()
            or ProductColor.objects.filter(
                product=product, name_ar__iexact=proposal["name_ar"]
            ).first()
        )

        if color is None:
            orders = ProductColor.objects.filter(product=product).values_list(
                "display_order", flat=True
            )
            top = max(orders, default=-10)
            color = ProductColor.objects.create(
                product=product,
                name_ar=proposal["name_ar"],
                name_en=proposal["name_en"],
                hex=proposal["hex"],
                display_order=top + 10,
            )
            created += 1
        else:
            reused += 1

        for variant in proposal["variants"]:
            variant.color = color
            variant.save(update_fields=["color", "updated_at"])
            linked += 1

    return {"created": created, "reused": reused, "linked": linked}


class Command(BaseCommand):
    help = "Propose (and with --apply, create) product colours from variants' free-text colour."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true", help="Create the colours and link the variants."
        )
        parser.add_argument("--sku", help="Only this product's SKU.")

    def handle(self, *args, **options):
        variants = ProductVariant.objects.filter(color__isnull=True).select_related("product")
        if options.get("sku"):
            variants = variants.filter(product__sku=options["sku"])

        proposals = plan(variants)
        if not proposals:
            self.stdout.write("لا ألوان مقترحة — لا نسخ بخاصية color حرّة بلا لون مرتبط.")
            return

        for proposal in proposals:
            skus = ", ".join(variant.sku for variant in proposal["variants"])
            self.stdout.write(
                f"{proposal['product'].sku:<14} {proposal['name']:<14} "
                f"{proposal['hex']}  ← {skus}"
            )

        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING(
                    f"\nتشغيل تجريبي: {len(proposals)} لون مقترح. أضف --apply للإنشاء."
                )
            )
            return

        result = apply_plan(proposals)
        self.stdout.write(
            self.style.SUCCESS(
                f"أُنشئ {result['created']} لون · أُعيد استخدام {result['reused']} · "
                f"رُبطت {result['linked']} نسخة."
            )
        )
