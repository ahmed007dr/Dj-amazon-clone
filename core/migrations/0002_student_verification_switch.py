from django.db import migrations

KEY = "student_verification_enforced"


def create_switch(apps, schema_editor):
    SystemSetting = apps.get_model("core", "SystemSetting")
    # ⚠️  get_or_create: re-running or restoring must never reset a switch the owner turned on.
    SystemSetting.objects.get_or_create(
        key=KEY,
        defaults={
            "value": False,
            "value_type": "BOOL",
            "group": "general",
            "label_ar": "جعل توثيق الطلاب إلزاميًا",
            "label_en": "Make student verification mandatory",
            "help_text_ar": (
                "مُطفأ: لا تظهر رسائل «قيد التوثيق» وأسعار الطلاب تُطبَّق حسب نوع الحساب. "
                "مُشغَّل: تعود الرسائل ويُشترط اعتماد الكارنيه لسعر الطلاب."
            ),
            "help_text_en": (
                "Off: no 'pending verification' notices and student prices follow the "
                "account type. On: notices return and an approved ID is required."
            ),
            "is_editable": True,
        },
    )


def remove_switch(apps, schema_editor):
    apps.get_model("core", "SystemSetting").objects.filter(key=KEY).delete()


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]

    operations = [migrations.RunPython(create_switch, remove_switch)]
