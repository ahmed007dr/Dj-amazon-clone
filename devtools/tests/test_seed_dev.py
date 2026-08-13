"""
اختبارات بذرة التطوير.

⚠️  البذرة ليست بيانات تجميلية — إنها **أول ما يجرّبه أي مطوّر
    جديد**، وأول ما يبني عليه الفرونت إند شاشاته.

    بذرة تنكسر بصمت تعني ساعة ضائعة قبل كتابة سطر واحد؛ وبذرة
    تتضاعف عند التشغيل الثاني تعني أرقام مخزون كاذبة يُبنى عليها
    كل ما بعدها.
"""

from decimal import Decimal

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import AccountStatus, User, VerificationStatus
from catalog.models import Product
from devtools.seeds import people
from inventory.models import Batch, Stock, StockMovement
from orders.models import Order
from pricing.models import PriceList
from promotions.models import Coupon


@pytest.fixture
def dev_mode(settings):
    """
    ⚠️  Django يفرض `DEBUG=False` في الاختبارات دائمًا.

        وهو صحيح — لكنه يعني أن أي اختبار للبذرة يصطدم بحارسها.
        الرفع هنا مقصود ومحصور في هذه الاختبارات وحدها.
    """
    settings.DEBUG = True


@pytest.fixture
def seeded(db, dev_mode):
    call_command("seed_dev", verbosity=0)


# ═══════════════════════════════════════════════════════════
#  الأمان
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_refuses_to_run_outside_debug(settings):
    """
    ⚠️  البذرة تُنشئ حسابات بكلمة مرور معروفة ومنشورة.

        الحاجز الأول أن التطبيق غير مثبّت في الإنتاج؛ وهذا يمسك
        الحالة التي يُثبَّت فيها بالخطأ.
    """
    settings.DEBUG = False

    with pytest.raises(CommandError, match="التطوير"):
        call_command("seed_dev", verbosity=0)

    assert not User.objects.exists()


# ═══════════════════════════════════════════════════════════
#  التشغيل المتكرر
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_reset_clears_then_rebuilds(seeded):
    """
    ⚠️  `--reset` يحذف كل شيء.

        اختباره ليس ترفًا: مساره الفاشل يترك قاعدة نصف محذوفة
        بقيود مفاتيح أجنبية مكسورة — وهي أسوأ من قاعدة فارغة.
    """
    original_ids = set(Product.objects.values_list("id", flat=True))

    call_command("seed_dev", "--reset", verbosity=0)

    rebuilt_ids = set(Product.objects.values_list("id", flat=True))

    assert Product.objects.count() == len(original_ids)
    assert not (original_ids & rebuilt_ids), "الحذف لم يقع فعلًا"
    assert Order.objects.exists()


@pytest.mark.django_db
def test_running_twice_changes_nothing(seeded):
    """
    ⚠️  **الخاصية الأهم.**

        بذرة تُضاعف المخزون في كل تشغيل تجعل كل رقم بعدها كاذبًا —
        والاكتشاف يكون بعد أسابيع حين لا يطابق الجرد شيئًا.
    """
    before = {
        "products": Product.objects.count(),
        "users": User.objects.count(),
        "batches": Batch.objects.count(),
        "movements": StockMovement.objects.count(),
        "orders": Order.objects.count(),
        "physical": sum(Stock.objects.values_list("quantity_physical", flat=True)),
    }

    call_command("seed_dev", verbosity=0)

    after = {
        "products": Product.objects.count(),
        "users": User.objects.count(),
        "batches": Batch.objects.count(),
        "movements": StockMovement.objects.count(),
        "orders": Order.objects.count(),
        "physical": sum(Stock.objects.values_list("quantity_physical", flat=True)),
    }

    assert before == after


@pytest.mark.django_db
def test_minimal_seeds_structure_without_data(db, dev_mode):
    call_command("seed_dev", "--minimal", verbosity=0)

    from inventory.models import StockLocation
    from shipping.models import ShippingZone

    assert StockLocation.objects.exists()
    assert ShippingZone.objects.exists()
    assert not Product.objects.exists()
    assert not User.objects.exists()


