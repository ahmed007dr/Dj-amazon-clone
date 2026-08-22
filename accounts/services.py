"""
Identity services — the only public interface to this domain.

Other domains call these functions and never touch `models.py`.
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import (
    AccountStatus,
    AccountStatusChange,
    SecurityToken,
    TokenPurpose,
    User,
    UserSession,
)
from core.errors import BusinessError, ErrorCode
from core.identifiers import hash_token, secure_token
from core.models.audit import AuditAction, AuditLog
from core.presence import PresenceRegistry

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  Session revocation on suspension  (ADR-16)
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  The problem: an already-issued token stays valid until it expires.
#      Untreated, a suspended user keeps working for a full 10 minutes.
#
#  The solution has three layers:
#      1. A short-lived access token (10 minutes) — in the settings
#      2. A blacklist for the refresh token — preventing renewal
#      3. The suspended set in the cache — checked on every request, so the effect is **immediate**
#
#  Layer 3 is what makes the "suspend account" button real rather than decorative.

SUSPENDED_CACHE_PREFIX = "suspended_user:"
SUSPENDED_CACHE_TTL = 60 * 60 * 24 * 7

#: How long a user counts as online — configurable (business rule 3)
PRESENCE_WINDOW = timedelta(minutes=5)

#: Security token lifetime
EMAIL_VERIFICATION_TTL = timedelta(hours=24)
PASSWORD_RESET_TTL = timedelta(minutes=45)


def _suspended_key(user_id) -> str:
    return f"{SUSPENDED_CACHE_PREFIX}{user_id}"


def is_suspended_cached(user_id) -> bool:
    """
    An O(1) check called in the authentication layer on every request.

    The cache is the fast source of truth; the database is the durable one.
    """
    return cache.get(_suspended_key(user_id)) is not None


def _mark_suspended(user_id) -> None:
    cache.set(_suspended_key(user_id), True, SUSPENDED_CACHE_TTL)


def _clear_suspended(user_id) -> None:
    cache.delete(_suspended_key(user_id))


def revoke_all_tokens(user: User) -> int:
    """
    Revoke all of the user's refresh tokens. Returns how many were revoked.

    A failure on one token does not stop the rest — an expired or
    already-revoked token is an expected state, and what matters is that
    everything still valid gets revoked.
    """
    revoked = 0
    for token in OutstandingToken.objects.filter(user=user):
        try:
            RefreshToken(token.token).blacklist()
            revoked += 1
        except TokenError as exc:
            logger.debug("تخطّي توكن غير صالح للمستخدم %s: %s", user.pk, exc)
        except Exception:
            logger.exception("فشل غير متوقع في إبطال توكن للمستخدم %s", user.pk)
    return revoked


@transaction.atomic
def suspend_account(
    user: User,
    *,
    reason: str,
    actor: User | None = None,
    status: str = AccountStatus.SUSPENDED,
) -> User:
    """
    Suspend an account — with immediate effect.

    The owner (`AdminProfile.is_owner`) is never suspended — otherwise the
    system could be locked away from everyone.
    """
    if status not in (AccountStatus.SUSPENDED, AccountStatus.BLOCKED):
        raise ValueError("الحالة يجب أن تكون SUSPENDED أو BLOCKED")

    admin_profile = getattr(user, "admin_profile", None)
    if admin_profile is not None and admin_profile.is_owner:
        raise BusinessError(
            ErrorCode.PERMISSION_DENIED,
            detail="لا يمكن إيقاف حساب مالك النظام",
        )

    previous = user.status
    if previous == status:
        return user

    user.status = status
    user.save(update_fields=["status"])

    AccountStatusChange.objects.create(
        user=user,
        from_status=previous,
        to_status=status,
        reason=reason,
        changed_by=actor,
    )

    _mark_suspended(user.pk)  # Layer 3 — immediate effect
    revoke_all_tokens(user)  # Layer 2 — prevents renewal
    close_all_sessions(user, revoked=True)

    AuditLog.objects.create(
        actor=actor,
        action=AuditAction.SUSPEND,
        object_repr=str(user),
        changes={"status": {"old": previous, "new": status}, "reason": reason},
    )
    return user


@transaction.atomic
def activate_account(user: User, *, reason: str = "", actor: User | None = None) -> User:
    previous = user.status
    if previous == AccountStatus.ACTIVE:
        return user

    user.status = AccountStatus.ACTIVE
    user.save(update_fields=["status"])

    AccountStatusChange.objects.create(
        user=user,
        from_status=previous,
        to_status=AccountStatus.ACTIVE,
        reason=reason or "إعادة تفعيل",
        changed_by=actor,
    )

    _clear_suspended(user.pk)

    AuditLog.objects.create(
        actor=actor,
        action=AuditAction.ACTIVATE,
        object_repr=str(user),
        changes={"status": {"old": previous, "new": AccountStatus.ACTIVE}},
    )
    return user


# ═══════════════════════════════════════════════════════════
#  Sessions
# ═══════════════════════════════════════════════════════════


def device_type_from_user_agent(user_agent: str) -> str:
    """
    ⚠️  Public rather than private — `analytics` uses it to classify visitor devices.

        A second copy of the classification would have made one device count as
        a "tablet" in sessions and a "phone" in the traffic report.
    """
    from accounts.models import DeviceType

    ua = (user_agent or "").lower()
    if any(k in ua for k in ("ipad", "tablet")):
        return DeviceType.TABLET
    if any(k in ua for k in ("mobi", "android", "iphone")):
        return DeviceType.MOBILE
    if ua:
        return DeviceType.DESKTOP
    return DeviceType.UNKNOWN


def open_session(user: User, *, session_key: str, request=None) -> UserSession:
    ip = user_agent = None
    if request is not None:
        ip = request.META.get("REMOTE_ADDR")
        user_agent = request.META.get("HTTP_USER_AGENT", "")

    return UserSession.objects.create(
        user=user,
        session_key=session_key,
        ip_address=ip,
        user_agent=user_agent or "",
        device_type=device_type_from_user_agent(user_agent or ""),
    )


def close_session(session: UserSession, *, revoked: bool = False) -> UserSession:
    now = timezone.now()
    session.logout_at = now
    if revoked:
        session.revoked_at = now
    session.duration_seconds = int((now - session.login_at).total_seconds())
    session.save(update_fields=["logout_at", "revoked_at", "duration_seconds"])

    # ⚠️  Logging out drops the heartbeat — otherwise the departed user stays
    #     "online" until the window expires, so the admin sees five people connected when three have
    #     left.
    #     The condition is deliberate: a second device still open means its owner is online.
    if not UserSession.objects.filter(user_id=session.user_id, logout_at__isnull=True).exists():
        drop_presence(session.user_id)

    return session


def close_all_sessions(user: User, *, revoked: bool = False) -> int:
    count = 0
    for session in UserSession.objects.filter(user=user, logout_at__isnull=True):
        close_session(session, revoked=revoked)
        count += 1
    return count


# ═══════════════════════════════════════════════════════════
#  Live presence  (ADR-17)
# ═══════════════════════════════════════════════════════════

PRESENCE_KEY = "presence:live"

#: The heartbeat is not written on every request — once every half minute is enough for the
#:     five-minute window.
PRESENCE_HEARTBEAT = timedelta(seconds=30)

#: The same record serves anonymous visitors in `analytics` — see `core.presence`.
presence = PresenceRegistry(PRESENCE_KEY, window=PRESENCE_WINDOW, heartbeat=PRESENCE_HEARTBEAT)


def touch_activity(user_id) -> None:
    """
    A presence heartbeat — **in the cache, not in the database**.

    ⚠️  Writing `last_activity` on every request kills the database (ADR-17).
        `flush_presence` drains the record into the sessions every minute.

    ⚠️  And the key is **the user, not the session**: the access token carries
        no login-session id, and tying it to one would need a new claim in the
        token — while "who is online now" is a question about the user anyway.
    """
    presence.touch(user_id)


def drop_presence(user_id) -> None:
    """Drop the heartbeat — on logout or revocation."""
    presence.drop(user_id)


def live_user_ids() -> set:
    """Those online from the cache alone — before any flush."""
    result = set()
    for identity in presence.identities():
        try:
            result.add(uuid.UUID(identity))
        except (AttributeError, ValueError):
            continue
    return result


def online_user_ids() -> list:
    """
    Who is online now — the **union** of the cache and the database.

    ⚠️  The two sources are not redundant:

        the cache knows about a heartbeat not yet flushed, and the database
        knows about a session opened before the first heartbeat arrived (and it
        survives a cache restart). Using either alone drops one of those cases.
    """
    cutoff = timezone.now() - PRESENCE_WINDOW
    from_db = set(
        UserSession.objects.filter(last_activity__gte=cutoff, logout_at__isnull=True)
        .values_list("user_id", flat=True)
        .distinct()
    )
    return list(from_db | live_user_ids())


def flush_presence() -> int:
    """
    Flush the presence record into `UserSession.last_activity` — a per-minute task.

    ⚠️  Timestamps are grouped by minute rather than written individually.

        Second-level precision in "last seen" is read by nobody, and grouping
        makes the number of updates equal the number of distinct minutes rather
        than the number of people online.
    """
    alive = presence.alive()
    if not alive:
        return 0

    groups: dict = {}
    for key, stamp in alive.items():
        try:
            user_id = uuid.UUID(key)
        except (AttributeError, ValueError):
            continue
        groups.setdefault(stamp.replace(second=0, microsecond=0), []).append(user_id)

    updated = 0
    for stamp, user_ids in groups.items():
        # ⚠️  `last_activity__lt` prevents moving a newer timestamp backwards
        updated += UserSession.objects.filter(
            user_id__in=user_ids, logout_at__isnull=True, last_activity__lt=stamp
        ).update(last_activity=stamp)

    return updated


# ═══════════════════════════════════════════════════════════
#  Security tokens
# ═══════════════════════════════════════════════════════════


def issue_token(
    user: User,
    purpose: str,
    *,
    ttl: timedelta | None = None,
    request=None,
    new_email: str = "",
) -> tuple[SecurityToken, str]:
    """
    Returns `(the record, the plaintext token)`.

    ⚠️  The plaintext token is sent to the user once and is **never stored**.
        Only its hash is kept — a database leak grants nobody the ability to
        reset passwords.
    """
    if ttl is None:
        ttl = (
            PASSWORD_RESET_TTL if purpose == TokenPurpose.PASSWORD_RESET else EMAIL_VERIFICATION_TTL
        )

    # One valid token per purpose — issuing a new one revokes the previous
    SecurityToken.objects.filter(user=user, purpose=purpose, used_at__isnull=True).update(
        used_at=timezone.now()
    )

    raw = secure_token()
    record = SecurityToken.objects.create(
        user=user,
        purpose=purpose,
        token_hash=hash_token(raw),
        expires_at=timezone.now() + ttl,
        requested_ip=request.META.get("REMOTE_ADDR") if request else None,
        new_email=new_email,
    )
    return record, raw


def consume_token(raw_token: str, purpose: str) -> SecurityToken:
    """Verifies and consumes. Raises `BusinessError` on failure."""
    record = SecurityToken.objects.filter(token_hash=hash_token(raw_token), purpose=purpose).first()

    if record is None or not record.is_valid:
        raise BusinessError(ErrorCode.TOKEN_INVALID)

    record.used_at = timezone.now()
    record.save(update_fields=["used_at"])
    return record


@transaction.atomic
def verify_email(raw_token: str) -> User:
    record = consume_token(raw_token, TokenPurpose.EMAIL_VERIFICATION)
    user = record.user

    user.email_verified_at = timezone.now()
    user.is_active = True
    user.save(update_fields=["email_verified_at", "is_active"])

    AuditLog.objects.create(
        actor=user,
        action=AuditAction.UPDATE,
        object_repr=str(user),
        changes={"email_verified": {"old": False, "new": True}},
    )
    return user


@transaction.atomic
def reset_password(raw_token: str, new_password: str) -> User:
    """
    Set a new password.

    **Revoking every session is mandatory** — anyone who knew the old password
    must lose access immediately.
    """
    record = consume_token(raw_token, TokenPurpose.PASSWORD_RESET)
    user = record.user

    user.set_password(new_password)
    user.save(update_fields=["password"])

    revoke_all_tokens(user)
    close_all_sessions(user, revoked=True)

    AuditLog.objects.create(
        actor=user,
        action=AuditAction.UPDATE,
        object_repr=str(user),
        changes={"password": {"old": "***", "new": "***"}},
    )
    return user


@transaction.atomic
def confirm_email_change(raw_token: str) -> User:
    """
    Complete an email change.

    ⚠️  Confirmation from both addresses together:

        1. A warning message to the **old** address — someone whose account was
           compromised learns of the attempt and can act.
        2. A confirmation code to the **new** address — proving the requester owns it.

        Sending to the new one alone means an attacker steals the account by
        silently changing its email and then resetting the password.
    """
    record = consume_token(raw_token, TokenPurpose.EMAIL_CHANGE)
    user = record.user
    new_email = (record.new_email or "").lower().strip()

    if not new_email:
        raise BusinessError(ErrorCode.TOKEN_INVALID)

    # Someone else may have registered with this email between the request and the confirmation
    if User.objects.filter(email__iexact=new_email).exclude(pk=user.pk).exists():
        raise BusinessError(
            ErrorCode.UNIQUE,
            detail="هذا البريد صار مسجلًا لحساب آخر",
            status_code=409,
        )

    previous = user.email
    user.email = new_email
    user.email_verified_at = timezone.now()
    user.save(update_fields=["email", "email_verified_at"])

    # Email is the identifier — changing it invalidates every session
    revoke_all_tokens(user)
    close_all_sessions(user, revoked=True)

    AuditLog.objects.create(
        actor=user,
        action=AuditAction.UPDATE,
        object_repr=str(user),
        changes={"email": {"old": previous, "new": new_email}},
    )
    return user


def issue_jwt(user: User) -> dict[str, str]:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def frontend_url(path: str) -> str:
    base = getattr(settings, "FRONTEND_BASE_URL", "").rstrip("/")
    return f"{base}/{path.lstrip('/')}"
