"""
Tax control tests.

⚠️  The approved business rule (2026-08-14):

        the rate is **variable**, and there may be **no tax at all** —
        for some products or for all of them.

    The tests here guard all three cases, and something more important still:
    that zero is **an explicit decision**, not the result of an absence or an oversight.

⚠️  They live in `pricing`, not `administration`, even though they exercise the admin API.

    The standing rule: **a test lives in the highest domain it touches.** And it
    touches three — `administration` (the interface), `catalog` (the product)
    and `pricing` (the calculation) — and `pricing` is the highest of them in
    the layer diagram. Putting them in `administration` makes it import what is
    above it, and `import-linter` genuinely refused it.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from administration.models import AdminProfile
from core.testing import grant_all_domains
from catalog.models import Category, Product
from core.models.settings import SystemSetting
from core.models.tax import TaxClass
from pricing import services as pricing

PASSWORD = "Str0ng-Test-Pass!23"


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_user(
        email="tax-admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    admin.is_active = True
    admin.save()
    AdminProfile.objects.create(user=admin)
    grant_all_domains(admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture
def standard(db):
    return TaxClass.objects.create(
        code="standard", name_ar="قياسي", name_en="Standard", rate=Decimal("14.00"), is_default=True
    )


@pytest.fixture
def exempt(db):
    return TaxClass.objects.create(
        code="exempt", name_ar="معفى", name_en="Exempt", rate=Decimal("0.00")
    )


@pytest.fixture
def category(db):
    return Category.objects.create(slug="c", name_ar="فئة", name_en="Category")


def make_product(category, tax_class=None, sku="SKU-1"):
    return Product.objects.create(
        sku=sku,
        name_ar="منتج",
        name_en="Product",
        category=category,
        base_price=Decimal("100.00"),
        tax_class=tax_class,
    )


@pytest.fixture(autouse=True)
def tax_enabled(db):
    SystemSetting.set("tax.enabled", True, value_type="BOOL", label_ar="ض", label_en="t")
    yield


# ═══════════════════════════════════════════════════════════
#  The rule's three cases
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestVariableTax:
    def test_rate_is_variable_per_class(self, standard, exempt, category):
        """A different rate per class — not a figure fixed in code."""
        taxed = make_product(category, standard, "T-1")
        free = make_product(category, exempt, "T-2")

        assert pricing.price_for(taxed).tax_rate == Decimal("14.00")
        assert pricing.price_for(free).tax_rate == Decimal("0.00")
        assert pricing.price_for(free).tax_amount == Decimal("0.00")

    def test_changing_a_rate_affects_only_future_pricing(self, standard, category):
        """
        ⚠️  The rate is **a snapshot**. (ADR-30)

            Changing it does not touch what was priced before it — or every old
            invoice would change with a new government decree.
        """
        product = make_product(category, standard)
        before = pricing.price_for(product)

        standard.rate = Decimal("15.00")
        standard.save()
        product.refresh_from_db()

        after = pricing.price_for(product)

        assert before.tax_rate == Decimal("14.00")
        assert after.tax_rate == Decimal("15.00")

    def test_tax_can_be_disabled_for_everything(self, standard, category):
        """"It may not exist … for any product" — a single switch."""
        product = make_product(category, standard)
        assert pricing.price_for(product).tax_amount > 0

        SystemSetting.set("tax.enabled", False, value_type="BOOL", label_ar="ض", label_en="t")

        priced = pricing.price_for(product)
        assert priced.tax_rate == Decimal("0.00")
        assert priced.tax_amount == Decimal("0.00")

    def test_a_product_without_a_class_uses_the_default(self, standard, category):
        """
        ⚠️  An empty field means "standard", not "exempt".

            And that is the correct default: most goods are taxable. Exemption
            is assigned explicitly through a zero-rate class — so an oversight
            never becomes an exemption.
        """
        product = make_product(category, None)
        assert pricing.price_for(product).tax_rate == Decimal("14.00")


# ═══════════════════════════════════════════════════════════
#  Zero is a decision, not an absence
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestZeroIsDeliberate:
    def test_expired_class_falls_back_instead_of_going_untaxed(self, standard, category):
        """
        ⚠️  **The trap that was fixed.**

            The admin sets `valid_to` when changing the rate and forgets to
            reclassify the products. The old behaviour made them all silently
            exempt — discovered only in a tax audit. And under-collecting is a
            legal liability, unlike over-collecting.
        """
        yesterday = timezone.localdate() - timedelta(days=1)
        old = TaxClass.objects.create(
            code="old-rate",
            name_ar="قديمة",
            name_en="Old",
            rate=Decimal("10.00"),
            valid_from=yesterday - timedelta(days=365),
            valid_to=yesterday,
        )
        product = make_product(category, old)

        priced = pricing.price_for(product)

        assert priced.tax_rate == Decimal("14.00"), "سقط إلى الافتراضية لا إلى الصفر"
        assert priced.tax_amount > 0

    def test_future_class_falls_back_too(self, standard, category):
        """A rate scheduled for next year does not make the product exempt today."""
        future = TaxClass.objects.create(
            code="next-year",
            name_ar="قادمة",
            name_en="Next",
            rate=Decimal("15.00"),
            valid_from=timezone.localdate() + timedelta(days=30),
        )
        product = make_product(category, future)

        assert pricing.price_for(product).tax_rate == Decimal("14.00")

    def test_explicit_zero_class_really_is_zero(self, standard, exempt, category):
        """An explicit exemption stays an exemption — it does not fall back to the default."""
        product = make_product(category, exempt)

        priced = pricing.price_for(product)
        assert priced.tax_rate == Decimal("0.00")
        assert priced.tax_class_code == "exempt"


# ═══════════════════════════════════════════════════════════
#  The admin interface
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestTaxAdminAPI:
    def test_admin_changes_the_rate_without_deploying(self, admin_client, standard, category):
        product = make_product(category, standard)
        assert pricing.price_for(product).tax_rate == Decimal("14.00")

        response = admin_client.patch(
            reverse("v1:administration:tax-class-detail", args=[standard.pk]),
            {"rate": "12.50"},
            format="json",
        )
        assert response.status_code == 200

        product.refresh_from_db()
        assert pricing.price_for(product).tax_rate == Decimal("12.50")

    def test_admin_disables_tax_entirely(self, admin_client, standard, category):
        product = make_product(category, standard)

        response = admin_client.put(
            reverse("v1:administration:tax-settings"),
            {
                "enabled": False,
                "prices_include_tax": False,
                "default_class": "standard",
                "rounding": "line",
            },
            format="json",
        )
        assert response.status_code == 200
        assert pricing.price_for(product).tax_amount == Decimal("0.00")

    def test_rate_change_is_audited_with_both_values(self, admin_client, standard):
        from core.models.audit import AuditLog

        admin_client.patch(
            reverse("v1:administration:tax-class-detail", args=[standard.pk]),
            {"rate": "16.00"},
            format="json",
        )

        entry = AuditLog.objects.filter(object_repr__contains="standard").first()
        assert entry is not None
        assert entry.changes["rate"] == {"old": "14.00", "new": "16.00"}

    def test_class_in_use_cannot_be_deleted(self, admin_client, standard, category):
        """Deleting it drops its products to a different rate with nobody intending it."""
        make_product(category, standard)

        response = admin_client.delete(
            reverse("v1:administration:tax-class-detail", args=[standard.pk])
        )
        assert response.status_code == 409
        assert TaxClass.objects.filter(pk=standard.pk).exists()

    def test_default_class_cannot_be_deleted(self, admin_client, standard):
        response = admin_client.delete(
            reverse("v1:administration:tax-class-detail", args=[standard.pk])
        )
        assert response.status_code == 409

    def test_inverted_validity_window_is_rejected(self, admin_client, standard):
        """An inverted period makes the class never effective — that is, a silent exemption."""
        today = timezone.localdate()
        response = admin_client.post(
            reverse("v1:administration:tax-classes"),
            {
                "code": "broken",
                "name_ar": "مكسورة",
                "name_en": "Broken",
                "rate": "5.00",
                "valid_from": str(today),
                "valid_to": str(today - timedelta(days=10)),
            },
            format="json",
        )
        assert response.status_code == 400

    def test_product_count_is_visible_before_editing(self, admin_client, standard, category):
        """Seeing the number of affected products turns the decision from a guess into knowledge."""
        make_product(category, standard, "P-1")
        make_product(category, standard, "P-2")

        response = admin_client.get(reverse("v1:administration:tax-classes"))
        row = next(item for item in response.data if item["code"] == "standard")
        assert row["product_count"] == 2

    def test_customer_cannot_touch_tax(self, standard):
        customer = User.objects.create_user(email="c-tax@test.local", password=PASSWORD)
        customer.is_active = True
        customer.save()

        client = APIClient()
        client.force_authenticate(user=customer)

        assert client.get(reverse("v1:administration:tax-settings")).status_code == 403
        assert (
            client.patch(
                reverse("v1:administration:tax-class-detail", args=[standard.pk]),
                {"rate": "0.00"},
                format="json",
            ).status_code
            == 403
        )