# ═══════════════════════════════════════════════════════════
#  البيانات صالحة للعمل
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSeededData:
    def test_every_seeded_account_can_sign_in(self, seeded):
        """
        ⚠️  حساب مبذور بكلمة مرور لا تعمل أسوأ من غيابه — المطوّر
            يظن الخطأ في المصادقة لا في البذرة.
        """
        for user in User.objects.all():
            assert user.check_password(people.PASSWORD), user.email

    def test_suspended_account_exists_and_is_suspended(self, seeded):
        suspended = User.objects.get(email="suspended@dev.local")
        assert suspended.status == AccountStatus.SUSPENDED

    def test_verification_queue_is_not_empty(self, seeded):
        """طابور المراجعة اليدوية يجب أن يكون قابلًا للتجربة."""
        assert User.objects.filter(verification_status=VerificationStatus.PENDING).exists()
        assert User.objects.filter(verification_status=VerificationStatus.REJECTED).exists()

    def test_default_price_list_exists(self, seeded):
        assert PriceList.get_default() is not None

    def test_student_prices_are_independent_not_derived(self, seeded):
        """
        ⚠️  قاعدة العمل ٩ — قائمة منفصلة لا نسبة خصم.

            لو كانت نسبة لَكان سعر الطالب دالةً في سعر التجزئة؛
            هنا هو رقم مستقل يُدقَّق وحده.
        """
        student = PriceList.objects.get(code="student")
        rule = student.rules.get(product__sku="STE-CLS")

        assert rule.unit_price == Decimal("690.00")
        assert rule.unit_price != Product.objects.get(sku="STE-CLS").base_price

    def test_stock_movements_exist_for_every_batch(self, seeded):
        """
        ⚠️  دفعة بلا حركة تعني مخزونًا بسجل فارغ — أول جرد يكشف
            فرقًا لا يفسّره أحد. المرور بالخدمة يمنع ذلك.
        """
        assert Batch.objects.exists()
        for batch in Batch.objects.all():
            assert batch.movements.exists(), batch.number

    def test_edge_cases_are_present(self, seeded):
        """الحالات التي لا يراها أحد حتى يشتكي عميل."""
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.localdate()

        # دفعة منتهية بالفعل
        assert Batch.objects.filter(expires_at__lt=today).exists()
        # دفعة توشك — داخل نافذة التنبيه
        assert Batch.objects.filter(
            expires_at__gte=today, expires_at__lte=today + timedelta(days=90)
        ).exists()
        # كوبون منتهٍ
        assert Coupon.objects.filter(code="EXPIRED2025").exists()

    def test_a_variant_is_out_of_stock_while_its_product_is_not(self, seeded):
        """
        ⚠️  هذا هو الفرق الذي يجعل تتبّع المخزون على النسخة ضروريًا:
            المنتج «متوفر» ونسخة منه ليست كذلك.
        """
        from catalog.models import ProductVariant

        out_of_stock = ProductVariant.objects.get(sku="GLV-NIT-L")
        in_stock = ProductVariant.objects.get(sku="GLV-NIT-M")

        assert not Stock.objects.filter(variant=out_of_stock, quantity_physical__gt=0).exists()
        assert Stock.objects.filter(variant=in_stock, quantity_physical__gt=0).exists()

    def test_orders_cover_multiple_statuses(self, seeded):
        statuses = set(Order.objects.values_list("status", flat=True))
        assert len(statuses) >= 3

    def test_orders_carry_price_snapshots(self, seeded):
        """
        ⚠️  السطر بلا لقطة سعر يجعل كل فاتورة قديمة تتغيّر بتغيّر
            سعر المنتج اليوم. (ADR-30)
        """
        for order in Order.objects.all():
            for line in order.lines.all():
                assert line.product_sku
                assert line.product_name_ar
                assert line.unit_price > 0

    def test_orders_reserved_stock(self, seeded):
        """الطلب الذي لا يحجز مخزونًا يبيع ما ليس موجودًا."""
        assert Stock.objects.filter(quantity_reserved__gt=0).exists()

    def test_payment_providers_are_available(self, seeded):
        from payments import services
        from payments.models import PaymentMethodKind

        providers = services.available_providers(
            method=PaymentMethodKind.CASH_ON_DELIVERY,
            channel="ONLINE",
            amount=Decimal("300"),
        )
        assert providers

    def test_student_bundles_reference_real_products(self, seeded):
        from academic.models import StudyBundle

        for bundle in StudyBundle.objects.all():
            assert bundle.items.exists(), bundle.slug
