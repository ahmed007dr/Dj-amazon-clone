"""
اختبارات محرك سياسات الوصول.

⚠️  **مصفوفة الأمان الكاملة**: كل نوع حساب × كل سياسة.

    هذه ليست تغطية شكلية — كل خانة في المصفوفة قرار أمني.
    خانة واحدة خاطئة تعني منتجًا مقيّدًا يظهر لمن لا يحق له،
    أو منتجًا عامًا يختفي عن عميل حقيقي.
"""

import pytest
from django.contrib.auth.models import Permission

from access.models import AccessLevel, AccessPolicy
from access.services import DenialReason, accessible_policy_ids, evaluate
from accounts.models import AccountType, User, VerificationStatus

PASSWORD = "Str0ng-Test-Pass!23"


def make_user(email: str, account_type: str, *, verified: bool = False) -> User:
    user = User.objects.create_user(
        email=email,
        password=PASSWORD,
        account_type=account_type,
        verification_status=(
            VerificationStatus.VERIFIED if verified else VerificationStatus.PENDING
        ),
    )
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def policies(db):
    """السياسات القياسية."""
    from django.core.management import call_command

    call_command("seed_access_policies", verbosity=0)
    return {p.code: p for p in AccessPolicy.objects.all()}


class Anonymous:
    is_authenticated = False
    account_type = AccountType.GUEST
    is_verified = False

    def has_perm(self, _p):
        return False


# ═══════════════════════════════════════════════════════════
#  مصفوفة الأمان
# ═══════════════════════════════════════════════════════════

#: (رمز السياسة, نوع الحساب, موثّق؟, مسموح؟)
MATRIX = [
    # ── عام: الجميع ────────────────────────────────────────
    ("public", None, False, True),  # زائر
    ("public", AccountType.STUDENT, False, True),
    ("public", AccountType.PHARMACY, True, True),
    # ── يتطلب تسجيل: أي مسجّل، لا الزائر ──────────────────
    ("registered", None, False, False),
    ("registered", AccountType.STUDENT, False, True),
    ("registered", AccountType.DOCTOR, False, True),
    ("registered", AccountType.PHARMACY, False, True),
    # ── طلاب فقط ──────────────────────────────────────────
    ("students", None, False, False),
    ("students", AccountType.STUDENT, False, True),
    ("students", AccountType.DOCTOR, True, False),
    ("students", AccountType.PHARMACY, True, False),
    # ── مهنيون موثّقون: النوع **و** التوثيق معًا ──────────
    ("professionals", None, False, False),
    ("professionals", AccountType.STUDENT, True, False),  # موثّق لكن نوعه خطأ
    ("professionals", AccountType.DOCTOR, False, False),  # نوعه صحيح لكن غير موثّق
    ("professionals", AccountType.DOCTOR, True, True),
    ("professionals", AccountType.PHARMACIST, True, True),
    ("professionals", AccountType.PHARMACY, True, True),
    ("professionals", AccountType.WAREHOUSE, True, False),
    # ── صيدليات فقط ───────────────────────────────────────
    ("pharmacy_only", AccountType.PHARMACY, True, True),
    ("pharmacy_only", AccountType.PHARMACY, False, False),
    ("pharmacy_only", AccountType.DOCTOR, True, False),
    ("pharmacy_only", AccountType.STUDENT, False, False),
    # ── جملة ──────────────────────────────────────────────
    ("wholesale", AccountType.WAREHOUSE, True, True),
    ("wholesale", AccountType.TRADER, True, True),
    ("wholesale", AccountType.SUPPLIER, True, True),
    ("wholesale", AccountType.PHARMACY, True, True),
    ("wholesale", AccountType.TRADER, False, False),
    ("wholesale", AccountType.STUDENT, False, False),
    ("wholesale", AccountType.DOCTOR, True, False),
    # ── دواء OTC ──────────────────────────────────────────
    ("otc_regulated", None, False, False),
    ("otc_regulated", AccountType.STUDENT, False, True),
    ("otc_regulated", AccountType.PHARMACY, True, True),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("policy_code", "account_type", "verified", "expected"), MATRIX)
def test_access_matrix(policies, policy_code, account_type, verified, expected):
    policy = policies[policy_code]

    if account_type is None:
        user = Anonymous()
        label = "زائر"
    else:
        user = make_user(
            f"{policy_code}-{account_type}@test.local", account_type, verified=verified
        )
        label = f"{account_type}{'/موثّق' if verified else ''}"

    result = evaluate(user, policy)

    assert result.allowed is expected, (
        f"[{policy_code}] × [{label}] "
        f"⟵ متوقع {'سماح' if expected else 'منع'}، والناتج "
        f"{'سماح' if result.allowed else f'منع ({result.reason})'}"
    )


