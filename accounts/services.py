"""
خدمات الهوية — الواجهة العامة الوحيدة لهذا النطاق.

النطاقات الأخرى تستدعي هذه الدوال ولا تلمس `models.py` مطلقًا.
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
#  إبطال الجلسة عند الإيقاف  (ADR-16)
# ═══════════════════════════════════════════════════════════
#
#  ⚠️  المشكلة: التوكن الصادر يبقى صالحًا حتى انتهاء عمره.
#      بلا معالجة، الموقوف يواصل العمل حتى ١٠ دقائق كاملة.
#
#  الحل ثلاثي الطبقات:
#      ١. عمر قصير للـ Access Token (١٠ دقائق) — في الإعدادات
#      ٢. قائمة سوداء للـ Refresh — تمنع التجديد
#      ٣. مجموعة الموقوفين في الكاش — تُفحص على كل طلب فالأثر **فوري**
#
#  الطبقة ٣ هي التي تجعل زر «إيقاف الحساب» حقيقيًا لا زخرفيًا.

SUSPENDED_CACHE_PREFIX = "suspended_user:"
SUSPENDED_CACHE_TTL = 60 * 60 * 24 * 7

#: مدة اعتبار المستخدم متصلًا — قابلة للضبط (قاعدة عمل ٣)
PRESENCE_WINDOW = timedelta(minutes=5)

#: صلاحية رموز الأمان
EMAIL_VERIFICATION_TTL = timedelta(hours=24)
PASSWORD_RESET_TTL = timedelta(minutes=45)


def _suspended_key(user_id) -> str:
    return f"{SUSPENDED_CACHE_PREFIX}{user_id}"


def is_suspended_cached(user_id) -> bool:
    """
    فحص O(1) يُستدعى في طبقة المصادقة على كل طلب.

    الكاش هو مصدر الحقيقة السريع؛ قاعدة البيانات هي الدائم.
    """
    return cache.get(_suspended_key(user_id)) is not None


def _mark_suspended(user_id) -> None:
    cache.set(_suspended_key(user_id), True, SUSPENDED_CACHE_TTL)


def _clear_suspended(user_id) -> None:
    cache.delete(_suspended_key(user_id))


def revoke_all_tokens(user: User) -> int:
    """
    إبطال كل Refresh Tokens للمستخدم. يعيد عدد ما أُبطل.

    الفشل على توكن واحد لا يوقف الباقي — توكن منتهٍ أو مُبطَل مسبقًا
    حالة متوقعة، والمهم أن يُبطَل كل ما هو صالح.
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
    إيقاف حساب — بأثر فوري.

    المالك (`AdminProfile.is_owner`) لا يُوقَف — وإلا أمكن قفل
    النظام على الجميع.
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

    _mark_suspended(user.pk)  # الطبقة ٣ — أثر فوري
    revoke_all_tokens(user)  # الطبقة ٢ — يمنع التجديد
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
#  الجلسات
# ═══════════════════════════════════════════════════════════


