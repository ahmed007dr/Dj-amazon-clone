"""
Feature switches the owner can flip without a deploy.

They are rows in `SystemSetting` (group *general*), read through its cache, so a
switch costs no query once warm and a missing row means "off".

⚠️  **Missing means off.** Every switch here defaults to the conservative
    behaviour, so a fresh database, a restored backup or a deleted row can never
    switch an enforcement on by surprise.
"""

from core.models.settings import SystemSetting

#: Student verification as a *requirement*.
#:
#: Off  → nothing is asked of the student: no "pending verification" notices, and
#:        student prices follow the account type alone.
#: On   → the notices return, and student prices require an approved ID.
STUDENT_VERIFICATION_ENFORCED = "student_verification_enforced"


def is_enabled(key: str) -> bool:
    return bool(SystemSetting.get(key, False))


def student_verification_enforced() -> bool:
    return is_enabled(STUDENT_VERIFICATION_ENFORCED)
