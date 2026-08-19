"""
Identifier and token generators.

⚠️  `secrets` exclusively — never `random`.

    The legacy code in utils/generate_code.py used `random` (Mersenne Twister)
    to generate the **account activation code**. Anyone observing enough output
    can deduce the internal state and predict the following codes — and the
    activation code grants access to the account.
"""

import hashlib
import secrets
from datetime import date

#: Crockford Base32 alphabet — without I L O U to prevent confusion when spoken or written
CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def random_code(length: int = 8, alphabet: str = CROCKFORD_ALPHABET) -> str:
    """A cryptographically secure random token."""
    return "".join(secrets.choice(alphabet) for _ in range(length))


def business_number(prefix: str, random_length: int = 6, year: int | None = None) -> str:
    """
    A human-facing business number — what the customer reads out on the phone.

        business_number('ORD')  →  'ORD-2026-7K3M9P'

    ⚠️  **Not the URL identifier.** The URL carries a UUID and the display carries this. (ADR-29)
        Deliberately non-sequential — a sequence discloses the size of the business.
    """
    year = year or date.today().year
    return f"{prefix}-{year}-{random_code(random_length)}"


def secure_token(nbytes: int = 32) -> str:
    """A URL-safe token — password recovery, email confirmation."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """
    The token's hash, for storage.

    The plaintext token is sent to the user once and is never stored — a
    database leak must not grant the ability to reset passwords.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(token: str, token_hash: str) -> bool:
    """A constant-time comparison — it blocks timing attacks."""
    return secrets.compare_digest(hash_token(token), token_hash)


def random_filename(original_name: str) -> str:
    """
    A random filename on a sharded path.

        random_filename('photo.jpg')  →  '8f/3k/8f3k2m9p4t8r2x5n1q7w.jpg'

    ⚠️  The current `media/brand/01.jpg` paths are fully enumerable with no
        permission check at all.
    """
    ext = ""
    if "." in original_name:
        ext = "." + original_name.rsplit(".", 1)[-1].lower()

    name = random_code(20).lower()
    return f"{name[:2]}/{name[2:4]}/{name}{ext}"
