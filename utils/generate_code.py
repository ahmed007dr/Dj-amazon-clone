"""
Deprecated — to be deleted along with the legacy forms.

Replacement: core.identifiers

The original used `random` (Mersenne Twister) to generate the account
activation code — predictable to anyone who observes enough output.
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
