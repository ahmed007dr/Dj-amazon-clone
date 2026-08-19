"""
Encrypting the stored gateway credentials.

⚠️  Two steps in order — and the order is not a detail:

        1. change the field type   ← enables encryption on write and decryption on read
        2. re-save the rows        ← converts what was written as plaintext before that

    Reversing them makes the second step read and write plaintext, so it does
    nothing, and the old keys stay exposed while the migration appears to have succeeded.

⚠️  And the conversion goes through Python rather than a single `UPDATE` —
    encryption is not a database function, and the key must never reach it at all.
"""

import core.encryption
from django.db import migrations


def encrypt_existing(apps, schema_editor):
    """
    ⚠️  Re-runnable: `encrypt` returns the value unchanged if it already carries
        the encryption marker — so there is no double encryption if the
        migration is re-run.
    """
    Credential = apps.get_model("payments", "ProviderCredential")

    for credential in Credential.objects.all().iterator():
        # The read decrypted whatever was encrypted and left the plaintext as it was,
        # and the save encrypts both.
        credential.save(update_fields=["value"])


def decrypt_existing(apps, schema_editor):
    """
    ⚠️  **The reversal writes the keys back into the database as plaintext.**

        It exists because a migration with no reverse blocks a deployment, not
        because it is an ordinary thing to do. Whoever runs it reopens the hole
        closed here — so let that be an explicit decision rather than a side
        effect of a routine rollback.

    ⚠️  And the write uses raw SQL, not the ORM.

        The model field is still encrypted at this moment (reversing operations
        starts from the bottom), so any `save` or `update` passing through it
        re-encrypts — and "decryption" ends with rows as encrypted as they started.
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
