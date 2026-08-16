"""
محرك تقييم سياسات الوصول.

⚠️  المبدأ الحاكم: **إخفاء الواجهة ليس أمنًا.**

    الفلترة تحدث في الـ **queryset** لا في الـ serializer ولا في
    المكوّن. المستخدم غير المصرّح له لا يستطيع:

        عرض · بحث · فلترة · إضافة لقائمة الرغبات · إضافة للسلة ·
        إتمام شراء · وصولًا بالرابط المباشر · تلاعبًا بالـ API

    نقطة واحدة تُقرِّر، والجميع يستهلك قرارها. تكرار المنطق في
    عدة أماكن يعني ثغرة عند أول تعديل يُنسى في أحدها.
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
    سبب المنع — للتشخيص ولاختيار الرسالة المعروضة.

    ⚠️  لا يُكشف للمستخدم إلا حين يكون كشف وجود المورد مقبولًا.
        للموارد التي يجب إخفاء وجودها أصلًا، الرد `404` موحّد.
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
#  التقييم
# ═══════════════════════════════════════════════════════════


def evaluate(user, policy: AccessPolicy | None) -> AccessResult:
    """
    القرار المركزي. **كل** فحص وصول يمر من هنا.

    `policy=None` ⟵ السياسة الافتراضية، وإن غابت فالمورد عام.
    """
    if policy is None:
        policy = AccessPolicy.get_default()
        if policy is None:
            return ALLOWED

    if not policy.is_active:
        # سياسة معطّلة ⟵ منع لا سماح.
        # الافتراض الآمن: تعطيل سياسة بالخطأ يجب ألا يكشف موارد.
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
    معرّفات السياسات المسموحة لهذا المستخدم.

    ⚠️  تُحسب **مرة واحدة** ثم تُستخدم في `filter(policy_id__in=...)`.

        البديل — تقييم كل صف على حدة — يعني تقييمًا لكل منتج في كل
        صفحة. عدد السياسات عشرات، وعدد المنتجات عشرات الآلاف.
    """
    return [
        policy.pk
        for policy in AccessPolicy.objects.filter(is_active=True)
        if evaluate(user, policy).allowed
    ]


def selectable_policies() -> list[AccessPolicy]:
    """
    السياسات التي يجوز إسنادها إلى مورد — لشاشات الأدمن.

    ⚠️  الواجهة العامة لهذا النطاق هي `services` وحدها؛ والنطاقات
        الأخرى تستدعيها ولا تلمس `models`.

    ⚠️  والافتراضية **أولًا** لا مرتّبة أبجديًا.

        هي جواب «للجميع» وهو الاختيار الصحيح لمعظم المنتجات. دفنها
        وسط القائمة يجعل الأدمن يختار من أعلى الظاهر — فيقيّد منتجًا
        عامًا بلا قصد، ولا يكتشف ذلك إلا بشكوى عميل لا يرى الصنف.
    """
    return list(
        AccessPolicy.objects.filter(is_active=True).order_by("-is_default", "level", "code")
    )


def accessible_filter(user, field: str = "access_policy") -> Q:
    """
    مرشِّح جاهز للدمج في أي queryset.

        Product.objects.filter(access.accessible_filter(user))

    يشمل الموارد بلا سياسة صريحة إن كانت الافتراضية مسموحة —
    وإلا استُبعدت.
    """
    condition = Q(**{f"{field}_id__in": accessible_policy_ids(user)})

    default_policy = AccessPolicy.get_default()
    default_allowed = default_policy is None or evaluate(user, default_policy).allowed
    if default_allowed:
        condition |= Q(**{f"{field}__isnull": True})

    return condition


class PolicyAwareQuerySetMixin:
    """
    يُدمج في أي view يقدّم موارد محكومة بسياسة.

        class ProductListAPI(PolicyAwareQuerySetMixin, ListAPIView):
            policy_field = "access_policy"

            def get_base_queryset(self):
                return Product.objects.filter(is_active=True)

    ⚠️  الفلترة في الـ queryset — لا في الـ serializer.

        الفلترة في الـ serializer تعني أن الصف يُقرأ من قاعدة
        البيانات ثم يُخفى: العدّ يبقى خاطئًا، والترقيم يعطي صفحات
        ناقصة، ووجود المورد يتسرّب من فارق الأعداد.

    ⚠️  **الفلاتر المخصصة تُكتب في `get_base_queryset` لا `get_queryset`.**

        تجاوز `get_queryset` في صنف فرعي **يُعطّل فلترة السياسات
        بصمت** — لا خطأ، ولا تحذير، فقط منتجات مقيّدة تظهر للجميع.
        وهو خطأ وقعنا فيه فعلًا وأمسكته الاختبارات.

        لذا `get_queryset` هنا `final` عمليًا: يستدعي
        `get_base_queryset` ثم يطبّق الفلتر دائمًا.
    """

    policy_field = "access_policy"

    def get_access_user(self):
        """
        نقطة الامتداد الوحيدة لتحديد «مَن يقيَّم».

        `access.preview.PreviewAwareMixin` يتجاوزها ليعيد مستخدمًا
        وهميًا — فلا يحتاج تجاوز `get_queryset` ولا يفلتر مرتين.
        """
        return getattr(self.request, "user", None)

    def get_base_queryset(self):
        """
        الـ queryset قبل فلترة السياسات.

        **هنا** تُكتب الفلاتر والترتيب والبحث — لا في `get_queryset`.
        """
        return super().get_queryset()

    def get_queryset(self):
        return self.get_base_queryset().filter(
            accessible_filter(self.get_access_user(), self.policy_field)
        )


def require_access(user, policy: AccessPolicy | None, *, reveal_existence: bool = False):
    """
    يرفع استثناءً عند المنع.

    `reveal_existence=False` (الافتراضي) ⟵ **`404`**.

        الرد `403` يؤكد وجود المورد. على كتالوج مقيّد، الفارق بين
        `403` و`404` يكشف قائمة المنتجات المقيّدة بالكامل.

    `reveal_existence=True` ⟵ `403` برسالة السياسة، للحالات التي
    يكون فيها وجود المورد معلومًا أصلًا (منتج ظهر في نتيجة عامة
    ثم قُيّد الشراء عليه).
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
