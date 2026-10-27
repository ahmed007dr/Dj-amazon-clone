from django.db import migrations, models
from django.utils import timezone


def merge_duplicate_active_guest_carts(apps, schema_editor):
    """
    Make the new constraint impossible to violate by existing rows.

    ⚠️  Before this migration nothing stopped two ACTIVE carts sharing a guest
        key (a double-tapped first request created both). Adding the unique
        index over them would fail the deploy — so the duplicates are folded
        into the most recently used one first: lines are summed (the same
        arithmetic `merge_guest_cart` uses) and the losers are marked MERGED,
        never deleted, so no history is lost.
    """
    Cart = apps.get_model("cart", "Cart")
    CartLine = apps.get_model("cart", "CartLine")

    keys = (
        Cart.objects.filter(status="ACTIVE", deleted_at__isnull=True, session_key__gt="")
        .values("session_key")
        .annotate(n=models.Count("id"))
        .filter(n__gt=1)
        .values_list("session_key", flat=True)
    )

    for key in list(keys):
        carts = list(
            Cart.objects.filter(
                session_key=key, status="ACTIVE", deleted_at__isnull=True
            ).order_by("-last_activity_at", "-created_at")
        )
        winner, losers = carts[0], carts[1:]

        for loser in losers:
            for line in CartLine.objects.filter(cart=loser, deleted_at__isnull=True):
                existing = CartLine.objects.filter(
                    cart=winner,
                    product_id=line.product_id,
                    variant_id=line.variant_id,
                    deleted_at__isnull=True,
                ).first()
                if existing is None:
                    line.cart_id = winner.pk
                    line.save(update_fields=["cart"])
                else:
                    existing.quantity += line.quantity
                    existing.save(update_fields=["quantity"])

            loser.status = "MERGED"
            loser.save(update_fields=["status"])

        winner.last_activity_at = timezone.now()
        winner.save(update_fields=["last_activity_at"])


class Migration(migrations.Migration):
    # ⚠️  Not atomic: on PostgreSQL, updating rows that carry deferred foreign-key
    #     checks and then building an index on the same table inside one
    #     transaction can fail with "pending trigger events". Each step commits on
    #     its own instead — and the data step is idempotent (a second run finds no
    #     duplicates), so a failure between the two is simply re-run.
    atomic = False

    dependencies = [
        ("cart", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(merge_duplicate_active_guest_carts, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="cart",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("deleted_at__isnull", True), ("session_key__gt", ""), ("status", "ACTIVE")
                ),
                fields=("session_key",),
                name="unique_active_cart_per_session",
            ),
        ),
    ]
