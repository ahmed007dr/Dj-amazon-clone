"""
Shared pytest configuration.
"""

import shutil
import tempfile

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True, scope="session")
def fast_password_hashing():
    """
    ⚠️  Password hashing dominates the runtime of any test that creates users.

        PBKDF2 is calibrated to be **deliberately slow** — correct in production
        and pure overhead in tests. The development seed alone creates 17
        accounts, and spends most of its time hashing rather than on what it tests.

        This creates no behavioural gap: `check_password` works unchanged, and
        the password-strength validators stay complete, exactly as in production.
    """
    from django.conf import settings

    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def isolated_media(settings):
    """
    ⚠️  Files uploaded during tests are written into the real `MEDIA_ROOT`
        and pile up there forever.

    Redirecting them to a temporary directory deleted after each test prevents
    that pollution, and guarantees one test never sees another test's files.
    """
    temp_dir = tempfile.mkdtemp(prefix="test-media-")
    settings.MEDIA_ROOT = temp_dir
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════
#  Test files with genuine signatures
# ═══════════════════════════════════════════════════════════
#
# ⚠️  `b"fake-pdf"` no longer passes — and that is intentional.
#
#     `validate_upload` reads the file signature, not its header, because the
#     header is forged by the uploader in one line. Dummy bytes with an
#     `application/pdf` header are exactly the attack we block, and must not pass in a test.
#
#     The replacements here are the smallest valid file of each type: a real
#     signature at the start and padding after it. Enough for the check, with no bulk.

PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + b"0" * 64
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"0" * 64
#: The size in bytes 4–7 is part of the real signature but is not checked
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 64


def upload(name: str, content: bytes, content_type: str):
    """An upload with a valid signature, for upload tests."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, content, content_type=content_type)


def pdf_upload(name: str = "document.pdf"):
    return upload(name, PDF_BYTES, "application/pdf")


def real_png_bytes(size=(8, 8)) -> bytes:
    """
    A genuinely valid PNG image — not just a signature.

    ⚠️  `ImageField` decodes the image with Pillow after the signature check.

        Bytes that start with the PNG signature and end in padding pass
        `validate_upload` and are then rejected by Pillow — failing the test in
        a layer other than the one it means to exercise.
    """
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, (200, 30, 30)).save(buffer, format="PNG")
    return buffer.getvalue()


def png_upload(name: str = "image.png"):
    return upload(name, real_png_bytes(), "image/png")


@pytest.fixture(autouse=True)
def clear_cache():
    """
    The cache crosses test boundaries.

    The suspended-account set and the rate-limiting keys survive between tests
    and make later tests fail for reasons that make no sense.
    """
    cache.clear()
    yield
    cache.clear()
