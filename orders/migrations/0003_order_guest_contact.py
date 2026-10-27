from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Guest checkout: the contact details a buyer with no account leaves behind.

    Additive only — three blank-by-default columns and one partial unique index
    over a column that is blank on every existing row, so it cannot fail on
    production data and needs no backfill.
    """

    dependencies = [
        ("orders", "0002_alter_order_customer"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="checkout_key",
            field=models.CharField(
                blank=True,
                editable=False,
                max_length=64,
                verbose_name="مفتاح منع تكرار الطلب",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="claimed_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="تاريخ ربطه بحساب"
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="contact_email",
            field=models.EmailField(
                blank=True,
                db_index=True,
                help_text="بريد الزائر الذي يُرسَل إليه التأكيد ورابط التتبّع",
                max_length=254,
                verbose_name="بريد التواصل",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="contact_language",
            field=models.CharField(
                blank=True,
                help_text="لغة رسائل الزائر — لا حساب له يحمل تفضيلًا",
                max_length=5,
                verbose_name="لغة التواصل",
            ),
        ),
        migrations.AddConstraint(
            model_name="order",
            constraint=models.UniqueConstraint(
                condition=models.Q(("checkout_key__gt", ""), ("deleted_at__isnull", True)),
                fields=("checkout_key",),
                name="unique_order_checkout_key",
            ),
        ),
    ]
