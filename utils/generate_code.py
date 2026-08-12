"""
مهجور — يُحذف مع إزالة النماذج القديمة.

الاستبدال: core.identifiers

الأصل كان يستخدم `random` (Mersenne Twister) لتوليد كود تفعيل
الحساب — قابل للتنبؤ من يراقب مخرجات كافية.
"""

import warnings

from core.identifiers import random_code


def generate_code(length: int = 8) -> str:
    warnings.warn(
        "utils.generate_code مهجور — استخدم core.identifiers.random_code",
        DeprecationWarning,
        stacklevel=2,
    )
    return random_code(length)
