"""
Fill `created_by` / `updated_by` on products that predate the audit columns.

    python manage.py backfill_product_audit [--dry-run]

⚠️  Best effort, and only from evidence that already exists: the legacy
    `AuditLog` CREATE row whose text is `منتج <sku>`. A product with no such row
    (seeded, imported, created in the Django panel) is left NULL and the admin
    table shows "—" — guessing an author is worse than showing none.

⚠️  Never overwrites a value that is already set, so it is safe to re-run.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import Product
from core.models.audit import AuditAction, AuditLog


class Command(BaseCommand):
    help = "Backfill Product.created_by / updated_by from legacy audit CREATE entries."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report only, write nothing.")

    def handle(self, *args, dry_run=False, **options):
        filled = 0
        queryset = Product.all_objects.filter(created_by__isnull=True).only("id", "sku")

        with transaction.atomic():
            for product in queryset.iterator(chunk_size=500):
                creator_id = (
                    AuditLog.objects.filter(
                        action=AuditAction.CREATE,
                        object_repr=f"منتج {product.sku}",
                        actor__isnull=False,
                    )
                    .order_by("created_at")
                    .values_list("actor_id", flat=True)
                    .first()
                )
                if creator_id is None:
                    continue

                filled += 1
                if not dry_run:
                    Product.all_objects.filter(pk=product.pk).update(created_by_id=creator_id)
                    Product.all_objects.filter(pk=product.pk, updated_by__isnull=True).update(
                        updated_by_id=creator_id
                    )

            if dry_run:
                transaction.set_rollback(True)

        verb = "would be filled" if dry_run else "filled"
        self.stdout.write(self.style.SUCCESS(f"{filled} product(s) {verb}."))
