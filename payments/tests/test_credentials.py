"""
Encryption of gateway credentials.

⚠️  **What matters here is what is in the database, not what is in Python.**

    Testing `credential.value == "secret"` alone passes even if nothing was
    encrypted — it reads back what it just wrote. The real test reads the column
    with raw SQL and confirms the secret is not in it.
"""

import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import FieldError, ImproperlyConfigured
from django.db import connection

from core import encryption
from payments.models import PaymentProvider, ProviderCredential

pytestmark = pytest.mark.django_db


@pytest.fixture
def provider():
    return PaymentProvider.objects.create(
        code="paymob-test",
        name_ar="بيموب",
        name_en="Paymob",
        adapter_key="paymob",
    )


def raw_value(credential) -> str:
    """The value exactly as it sits in the column — bypassing the field's decryption."""
    table = ProviderCredential._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT value FROM {table} WHERE id = %s", [credential.pk])  # noqa: S608
        return cursor.fetchone()[0]


# ═══════════════════════════════════════════════════════════
#  Storage
# ═══════════════════════════════════════════════════════════


class TestStorage:
    def test_secret_is_not_stored_in_plain_text(self, provider):
        """
        ⚠️  **The most important test in the file.**

            A backup or a SQL leak must not hand over a usable key.
        """
        credential = ProviderCredential.objects.create(
            provider=provider, key="api_key", value="sk-live-super-secret"
        )

        stored = raw_value(credential)
        assert "sk-live-super-secret" not in stored
        assert stored.startswith(encryption.PREFIX)

    def test_value_reads_back_identical(self, provider):
        ProviderCredential.objects.create(
            provider=provider, key="api_key", value="sk-live-super-secret"
        )

        # A fresh read from the database, not from the saved object
        fetched = ProviderCredential.objects.get(provider=provider, key="api_key")
        assert fetched.value == "sk-live-super-secret"

    def test_same_secret_encrypts_differently_each_time(self, provider):
        """
        ⚠️  Deterministic encryption leaks equality: whoever sees the column
            learns that two gateways use the same key.
        """
        first = ProviderCredential.objects.create(
            provider=provider, key="api_key", value="same-secret"
        )
        second = ProviderCredential.objects.create(
            provider=provider, key="hmac_secret", value="same-secret"
        )

        assert raw_value(first) != raw_value(second)
        assert first.value == second.value == "same-secret"

    def test_adapter_receives_the_plain_secret(self, provider):
        """
        ⚠️  Encryption that reaches the gateway as ciphertext breaks every
            payment. This test catches that on the real build path.
        """
        from payments.services import _build_adapter

        ProviderCredential.objects.create(
            provider=provider, key="hmac_secret", value="the-real-secret", is_sandbox=True
        )

        adapter = _build_adapter(provider)
        assert adapter.credentials["hmac_secret"] == "the-real-secret"

    def test_masked_value_shows_last_four_of_the_plain_secret(self, provider):
        credential = ProviderCredential.objects.create(
            provider=provider, key="api_key", value="abcdefgh1234"
        )
        assert credential.masked_value.endswith("1234")
        assert "abcdefgh" not in credential.masked_value


# ═══════════════════════════════════════════════════════════
#  Querying
# ═══════════════════════════════════════════════════════════


class TestQuerying:
    def test_filtering_by_value_is_refused(self, provider):
        """
        ⚠️  **Silent failure is the danger**: the encryption is randomised, so
            `filter(value="k")` would have returned zero forever with no error —
            and that reads as "there is none" rather than "the question is invalid".
        """
        ProviderCredential.objects.create(provider=provider, key="api_key", value="k")

        with pytest.raises(FieldError):
            list(ProviderCredential.objects.filter(value="k"))

    def test_null_check_still_works(self, provider):
        """A check at the `NULL` level does not touch the content — so it stays permitted."""
        ProviderCredential.objects.create(provider=provider, key="api_key", value="k")
        assert ProviderCredential.objects.filter(value__isnull=False).count() == 1