def device_type_from_user_agent(user_agent: str) -> str:
    """
    ⚠️  عامّة لا خاصة — `analytics` يصنّف أجهزة الزوار بها.

        نسخة ثانية من التصنيف كانت ستجعل جهازًا يُحسب «لوحيًا» في
        الجلسات و«هاتفًا» في تقرير الحركة.
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

    # ⚠️  الخروج يُسقط النبضة — وإلا بقي الخارج «متصلًا» حتى تنتهي
    #     النافذة، فيرى الأدمن خمسة متصلين وقد خرج ثلاثة منهم.
    #     والشرط مقصود: جهاز ثانٍ ما زال مفتوحًا يعني أن صاحبه متصل.
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
#  التواجد اللحظي  (ADR-17)
# ═══════════════════════════════════════════════════════════

PRESENCE_KEY = "presence:live"

#: النبضة لا تُكتب على كل طلب — مرة كل نصف دقيقة تكفي لنافذة الخمس.
PRESENCE_HEARTBEAT = timedelta(seconds=30)

#: السجل نفسه يخدم الزوار المجهولين في `analytics` — انظر `core.presence`.
presence = PresenceRegistry(PRESENCE_KEY, window=PRESENCE_WINDOW, heartbeat=PRESENCE_HEARTBEAT)


def touch_activity(user_id) -> None:
    """
    نبضة تواجد — **في الكاش لا في قاعدة البيانات**.

    ⚠️  كتابة `last_activity` على كل طلب تقتل القاعدة (ADR-17).
        `flush_presence` تفرّغ السجل إلى الجلسات كل دقيقة.

    ⚠️  والمفتاح **المستخدم لا الجلسة**: توكن الوصول لا يحمل معرّف
        جلسة الدخول، وربطه بها يحتاج ادعاءً جديدًا في التوكن —
        و«من متصل الآن» سؤال عن المستخدم أصلًا.
    """
    presence.touch(user_id)


def drop_presence(user_id) -> None:
    """إسقاط النبضة — عند الخروج أو الإبطال."""
    presence.drop(user_id)


def live_user_ids() -> set:
    """المتصلون من الكاش وحده — قبل أي تفريغ."""
    result = set()
    for identity in presence.identities():
        try:
            result.add(uuid.UUID(identity))
        except (AttributeError, ValueError):
            continue
    return result


def online_user_ids() -> list:
    """
    من متصل الآن — **اتحاد** الكاش وقاعدة البيانات.

    ⚠️  المصدران ليسا تكرارًا:

        الكاش يعرف النبضة التي لم تُفرَّغ بعد، والقاعدة تعرف جلسةً
        فُتحت قبل وصول أول نبضة (وتنجو من إعادة تشغيل الكاش).
        الاكتفاء بأحدهما يُسقط إحدى الحالتين.
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
    تفريغ سجل التواجد إلى `UserSession.last_activity` — مهمة كل دقيقة.

    ⚠️  الطوابع تُجمَّع بالدقيقة لا تُكتب فرديًا.

        دقة الثانية في «آخر ظهور» لا يقرأها أحد، والتجميع يجعل
        عدد التحديثات = عدد الدقائق المتميّزة لا عدد المتصلين.
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
        # ⚠️  `last_activity__lt` يمنع إرجاع طابع أحدث إلى الوراء
        updated += UserSession.objects.filter(
            user_id__in=user_ids, logout_at__isnull=True, last_activity__lt=stamp
        ).update(last_activity=stamp)

    return updated


# ═══════════════════════════════════════════════════════════
#  الرموز الأمنية
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
    يعيد `(السجل, الرمز الصريح)`.

    ⚠️  الرمز الصريح يُرسَل للمستخدم مرة واحدة **ولا يُخزَّن أبدًا**.
        المخزَّن بصمته فقط — تسريب القاعدة لا يمنح القدرة على
        إعادة تعيين كلمات المرور.
    """
    if ttl is None:
        ttl = (
            PASSWORD_RESET_TTL if purpose == TokenPurpose.PASSWORD_RESET else EMAIL_VERIFICATION_TTL
        )

    # رمز واحد صالح لكل غرض — إصدار جديد يُبطل السابق
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
    """يتحقق ويستهلك. يرفع `BusinessError` عند الفشل."""
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
    تعيين كلمة مرور جديدة.

    **إبطال كل الجلسات إجباري** — من عرف كلمة المرور القديمة
    يجب أن يفقد وصوله فورًا.
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
    إتمام تغيير البريد.

    ⚠️  التأكيد من العنوانين معًا:

        ١. رسالة تحذير للعنوان **القديم** — من اختُرق حسابه يعلم
           بالمحاولة ويستطيع التصرف.
        ٢. رمز تأكيد للعنوان **الجديد** — يثبت أن الطالب يملكه.

        الاكتفاء بالجديد يعني أن مهاجمًا يسرق الحساب بتغيير بريده
        بصمت ثم إعادة تعيين كلمة المرور.
    """
    record = consume_token(raw_token, TokenPurpose.EMAIL_CHANGE)
    user = record.user
    new_email = (record.new_email or "").lower().strip()

    if not new_email:
        raise BusinessError(ErrorCode.TOKEN_INVALID)

    # قد يكون شخص آخر سجّل بهذا البريد بين الطلب والتأكيد
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

    # البريد هو المعرّف — تغييره يبطل كل الجلسات
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
