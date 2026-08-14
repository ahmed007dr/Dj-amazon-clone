"""
اختبارات التحكم بالضريبة.

⚠️  قاعدة العمل المُعتمدة (2026-08-14):

        النسبة **متغيّرة**، وقد **لا توجد ضريبة أصلًا** —
        لبعض المنتجات أو لكلها.

    الاختبارات هنا تحرس الحالات الثلاث، وتحرس ما هو أهم منها:
    أن الصفر **قرار صريح** لا نتيجة غياب أو سهو.

⚠️  مكانها `pricing` لا `administration` رغم أنها تختبر واجهة الأدمن.

    القاعدة المعتمدة: **الاختبار يسكن في أعلى نطاق يلمسه.** وهو
    يلمس ثلاثة — `administration` (الواجهة) و`catalog` (المنتج)
    و`pricing` (الحساب) — و`pricing` أعلاها في مخطط الطبقات.
    وضعها في `administration` يجعله يستورد ما هو فوقه، وقد رفضه
    `import-linter` فعلًا.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from administration.models import AdminProfile
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
#  الحالات الثلاث للقاعدة
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestVariableTax:
    def test_rate_is_variable_per_class(self, standard, exempt, category):
        """نسبة مختلفة لكل فئة — لا رقم مثبَّت في الكود."""
        taxed = make_product(category, standard, "T-1")
        free = make_product(category, exempt, "T-2")

        assert pricing.price_for(taxed).tax_rate == Decimal("14.00")
        assert pricing.price_for(free).tax_rate == Decimal("0.00")
        assert pricing.price_for(free).tax_amount == Decimal("0.00")

    def test_changing_a_rate_affects_only_future_pricing(self, standard, category):
        """
        ⚠️  النسبة **لقطة**. (ADR-30)

            تغييرها لا يمسّ ما سُعِّر قبلها — وإلا تغيّرت كل فاتورة
            قديمة بقرار حكومي جديد.
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
        """«قد لا تكون موجودة … لكل المنتجات» — مفتاح واحد."""
        product = make_product(category, standard)
        assert pricing.price_for(product).tax_amount > 0

        SystemSetting.set("tax.enabled", False, value_type="BOOL", label_ar="ض", label_en="t")

        priced = pricing.price_for(product)
        assert priced.tax_rate == Decimal("0.00")
        assert priced.tax_amount == Decimal("0.00")

    def test_a_product_without_a_class_uses_the_default(self, standard, category):
        """
        ⚠️  الحقل الفارغ يعني «قياسي» لا «معفى».

            وهو الافتراضي الصحيح: أغلب السلع خاضعة. الإعفاء يُسنَد
            صراحةً بفئة نسبتها صفر — فلا يصير سهوٌ إعفاءً.
        """
        product = make_product(category, None)
        assert pricing.price_for(product).tax_rate == Decimal("14.00")


# ═══════════════════════════════════════════════════════════
#  الصفر قرار لا غياب
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestZeroIsDeliberate:
    def test_expired_class_falls_back_instead_of_going_untaxed(self, standard, category):
        """
        ⚠️  **الفخّ الذي أُصلح.**

            الأدمن يضبط `valid_to` عند تغيير النسبة وينسى إعادة
            تصنيف المنتجات. السلوك القديم كان يجعلها كلها معفاة
            بصمت — ولا يُكتشف إلا في مراجعة ضريبية. ونقص التحصيل
            مسؤولية قانونية بخلاف زيادته.
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
        """نسبة مجدولة للعام القادم لا تجعل المنتج معفى اليوم."""
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
        """الإعفاء الصريح يبقى إعفاءً — لا يسقط إلى الافتراضية."""
        product = make_product(category, exempt)

        priced = pricing.price_for(product)
        assert priced.tax_rate == Decimal("0.00")
        assert priced.tax_class_code == "exempt"


# ═══════════════════════════════════════════════════════════
#  واجهة الأدمن
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
        """حذفها يسقط منتجاتها إلى نسبة أخرى بلا أن يقصد أحد ذلك."""
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
        """فترة مقلوبة تجعل الفئة غير سارية أبدًا — أي إعفاءً صامتًا."""
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
        """رؤية عدد المنتجات المتأثرة تحوّل القرار من تخمين إلى معرفة."""
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
