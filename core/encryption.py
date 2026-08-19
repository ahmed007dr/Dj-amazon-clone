"""
Encryption of sensitive fields at rest.

⚠️  **The problem this solves**: the payment gateway key is plaintext in the
    database. The code does not contain it — which is correct and not enough.
    Any backup, any SQL leak, or one glance at a `psql` screen is enough to move
    real money.

⚠️  **The encryption is randomised, not deterministic** — Fernet injects an IV
    and a timestamp, so the same value produces different ciphertext every time.

    The field is therefore **never searched and never compared**:
    `filter(value="k")` would have returned zero rows forever with no error —
    the worst possible behaviour. The field explicitly refuses to be queried instead.

⚠️  **An explicit prefix, never guessing**: an encrypted row starts with `PREFIX`.

    Distinguishing with `try: decrypt() except: it is plaintext` swallows a
    corrupt key and treats it as plaintext — sending it to the gateway as-is.
    The prefix turns "is this encrypted?" into an answer rather than a
    probability, and allows old rows to be read during the data migration.

Configuration:

    FIELD_ENCRYPTION_KEY=<key>

    Generate it with:
        python -c "from cryptography.fernet import Fernet; \
                   print(Fernet.generate_key().decode())"

⚠️  **Key rotation**: the value accepts comma-separated keys.

        FIELD_ENCRYPTION_KEY=<new>,<old>

    The first encrypts, all of them decrypt. Add a new value at the front, then
    re-save the rows, then drop the old one. Without this, a leaked key means a
    database that cannot be rescued without downtime.
"""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.core.exceptions import FieldError, ImproperlyConfigured
from django.core.signals import setting_changed
from django.db import models
from django.dispatch import receiver

logger = logging.getLogger(__name__)

#: Marker for an encrypted row. Chosen from characters gateway keys never start
#: with (they are base64, hex or UUID) — so no real value can be mistaken for the marker.
PREFIX = "enc$fernet$"

_cipher: MultiFernet | None = None


def _configured_keys() -> list[str]:
    raw = getattr(settings, "FIELD_ENCRYPTION_KEY", "") or ""
    return [key.strip() for key in raw.split(",") if key.strip()]


def _get_cipher() -> MultiFernet | None:
    """Built once and cached — key derivation is not free per row."""
    global _cipher

    if _cipher is not None:
        return _cipher

    keys = _configured_keys()
    if not keys:
        return None

    try:
        _cipher = MultiFernet([Fernet(key.encode()) for key in keys])
    except (ValueError, TypeError) as exc:
        # ⚠️  A malformed key must say so clearly.
        #
        #     Fernet's original message ("Fernet key must be 32
        #     url-safe base64-encoded bytes") does not name the variable,
        #     so the operator hunts for it in the code rather than the environment file.
        raise ImproperlyConfigured(
            "FIELD_ENCRYPTION_KEY غير صالح — يجب أن يكون مفتاح Fernet. ولّده بـ: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        ) from exc

    return _cipher


@receiver(setting_changed)
def _reset_cipher(sender, setting, **kwargs):
    """A test that swaps the key must not inherit a cipher built with the old one."""
    if setting == "FIELD_ENCRYPTION_KEY":
        global _cipher
        _cipher = None


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(PREFIX)


def encrypt(value: str | None) -> str | None:
    """
    Plaintext ← ciphertext with its marker.

    ⚠️  **Refuses to write without a key** — it never falls back to plaintext.

        Silent fallback is exactly the situation we are fixing: a field
        described as "encrypted" whose contents are in the clear. Failing here
        surfaces at configuration time, not a month later in a leaked backup.
    """
    if value is None or value == "":
        return value
    if is_encrypted(value):
        # ⚠️  Re-encrypting is a no-op on already-encrypted values. This makes the data
        #     migration re-runnable without double encryption.
        return value

    cipher = _get_cipher()
    if cipher is None:
        raise ImproperlyConfigured(
            "FIELD_ENCRYPTION_KEY غير مضبوط — رُفض حفظ قيمة حسّاسة بلا تشفير. "
            "اضبطه في .env ثم أعد المحاولة."
        )

    return PREFIX + cipher.encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str | None:
    """
    Ciphertext ← plaintext.

    ⚠️  A value with no marker is returned as-is — rows predating encryption
        stay readable until the data migration reaches them.

    ⚠️  And a decryption failure is logged, returns `""`, and raises nothing.

        A wrong key or a corrupt row happens on **lists** — raising would take
        down the whole gateways screen instead of one row. The empty value
        makes the adapter fail with "incomplete credentials: api_key", a safe
        and comprehensible failure: no charging with a key we could not read.
    """
    if not is_encrypted(value):
        return value

    cipher = _get_cipher()
    if cipher is None:
        logger.error("قيمة مشفّرة بلا FIELD_ENCRYPTION_KEY — تعذّرت القراءة")
        return ""

    try:
        return cipher.decrypt(value[len(PREFIX) :].encode()).decode()
    except InvalidToken:
        logger.error("تعذّر فكّ تشفير قيمة — مفتاح خاطئ أو صف تالف")
        return ""


class EncryptedTextField(models.TextField):
    """
    Text encrypted on write and decrypted on read — fully transparent to the code.

    ⚠️  **Never queried.** See the randomness note at the top of this module.

    ⚠️  And unfit for a field needing an index or a uniqueness constraint: the
        ciphertext for the same text differs each time, so the constraint does
        not prevent duplicates and the index is never used.
    """

    #: The only one allowed — it works at the `NULL` level, not on the content
    ALLOWED_LOOKUPS = frozenset({"isnull"})

    def from_db_value(self, value, expression, connection):
        return decrypt(value)

    def get_prep_value(self, value):
        return encrypt(super().get_prep_value(value))

    def get_lookup(self, lookup_name):
        if lookup_name not in self.ALLOWED_LOOKUPS:
            raise FieldError(
                f"لا يُستعلَم عن حقل مشفّر بـ `{lookup_name}` — "
                "التشفير عشوائي فالمقارنة تفشل دائمًا بلا خطأ. "
                "رشّح بحقل آخر ثم افحص القيمة في بايثون."
            )
        return super().get_lookup(lookup_name)
