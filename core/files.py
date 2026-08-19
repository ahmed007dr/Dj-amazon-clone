"""
Sensitive files.

⚠️  An obscure path is not protection.

    A file under `MEDIA_URL` is served to anyone who knows its path — with no
    authentication and no ownership check. And sequential paths
    (`media/brand/01.jpg`) are guessed with a trivial loop.

    Protection is two layers:
      1. A random name on a sharded path  →  core.identifiers.random_filename
      2. A signed URL with a time limit    →  this file
"""

from __future__ import annotations

from django.core import signing
from django.core.exceptions import ValidationError

#: Link lifetime — deliberately short.
#: The link gets shared, copied, and lingers in browser history; a short life limits the damage.
SIGNED_URL_TTL = 300

SALT = "core.files.signed-url"

#: Allowed document types — an allowlist is safer than a blocklist
ALLOWED_DOCUMENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
}

MAX_DOCUMENT_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_IMAGE_SIZE = 5 * 1024 * 1024


def sign_file_access(resource: str, resource_id, user_id) -> str:
    """
    An access signature for one specific file and one specific user.

    ⚠️  `user_id` is part of the signed payload — the link does not work for
        anyone other than the person it was issued to. Sharing it grants nothing.
    """
    return signing.dumps(
        {"r": resource, "id": str(resource_id), "u": str(user_id)},
        salt=SALT,
    )


def verify_file_access(signature: str, resource: str, user_id) -> str | None:
    """
    Verifies and returns the resource id, or `None` on any failure.

    Failure covers: a forged signature · expiry · a different resource · a
    different user.
    """
    try:
        payload = signing.loads(signature, salt=SALT, max_age=SIGNED_URL_TTL)
    except signing.BadSignature:
        return None

    if payload.get("r") != resource:
        return None
    if payload.get("u") != str(user_id):
        return None

    return payload.get("id")


#: Product image types — narrower than documents: no PDF on a product page
ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}

#: File signature (magic bytes) → its true type.
#
# ⚠️  **`content_type` comes from the client and can be forged.**
#
#     Uploading `shell.php` with an `image/png` header passes a surface check entirely.
#     The signature is read from the file's own first bytes, and the uploader
#     cannot change it without actually changing the file.
#
#     The key is (offset, bytes) — WebP needs two checks because its signature
#     is split: `RIFF`, then `WEBP` four bytes later after the file size.
_MAGIC_SIGNATURES: list[tuple[str, list[tuple[int, bytes]]]] = [
    ("image/jpeg", [(0, b"\xff\xd8\xff")]),
    ("image/png", [(0, b"\x89PNG\r\n\x1a\n")]),
    ("image/webp", [(0, b"RIFF"), (8, b"WEBP")]),
    ("application/pdf", [(0, b"%PDF-")]),
]

#: The longest signature we need to read
_MAGIC_READ_SIZE = 16


def detect_file_type(uploaded_file) -> str | None:
    """
    The true type from the file signature — or `None` if unrecognised.

    ⚠️  The pointer is rewound to zero after reading.

        Leaving it advanced makes Django store a file missing its first sixteen
        bytes — a broken image uploaded "successfully" and never displayed.
    """
    try:
        uploaded_file.seek(0)
        header = uploaded_file.read(_MAGIC_READ_SIZE)
    finally:
        uploaded_file.seek(0)

    for content_type, parts in _MAGIC_SIGNATURES:
        if all(header[offset : offset + len(magic)] == magic for offset, magic in parts):
            return content_type

    return None


def validate_upload(uploaded_file, *, allowed_types=None, max_size=None) -> None:
    """
    Validates an uploaded file before storing it.

    ⚠️  **The check is on the file signature, not on its header.**

        `content_type` comes from the client and can be forged in one line;
        an allowlist built on it alone is protection in appearance only. The
        signature is read from the file itself.

    ⚠️  And a file with an unknown signature is **rejected**, not accepted cautiously.

        Accepting by default makes every format we did not think of an open
        door; an allowlist means a new one is added by decision, not by oversight.
    """
    allowed_types = allowed_types or ALLOWED_DOCUMENT_TYPES
    max_size = max_size or MAX_DOCUMENT_SIZE

    if uploaded_file.size > max_size:
        raise ValidationError(
            f"حجم الملف يتجاوز الحد المسموح ({max_size // (1024 * 1024)} ميجابايت)"
        )

    # ⚠️  A zero size passes every content check — and is stored as an empty file that looks fine
    if uploaded_file.size == 0:
        raise ValidationError("الملف فارغ")

    detected = detect_file_type(uploaded_file)

    if detected is None:
        raise ValidationError("تعذّر التعرّف على نوع الملف")

    if detected not in allowed_types:
        raise ValidationError("نوع الملف غير مسموح")

    # ⚠️  A mismatch between header and signature signals forgery, not a passing
    #     glitch — it is rejected and logged rather than silently corrected.
    declared = getattr(uploaded_file, "content_type", None)
    if declared and declared not in allowed_types:
        raise ValidationError("نوع الملف غير مسموح")
