"""
Student prices follow the account type — or, when the owner switches it on, the ID card.

⚠️  The switch (`core.features.student_verification_enforced`) is **off by default**,
    and off must behave *exactly* as pricing did before the verification workflow
    existed: the account type alone selects the list. These tests pin both sides, and
    that turning it on withholds only the `STUDENT`-kind lists, only from an
    unverified student.
"""

from decimal import Decimal

import pytest

from accounts.models import AccountType, User, VerificationStatus
from core import features
from core.models.settings import SystemSetting
from pricing import services
from pricing.models import PriceList, PriceListKind

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


def make_user(
    email, account_type=AccountType.STUDENT, verification=VerificationStatus.NOT_REQUIRED
):
    user = User.objects.create_user(email=email, password=PASSWORD, account_type=account_type)
    user.is_active = True
    user.verification_status = verification
    user.save()
    return user


@pytest.fixture
def retail(db):
    return PriceList.objects.create(
        code="retail", name_ar="تجزئة", name_en="Retail", is_default=True
    )


@pytest.fixture
def student_list(db):
    return PriceList.objects.create(
        code="student",
        name_ar="طلاب",
        name_en="Student",
        kind=PriceListKind.STUDENT,
        account_types=[AccountType.STUDENT],
        priority=10,
    )


@pytest.fixture
def doctor_list(db):
    return PriceList.objects.create(
        code="pro",
        name_ar="مهنيون",
        name_en="Professional",
        kind=PriceListKind.PROFESSIONAL,
        account_types=[AccountType.DOCTOR],
        priority=5,
    )


@pytest.fixture
def enforced(db):
    SystemSetting.set(features.STUDENT_VERIFICATION_ENFORCED, True)


class TestSwitchOff:
    """The default — behaves exactly as before."""

    def test_the_switch_is_off_by_default(self):
        assert features.student_verification_enforced() is False

    @pytest.mark.parametrize(
        "verification",
        [
            VerificationStatus.NOT_REQUIRED,
            VerificationStatus.PENDING,
            VerificationStatus.REJECTED,
            VerificationStatus.VERIFIED,
        ],
    )
    def test_every_student_gets_the_student_list(self, retail, student_list, verification):
        student = make_user("s@test.local", verification=verification)

        assert services.resolve_price_list(student) == student_list


class TestSwitchOn:
    def test_an_unverified_student_falls_through_to_the_default(
        self, retail, student_list, enforced
    ):
        student = make_user("s@test.local")

        assert services.resolve_price_list(student) == retail

    @pytest.mark.parametrize(
        "verification", [VerificationStatus.PENDING, VerificationStatus.REJECTED]
    )
    def test_a_pending_or_rejected_student_is_withheld_too(
        self, retail, student_list, enforced, verification
    ):
        student = make_user("s@test.local", verification=verification)

        assert services.resolve_price_list(student) == retail

    def test_a_verified_student_keeps_the_student_list(self, retail, student_list, enforced):
        student = make_user("s@test.local", verification=VerificationStatus.VERIFIED)

        assert services.resolve_price_list(student) == student_list

    def test_other_account_types_are_not_affected(
        self, retail, student_list, doctor_list, enforced
    ):
        doctor = make_user("d@test.local", AccountType.DOCTOR)

        assert services.resolve_price_list(doctor) == doctor_list

    def test_a_student_list_is_not_picked_even_as_the_default(self, student_list, enforced):
        """The rule is about the *kind* of list, wherever it would have been chosen."""
        student_list.is_default = True
        student_list.save()
        student = make_user("s@test.local")

        assert services.resolve_price_list(student) is None

    def test_a_guest_and_no_user_are_unchanged(self, retail, student_list, enforced):
        assert services.resolve_price_list(None) == retail
        assert services.resolve_price_list() == retail

    def test_unverified_student_pays_the_default_price_in_a_priced_line(
        self, retail, student_list, enforced
    ):
        """End to end through `price_for`, not only the selector."""
        from catalog.models import Category, Product
        from pricing.models import PriceRule

        product = Product.objects.create(
            sku="G-1",
            name_ar="منتج",
            name_en="Product",
            category=Category.objects.create(name_ar="فئة", name_en="Category"),
            base_price=Decimal("100.00"),
        )
        PriceRule.objects.create(price_list=retail, product=product, unit_price=Decimal("100.00"))
        PriceRule.objects.create(
            price_list=student_list, product=product, unit_price=Decimal("75.00")
        )
        waiting = make_user("w@test.local", verification=VerificationStatus.PENDING)
        approved = make_user("a@test.local", verification=VerificationStatus.VERIFIED)

        assert services.price_for(product, 1, user=waiting).unit_price == Decimal("100.00")
        assert services.price_for(product, 1, user=approved).unit_price == Decimal("75.00")

    def test_turning_it_off_again_restores_the_student_list(self, retail, student_list):
        student = make_user("s@test.local")
        SystemSetting.set(features.STUDENT_VERIFICATION_ENFORCED, True)
        assert services.resolve_price_list(student) == retail

        SystemSetting.set(features.STUDENT_VERIFICATION_ENFORCED, False)

        assert services.resolve_price_list(student) == student_list
