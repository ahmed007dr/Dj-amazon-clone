"""
تشفير بيانات اعتماد البوابات المخزَّنة.

⚠️  خطوتان بالترتيب — والترتيب ليس تفصيلًا:

        ١. تبديل نوع الحقل  ← يفعّل التشفير على الكتابة والفكّ على القراءة
        ٢. إعادة حفظ الصفوف ← يحوّل ما كُتب قبل ذلك نصًّا صريحًا

    عكسهما يجعل الخطوة الثانية تقرأ وتكتب نصًّا صريحًا فلا تفعل شيئًا،
    وتبقى المفاتيح القديمة مكشوفة بينما يبدو الترحيل ناجحًا.

⚠️  والتحويل يمرّ عبر بايثون لا بـ `UPDATE` واحد — التشفير ليس دالة
    في قاعدة البيانات، والمفتاح لا يجوز أن يصلها أصلًا.
"""

import core.encryption
from django.db import migrations


def encrypt_existing(apps, schema_editor):
    """
    ⚠️  قابل لإعادة التشغيل: `encrypt` تعيد القيمة كما هي إن كانت
        تحمل علامة التشفير — فلا تشفير مزدوج لو أُعيد الترحيل.
    """
    Credential = apps.get_model("payments", "ProviderCredential")

    for credential in Credential.objects.all().iterator():
        # القراءة فكّت ما كان مشفّرًا وأبقت الصريح كما هو،
        # والحفظ يشفّر الاثنين.
        credential.save(update_fields=["value"])


def decrypt_existing(apps, schema_editor):
    """
    ⚠️  **التراجع يعيد المفاتيح نصًّا صريحًا إلى قاعدة البيانات.**

        موجود لأن ترحيلًا بلا عكس يحبس النشر، لا لأنه تصرّف عادي.
        من يشغّله يعيد الثغرة التي أُغلقت هنا — فليكن ذلك قرارًا
        صريحًا لا أثرًا جانبيًا لتراجع روتيني.

    ⚠️  والكتابة بـ SQL خام لا بـ ORM.

        حقل النموذج ما زال مشفَّرًا في هذه اللحظة (عكس العمليات
        يبدأ من الأسفل)، فأي `save` أو `update` يمرّ به يعيد
        التشفير — فينتهي «فكّ التشفير» بصفوف مشفّرة كما بدأت.
    """
    Credential = apps.get_model("payments", "ProviderCredential")
    table = Credential._meta.db_table

    with schema_editor.connection.cursor() as cursor:
        for credential in Credential.objects.all().iterator():
            cursor.execute(
                f"UPDATE {table} SET value = %s WHERE id = %s",  # noqa: S608
                [core.encryption.decrypt(credential.value), credential.pk],
            )


class Migration(migrations.Migration):
    dependencies = [
        ("payments", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="providercredential",
            name="value",
            field=core.encryption.EncryptedTextField(
                help_text="مشفّرة — لا تُقرأ عبر الـ API", verbose_name="القيمة"
            ),
        ),
        migrations.RunPython(encrypt_existing, decrypt_existing),
    ]
