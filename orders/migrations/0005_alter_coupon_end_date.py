# Generated by Django 4.2 on 2024-01-24 18:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0004_rename_quatity_cartdetails_quantity_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='coupon',
            name='end_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
