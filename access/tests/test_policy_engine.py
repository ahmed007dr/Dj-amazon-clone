"""
Access policy engine tests.

⚠️  **The full security matrix**: every account type × every policy.

    This is not coverage for its own sake — every cell in the matrix is a
    security decision. One wrong cell means a restricted product visible to
    someone not entitled to it, or a public product invisible to a real customer.
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
    """The standard policies."""
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
#  The security matrix
# ═══════════════════════════════════════════════════════════

#: (policy code, account type, verified?, allowed?)
MATRIX = [
    # ── Public: everyone ───────────────────────────────────
    ("public", None, False, True),  # guest
    ("public", AccountType.STUDENT, False, True),
    ("public", AccountType.PHARMACY, True, True),
    # ── Requires registration: any registered user, not a guest ──
    ("registered", None, False, False),
    ("registered", AccountType.STUDENT, False, True),
    ("registered", AccountType.DOCTOR, False, True),
    ("registered", AccountType.PHARMACY, False, True),
    # ── Students only ──────────────────────────────────────
    ("students", None, False, False),
    ("students", AccountType.STUDENT, False, True),
    ("students", AccountType.DOCTOR, True, False),
    ("students", AccountType.PHARMACY, True, False),
    # ── Verified professionals: the type **and** the verification together ──
    ("professionals", None, False, False),
    ("professionals", AccountType.STUDENT, True, False),  # verified but the wrong type
    ("professionals", AccountType.DOCTOR, False, False),  # the right type but unverified
    ("professionals", AccountType.DOCTOR, True, True),
    ("professionals", AccountType.PHARMACIST, True, True),
    ("professionals", AccountType.PHARMACY, True, True),
    ("professionals", AccountType.WAREHOUSE, True, False),
    # ── Pharmacies only ────────────────────────────────────
    ("pharmacy_only", AccountType.PHARMACY, True, True),
    ("pharmacy_only", AccountType.PHARMACY, False, False),
    ("pharmacy_only", AccountType.DOCTOR, True, False),
    ("pharmacy_only", AccountType.STUDENT, False, False),
    # ── Wholesale ──────────────────────────────────────────
    ("wholesale", AccountType.WAREHOUSE, True, True),
    ("wholesale", AccountType.TRADER, True, True),
    ("wholesale", AccountType.SUPPLIER, True, True),
    ("wholesale", AccountType.PHARMACY, True, True),
    ("wholesale", AccountType.TRADER, False, False),
    ("wholesale", AccountType.STUDENT, False, False),
    ("wholesale", AccountType.DOCTOR, True, False),
    # ── OTC medicine ───────────────────────────────────────
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
#  Denial reasons
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
#  Safe defaults
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSafeDefaults:
    def test_inactive_policy_denies_not_allows(self, policies):
        """
        ⚠️  Disabling a policy by mistake must not expose resources.

        "disabled ⟵ allowed" is a catastrophic assumption: whoever disables the
        restricted-medicines policy opens it to everyone instead of hiding it.
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
        # The default is "public"
        assert evaluate(user, None).allowed

    def test_no_policies_at_all_means_public(self, db):
        """A system with no policies = a public catalogue. Not a total lockout."""
        assert evaluate(Anonymous(), None).allowed


# ═══════════════════════════════════════════════════════════
#  The required permission
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
        user = User.objects.get(pk=user.pk)  # Reload — permissions are cached
        assert evaluate(user, policy).allowed


# ═══════════════════════════════════════════════════════════
#  Performance
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestQueryEfficiency:
    def test_accessible_ids_computed_once(self, policies, django_assert_max_num_queries):
        """
        ⚠️  The decision is computed once per user, not once per product.

        Evaluating each row means tens of thousands of evaluations on one page.
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
