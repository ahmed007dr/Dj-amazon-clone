"""
Access policy evaluation engine.

⚠️  The governing principle: **hiding the interface is not security.**

    Filtering happens in the **queryset**, not in the serializer and not in the
    component. An unauthorised user cannot:

        view · search · filter · add to a wishlist · add to the cart ·
        check out · reach it by direct link · manipulate it through the API

    One point decides, and everyone consumes its decision. Duplicating the logic
    in several places means a hole at the first edit forgotten in one of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from django.db.models import Q
from django.utils.translation import get_language

from access.models import AccessLevel, AccessPolicy


class Decision(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class DenialReason(str, Enum):
    """
    The denial reason — for diagnosis and for choosing the displayed message.

    ⚠️  Never revealed to the user except where disclosing the resource's
        existence is acceptable. For resources whose existence must be hidden,
        the response is a uniform `404`.
    """

    NONE = "NONE"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    ACCOUNT_TYPE_NOT_ALLOWED = "ACCOUNT_TYPE_NOT_ALLOWED"
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"
    PERMISSION_REQUIRED = "PERMISSION_REQUIRED"
    POLICY_INACTIVE = "POLICY_INACTIVE"


@dataclass(frozen=True)
class AccessResult:
    decision: Decision
    reason: DenialReason = DenialReason.NONE
    message: str = ""

    def __bool__(self) -> bool:
        return self.decision is Decision.ALLOW

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW


ALLOWED = AccessResult(Decision.ALLOW)


def _deny(reason: DenialReason, policy: AccessPolicy | None = None) -> AccessResult:
    message = ""
    if policy is not None:
        lang = (get_language() or "ar")[:2]
        message = getattr(policy, f"denial_message_{lang}", "") or policy.denial_message_ar
    return AccessResult(Decision.DENY, reason, message)


# ═══════════════════════════════════════════════════════════
#  Evaluation
# ═══════════════════════════════════════════════════════════


def evaluate(user, policy: AccessPolicy | None) -> AccessResult:
    """
    The central decision. **Every** access check passes through here.

    `policy=None` ⟵ the default policy, and if that is absent the resource is public.
    """
    if policy is None:
        policy = AccessPolicy.get_default()
        if policy is None:
            return ALLOWED

    if not policy.is_active:
        # A disabled policy ⟵ deny, not allow.
        # The safe assumption: disabling a policy by mistake must not expose resources.
        return _deny(DenialReason.POLICY_INACTIVE, policy)

    if policy.level == AccessLevel.PUBLIC:
        return ALLOWED

    is_authenticated = bool(user and getattr(user, "is_authenticated", False))
    if not is_authenticated:
        return _deny(DenialReason.AUTHENTICATION_REQUIRED, policy)

    allowed_types = policy.allowed_account_types or []
    if allowed_types and user.account_type not in allowed_types:
        return _deny(DenialReason.ACCOUNT_TYPE_NOT_ALLOWED, policy)

    if policy.level == AccessLevel.PROFESSIONAL or policy.requires_verification:
        if not user.is_verified:
            return _deny(DenialReason.VERIFICATION_REQUIRED, policy)

    if policy.required_permission and not user.has_perm(policy.required_permission):
        return _deny(DenialReason.PERMISSION_REQUIRED, policy)

    return ALLOWED


def accessible_policy_ids(user) -> list:
    """
    The policy ids permitted for this user.

    ⚠️  Computed **once** and then used in `filter(policy_id__in=...)`.

        The alternative — evaluating each row separately — means one evaluation
        per product per page. Policies number in the tens; products in the tens
        of thousands.
    """
    return [
        policy.pk
        for policy in AccessPolicy.objects.filter(is_active=True)
        if evaluate(user, policy).allowed
    ]


def selectable_policies() -> list[AccessPolicy]:
    """
    The policies assignable to a resource — for admin screens.

    ⚠️  This domain's public interface is `services` alone; other domains
        call it and never touch `models`.

    ⚠️  And the default comes **first**, not in alphabetical order.

        It is the "for everyone" answer, and the right choice for most products.
        Burying it mid-list makes the admin pick from the top of what is visible
        — restricting a public product unintentionally, and discovering it only
        when a customer complains they cannot see the item.
    """
    return list(
        AccessPolicy.objects.filter(is_active=True).order_by("-is_default", "level", "code")
    )


def accessible_filter(user, field: str = "access_policy") -> Q:
    """
    A ready-made filter to merge into any queryset.

        Product.objects.filter(access.accessible_filter(user))

    It includes resources with no explicit policy if the default one is
    permitted — otherwise they are excluded.
    """
    condition = Q(**{f"{field}_id__in": accessible_policy_ids(user)})

    default_policy = AccessPolicy.get_default()
    default_allowed = default_policy is None or evaluate(user, default_policy).allowed
    if default_allowed:
        condition |= Q(**{f"{field}__isnull": True})

    return condition


class PolicyAwareQuerySetMixin:
    """
    Mixed into any view that serves policy-governed resources.

        class ProductListAPI(PolicyAwareQuerySetMixin, ListAPIView):
            policy_field = "access_policy"

            def get_base_queryset(self):
                return Product.objects.filter(is_active=True)

    ⚠️  Filtering happens in the queryset — not in the serializer.

        Filtering in the serializer means the row is read from the database and
        then hidden: the count stays wrong, pagination yields short pages, and
        the resource's existence leaks through the difference in counts.

    ⚠️  **Custom filters go in `get_base_queryset`, never in `get_queryset`.**

        Overriding `get_queryset` in a subclass **silently disables policy
        filtering** — no error, no warning, just restricted products visible to
        everyone. It is a mistake we actually made, and the tests caught it.

        So `get_queryset` here is effectively `final`: it calls
        `get_base_queryset` and then always applies the filter.
    """

    policy_field = "access_policy"

    def get_access_user(self):
        """
        The single extension point for deciding "who is being evaluated".

        `access.preview.PreviewAwareMixin` overrides it to return a dummy user —
        so it needs no `get_queryset` override and never filters twice.
        """
        return getattr(self.request, "user", None)

    def get_base_queryset(self):
        """
        The queryset before policy filtering.

        Filters, ordering and search are written **here** — not in `get_queryset`.
        """
        return super().get_queryset()

    def get_queryset(self):
        return self.get_base_queryset().filter(
            accessible_filter(self.get_access_user(), self.policy_field)
        )


def require_access(user, policy: AccessPolicy | None, *, reveal_existence: bool = False):
    """
    Raises on denial.

    `reveal_existence=False` (the default) ⟵ **`404`**.

        A `403` confirms the resource exists. On a restricted catalogue, the
        difference between `403` and `404` exposes the entire list of restricted
        products.

    `reveal_existence=True` ⟵ `403` with the policy's message, for cases where
    the resource's existence is already known (a product that appeared in public
    results and then had purchasing restricted).
    """
    from core.errors import BusinessError, ErrorCode

    result = evaluate(user, policy)
    if result.allowed:
        return result

    if not reveal_existence:
        raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)

    raise BusinessError(
        ErrorCode.PRODUCT_ACCESS_DENIED,
        detail=result.message or None,
        status_code=403,
    )
