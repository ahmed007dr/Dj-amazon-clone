"""
Testing helpers.

⚠️  **Testing a feature is not testing the gate.**

    After the permissions were tightened, every old admin test started coming
    back 403 — because its subject is the feature, not the guard. Granting the
    domains here returns the tests to their subject, and the gate itself has its
    own file: `core/tests/test_domain_permissions.py`.

⚠️  And it is never used in production code: its place is `core` because every
    domain needs it, and it imports not one business domain.
"""

from __future__ import annotations


def grant_all_domains(user):
    """
    Grants the test user the full set of domain permissions.

    ⚠️  The domains alone — not finance, not suppliers, not loyalty and not
        staff. Those were guarded by explicit permissions before the tightening,
        and granting them here would have made a test pass on a permission its
        subject does not hold.
    """
    from django.contrib.auth.models import Permission

    from core.permissions import DOMAIN_PERMISSIONS

    for path in DOMAIN_PERMISSIONS.values():
        app_label, codename = path.split(".")
        permission = Permission.objects.filter(
            content_type__app_label=app_label, codename=codename
        ).first()
        if permission is not None:
            user.user_permissions.add(permission)

    # ⚠️  The cache holds the permissions for the object's lifetime: without
    # clearing it the loaded instance stays unprivileged and the test fails for no evident reason.
    for attribute in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
        if hasattr(user, attribute):
            delattr(user, attribute)

    return user