# ═══════════════════════════════════════════════════════════
#  The key
# ═══════════════════════════════════════════════════════════


class TestKeyHandling:
    def test_writing_without_a_key_is_refused(self, provider, settings):
        """
        ⚠️  **No fallback to plaintext.**

            Saving silently without encryption is exactly the situation that was
            fixed: a field described as "encrypted" whose contents are exposed.
        """
        settings.FIELD_ENCRYPTION_KEY = ""

        with pytest.raises(ImproperlyConfigured):
            ProviderCredential.objects.create(provider=provider, key="api_key", value="secret")

    def test_wrong_key_reads_empty_instead_of_crashing(self, provider, settings):
        """
        ⚠️  A wrong key happens on **lists**: raising takes down the whole
            gateways screen instead of one row.

            And the empty value makes the adapter fail with "incomplete
            credentials" — a safe failure: no charging with a key that was not read.
        """
        credential = ProviderCredential.objects.create(
            provider=provider, key="api_key", value="secret"
        )

        settings.FIELD_ENCRYPTION_KEY = Fernet.generate_key().decode()

        assert ProviderCredential.objects.get(pk=credential.pk).value == ""

    def test_rotation_reads_old_and_writes_new(self, provider, settings):
        """
        ⚠️  Without rotation, a leaked key means a database that cannot be
            rescued without downtime. The first encrypts and all of them decrypt.
        """
        old_key = settings.FIELD_ENCRYPTION_KEY
        credential = ProviderCredential.objects.create(
            provider=provider, key="api_key", value="written-with-old-key"
        )

        new_key = Fernet.generate_key().decode()
        settings.FIELD_ENCRYPTION_KEY = f"{new_key},{old_key}"

        # The old one is still readable
        fetched = ProviderCredential.objects.get(pk=credential.pk)
        assert fetched.value == "written-with-old-key"

        # And re-saving moves it onto the new one
        fetched.save(update_fields=["value"])
        settings.FIELD_ENCRYPTION_KEY = new_key
        assert ProviderCredential.objects.get(pk=credential.pk).value == "written-with-old-key"

    def test_malformed_key_names_the_setting(self, provider, settings):
        """
        `cryptography`'s original message does not name the variable, so the
        operator hunts for it in the code rather than the environment file.
        """
        settings.FIELD_ENCRYPTION_KEY = "not-a-fernet-key"

        with pytest.raises(ImproperlyConfigured, match="FIELD_ENCRYPTION_KEY"):
            ProviderCredential.objects.create(provider=provider, key="api_key", value="secret")


# ═══════════════════════════════════════════════════════════
#  Legacy rows
# ═══════════════════════════════════════════════════════════


class TestLegacyRows:
    def test_plain_text_rows_stay_readable(self, provider):
        """
        ⚠️  A row written before the migration carries no encryption marker —
            reading it must work, or payment stops the moment it deploys and
            before the data migration has run.
        """
        credential = ProviderCredential.objects.create(
            provider=provider, key="api_key", value="new-value"
        )

        table = ProviderCredential._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET value = %s WHERE id = %s",  # noqa: S608
                ["legacy-plain-secret", credential.pk],
            )

        assert ProviderCredential.objects.get(pk=credential.pk).value == "legacy-plain-secret"

    def test_re_encrypting_an_encrypted_value_is_a_no_op(self):
        """
        ⚠️  It makes the data migration re-runnable: double encryption produced
            a value nobody could decrypt.
        """
        once = encryption.encrypt("secret")
        assert encryption.encrypt(once) == once
        assert encryption.decrypt(once) == "secret"

    def test_empty_values_pass_through_untouched(self):
        assert encryption.encrypt("") == ""
        assert encryption.encrypt(None) is None
        assert encryption.decrypt("") == ""
        assert encryption.decrypt(None) is None
