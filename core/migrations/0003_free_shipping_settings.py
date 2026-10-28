from django.db import migrations

ENABLED_KEY = "free_shipping_enabled"
THRESHOLD_KEY = "free_shipping_threshold"

ROWS = [
    {
        "key": ENABLED_KEY,
        "value": False,
        "value_type": "BOOL",
        "label_ar": "تفعيل الشحن المجاني فوق مبلغ معيّن",
        "label_en": "Free shipping above an amount",
        "help_text_ar": (
            "مُطفأ: يُحتسب الشحن بتعريفة المنطقة كالمعتاد. "
            "مُشغَّل: يصبح الشحن مجانيًا للطرق المؤهَّلة متى بلغ إجمالي المنتجات "
            "(بعد الخصومات وقبل الضريبة والشحن) الحدّ المحدَّد."
        ),
        "help_text_en": (
            "Off: shipping is charged at the zone rate as usual. On: eligible methods "
            "ship free once the products total (after discounts, before tax and "
            "shipping) reaches the threshold."
        ),
    },
    {
        "key": THRESHOLD_KEY,
        # A string, not a float: it is read back through `Decimal(str(...))`
        "value": "0.00",
        "value_type": "DECIMAL",
        "label_ar": "حدّ الشحن المجاني (بالجنيه)",
        "label_en": "Free shipping threshold (EGP)",
        "help_text_ar": "إجمالي المنتجات الذي يبدأ منه الشحن المجاني. لا يعمل إلا مع تفعيل الخيار أعلاه.",
        "help_text_en": (
            "The products total from which shipping is free. Only applies while the "
            "switch above is on."
        ),
    },
]


def create_settings(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    for row in ROWS:
        defaults = {k: v for k, v in row.items() if k != "key"}
        # ⚠️  get_or_create: re-running or restoring must never reset a rule the owner turned on.
        SystemSetting.objects.get_or_create(
            key=row["key"],
            defaults={**defaults, "group": "orders", "is_editable": True},
        )


def remove_settings(apps, schema_editor):
    apps.get_model("core", "SystemSetting").objects.filter(
        key__in=[ENABLED_KEY, THRESHOLD_KEY]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0002_student_verification_switch")]

    operations = [migrations.RunPython(create_settings, remove_settings)]