# ═══════════════════════════════════════════════════════════
#  أسباب المنع
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestDenialReasons:
    def test_anonymous_on_registered(self, policies):
        result = evaluate(Anonymous(), policies["registered"])
        assert result.reason is DenialReason.AUTHENTICATION_REQUIRED

    def test_wrong_account_type(self, policies):
        user = make_user("wrong@test.local", AccountType.STUDENT)
        result = evaluate(user, policies["pharmacy_only"])
        assert result.reason is DenialReason.ACCOUNT_TYPE_NOT_ALLOWED

    def test_unverified_professional(self, policies):
        user = make_user("unverified@test.local", AccountType.DOCTOR, verified=False)
        result = evaluate(user, policies["professionals"])
        assert result.reason is DenialReason.VERIFICATION_REQUIRED

    def test_denial_message_follows_language(self, policies):
        from django.utils import translation

        user = make_user("lang@test.local", AccountType.STUDENT)

        with translation.override("ar"):
            assert "موثّق" in evaluate(user, policies["professionals"]).message
        with translation.override("en"):
            assert "verified" in evaluate(user, policies["professionals"]).message.lower()


# ═══════════════════════════════════════════════════════════
#  الافتراضات الآمنة
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSafeDefaults:
    def test_inactive_policy_denies_not_allows(self, policies):
        """
        ⚠️  تعطيل سياسة بالخطأ يجب ألا يكشف موارد.

        «معطّلة ⟵ مسموح» افتراض كارثي: من يعطّل سياسة الأدوية
        المقيّدة يفتحها للجميع بدل إخفائها.
        """
        policy = policies["pharmacy_only"]
        policy.is_active = False
        policy.save()

        user = make_user("pharm@test.local", AccountType.PHARMACY, verified=True)
        result = evaluate(user, policy)

        assert not result.allowed
        assert result.reason is DenialReason.POLICY_INACTIVE

    def test_no_policy_falls_back_to_default(self, policies):
        user = make_user("nopolicy@test.local", AccountType.STUDENT)
        # الافتراضية هي «عام»
        assert evaluate(user, None).allowed

    def test_no_policies_at_all_means_public(self, db):
        """نظام بلا سياسات = كتالوج عام. لا تعطيل كامل."""
        assert evaluate(Anonymous(), None).allowed


# ═══════════════════════════════════════════════════════════
#  الصلاحية المطلوبة
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPermissionRequirement:
    def test_policy_can_require_named_permission(self, policies):
        policy = AccessPolicy.objects.create(
            code="perm_gated",
            name_ar="يتطلب صلاحية",
            name_en="Permission gated",
            level=AccessLevel.REGISTERED,
            required_permission="access.view_accesspolicy",
        )

        user = make_user("noperm@test.local", AccountType.STUDENT)
        assert not evaluate(user, policy).allowed
        assert evaluate(user, policy).reason is DenialReason.PERMISSION_REQUIRED

        user.user_permissions.add(Permission.objects.get(codename="view_accesspolicy"))
        user = User.objects.get(pk=user.pk)  # إعادة تحميل — الصلاحيات مُخزَّنة
        assert evaluate(user, policy).allowed


# ═══════════════════════════════════════════════════════════
#  الأداء
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestQueryEfficiency:
    def test_accessible_ids_computed_once(self, policies, django_assert_max_num_queries):
        """
        ⚠️  القرار يُحسب مرة لكل مستخدم، لا مرة لكل منتج.

        تقييم كل صف يعني عشرات الآلاف من التقييمات في صفحة واحدة.
        """
        user = make_user("perf@test.local", AccountType.PHARMACY, verified=True)

        with django_assert_max_num_queries(3):
            ids = accessible_policy_ids(user)

        assert policies["public"].pk in ids
        assert policies["pharmacy_only"].pk in ids
        assert policies["students"].pk not in ids

    def test_student_cannot_see_professional_policies(self, policies):
        user = make_user("student@test.local", AccountType.STUDENT)
        ids = accessible_policy_ids(user)

        assert policies["public"].pk in ids
        assert policies["students"].pk in ids
        assert policies["professionals"].pk not in ids
        assert policies["pharmacy_only"].pk not in ids
        assert policies["wholesale"].pk not in ids
