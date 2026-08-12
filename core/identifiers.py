"""
مولّدات المعرّفات والرموز.

⚠️  `secrets` حصرًا — لا `random`.

    الكود القديم في utils/generate_code.py كان يستخدم `random`
    (Mersenne Twister) لتوليد **كود تفعيل الحساب**. من يراقب مخرجات
    كافية يستنتج الحالة الداخلية ويتوقّع الأكواد التالية — وكود
    التفعيل يمنح الوصول إلى الحساب.
"""

import hashlib
import secrets
from datetime import date

#: أبجدية Crockford Base32 — بلا I L O U لمنع اللبس في النطق والكتابة
CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def random_code(length: int = 8, alphabet: str = CROCKFORD_ALPHABET) -> str:
    """رمز عشوائي آمن تشفيريًا."""
    return "".join(secrets.choice(alphabet) for _ in range(length))


def business_number(prefix: str, random_length: int = 6, year: int | None = None) -> str:
    """
    رقم عمل بشري — ما ينطقه العميل على الهاتف.

        business_number('ORD')  →  'ORD-2026-7K3M9P'

    ⚠️  **ليس معرّف الرابط.** الرابط يحمل UUID والعرض يحمل هذا. (ADR-29)
        غير تسلسلي عمدًا — التسلسل يفصح عن حجم النشاط.
    """
    year = year or date.today().year
    return f"{prefix}-{year}-{random_code(random_length)}"


def secure_token(nbytes: int = 32) -> str:
    """رمز آمن للروابط — استرجاع كلمة المرور، تأكيد البريد."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """
    بصمة الرمز للتخزين.

    الرمز الصريح يُرسَل للمستخدم مرة واحدة ولا يُخزَّن أبدًا —
    تسريب قاعدة البيانات لا يجب أن يمنح القدرة على إعادة تعيين
    كلمات المرور.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token(token: str, token_hash: str) -> bool:
    """مقارنة ثابتة الزمن — تمنع هجمات التوقيت."""
    return secrets.compare_digest(hash_token(token), token_hash)


def random_filename(original_name: str) -> str:
    """
    اسم ملف عشوائي بمسار مجزّأ.

        random_filename('photo.jpg')  →  '8f/3k/8f3k2m9p4t8r2x5n1q7w.jpg'

    ⚠️  المسارات الحالية `media/brand/01.jpg` قابلة للتعداد بالكامل
        بلا أي فحص صلاحية.
    """
    ext = ""
    if "." in original_name:
        ext = "." + original_name.rsplit(".", 1)[-1].lower()

    name = random_code(20).lower()
    return f"{name[:2]}/{name[2:4]}/{name}{ext}"
