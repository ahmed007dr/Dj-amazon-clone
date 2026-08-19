"""
Admin preview mode.

Answers: **"What does a student see? And what does a pharmacy see?"**

⚠️  This is a policy testing tool, and it is **dangerous by nature**:

    - it grants no permissions — it only narrows
    - it works only for someone holding an admin profile
    - it is never used in any write operation
    - every use is recorded in the audit log

    Without these constraints it becomes a bridge to impersonation.
"""

from __future__ import annotations

from dataclasses import dataclass

from accounts.models import AccountType

PREVIEW_HEADER = "HTTP_X_PREVIEW_AS"
PREVIEW_VERIFIED_HEADER = "HTTP_X_PREVIEW_VERIFIED"


@dataclass
class PreviewUser:
    """
    A dummy user for evaluation only.

    ⚠️  Never saved, never authenticated, and used only in `access.evaluate`.
        It carries the minimum surface the engine reads.
    """

    account_type: str
    is_verified: bool = False
    is_authenticated: bool = True

    #: Preview permissions are always empty — the admin does not "lend" their own
    #: permissions to the type being previewed, or they would see what that type genuinely cannot.
    def has_perm(self, _permission: str) -> bool:
        return False


class AnonymousPreview:
    """Preview as a guest."""

    account_type = AccountType.GUEST
    is_verified = False
    is_authenticated = False

    def has_perm(self, _permission: str) -> bool:
        return False


def build_preview_user(account_type: str, *, verified: bool = False):
    if account_type == AccountType.GUEST:
        return AnonymousPreview()
    return PreviewUser(account_type=account_type, is_verified=verified)


def resolve_preview(request):
    """
    Extracts the preview user from the request headers, or `None`.

    All conditions together:
      • the caller is authenticated
      • they hold an admin profile
      • the requested type is valid
      • the request is read-only
    """
    requested = request.META.get(PREVIEW_HEADER)
    if not requested:
        return None

    if request.method not in ("GET", "HEAD", "OPTIONS"):
        return None

    user = getattr(request, "user", None)
    if not (user and user.is_authenticated and hasattr(user, "admin_profile")):
        return None

    requested = requested.strip().upper()
    if requested not in AccountType.values:
        return None

    verified = request.META.get(PREVIEW_VERIFIED_HEADER, "").lower() in (
        "1",
        "true",
        "yes",
    )
    return build_preview_user(requested, verified=verified)


def log_preview(request, preview_user) -> None:
    from core.models.audit import AuditAction, AuditLog

    AuditLog.objects.create(
        actor=request.user,
        action=AuditAction.EXPORT,
        object_repr=f"معاينة كـ {preview_user.account_type}",
        changes={
            "path": request.path,
            "account_type": preview_user.account_type,
            "verified": getattr(preview_user, "is_verified", False),
        },
        ip_address=request.META.get("REMOTE_ADDR"),
    )


class PreviewAwareMixin:
    """
    Makes the view respect preview mode.

        class ProductListAPI(PreviewAwareMixin, PolicyAwareQuerySetMixin, ListAPIView):
            ...

    ⚠️  It never overrides `get_queryset`.

        It overrides `get_access_user` alone — the single extension point in
        `PolicyAwareQuerySetMixin`. Were it to override `get_queryset` too, the
        queryset would be filtered twice: once by the preview and once by the
        real user, showing the admin's full results interleaved with the preview.
    """

    def get_access_user(self):
        preview = resolve_preview(self.request)
        if preview is None:
            return super().get_access_user()

        if not getattr(self, "_preview_logged", False):
            log_preview(self.request, preview)
            self._preview_logged = True

        return preview
