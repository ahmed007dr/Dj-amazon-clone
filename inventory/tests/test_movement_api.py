"""
نقاط حركات المخزون عبر HTTP.

⚠️  الخدمات مختبَرة في `test_inventory.py`. المختبَر هنا هو **العقد
    الذي تعتمد عليه شاشة الأدمن**: شكل الحمولة، والصلاحية، والرفض
    الذي يجب أن يصل إلى الواجهة رسالةً على حقل لا انهيارًا.

⚠️  و`administration` يُوصَل إليه بـ `apps.get_model` — هو و`inventory`
    لا يستورد أحدهما الآخر.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.apps import apps
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from catalog.models import Category, Product
from inventory import services
from inventory.models import LocationKind, MovementType, StockLocation, StockMovement

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


@pytest.fixture
def location(db):
    return StockLocation.objects.create(
        code="main", name_ar="المخزن الرئيسي", name_en="Main", is_default=True
    )


@pytest.fixture
def branch(db):
    return StockLocation.objects.create(
        code="branch-1", name_ar="فرع ١", name_en="Branch 1", kind=LocationKind.BRANCH
    )


@pytest.fixture
def product(db):
    category = Category.objects.create(name_ar="فئة", name_en="Category")
    return Product.objects.create(
        sku="MOV-001", name_ar="منتج", name_en="Product", category=category
    )


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_user(
        email="admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    admin.is_active = True
    admin.save()
    apps.get_model("administration", "AdminProfile").objects.create(user=admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture
def customer_client(db):
    customer = User.objects.create_user(email="c@test.local", password=PASSWORD)
    customer.is_active = True
    customer.save()

    client = APIClient()
    client.force_authenticate(user=customer)
    return client


# ═══════════════════════════════════════════════════════════
#  الاستلام
# ═══════════════════════════════════════════════════════════


class TestReceive:
    def test_receiving_creates_a_batch_and_raises_the_balance(
        self, admin_client, product, location
    ):
        response = admin_client.post(
            reverse("v1:inventory:receive"),
            {
                "product": str(product.pk),
                "location": str(location.pk),
                "quantity": 40,
                "unit_cost": "12.50",
                "expires_at": (timezone.localdate() + timedelta(days=365)).isoformat(),
                "supplier_batch_number": "SUP-9",
            },
            format="json",
        )

        assert response.status_code == 201
        assert services.available_quantity(product, location) == 40

    def test_unit_cost_is_required(self, admin_client, product, location):
        """
        ⚠️  بلا تكلفة الوحدة يستحيل حساب الربح لاحقًا — والرفض هنا
            أرخص من قيد تكلفة صفري يمرّ إلى قائمة الأرباح.
        """
        response = admin_client.post(
            reverse("v1:inventory:receive"),
            {"product": str(product.pk), "quantity": 10},
            format="json",
        )

        assert response.status_code == 400
        assert "unit_cost" in response.data["fields"]

    def test_location_may_be_omitted(self, admin_client, product, location):
        """أغلب المنشآت لها مخزن واحد — وإجبار اختياره خطوة بلا قرار."""
        response = admin_client.post(
            reverse("v1:inventory:receive"),
            {"product": str(product.pk), "quantity": 5, "unit_cost": "3.00"},
            format="json",
        )

        assert response.status_code == 201
        assert services.available_quantity(product, location) == 5


# ═══════════════════════════════════════════════════════════
#  التسوية
# ═══════════════════════════════════════════════════════════


class TestAdjust:
    def test_negative_quantity_reduces_the_balance(self, admin_client, product, location):
        services.receive(product, 100, Decimal("10.00"), location=location)

        response = admin_client.post(
            reverse("v1:inventory:adjust"),
            {
                "product": str(product.pk),
                "location": str(location.pk),
                "quantity": -3,
                "reason": "جرد أغسطس — فرق ثلاث علب",
            },
            format="json",
        )

        assert response.status_code == 201
        assert services.available_quantity(product, location) == 97

    def test_reason_is_required(self, admin_client, product, location):
        """تسوية بلا سبب ثغرة في الجرد: الفرق يظهر بعد شهر بلا تفسير."""
        services.receive(product, 10, Decimal("1.00"), location=location)

        response = admin_client.post(
            reverse("v1:inventory:adjust"),
            {"product": str(product.pk), "quantity": -1},
            format="json",
        )

        assert response.status_code == 400
        assert "reason" in response.data["fields"]

    def test_zero_is_refused(self, admin_client, product, location):
        response = admin_client.post(
            reverse("v1:inventory:adjust"),
            {"product": str(product.pk), "quantity": 0, "reason": "بلا معنى"},
            format="json",
        )

        assert response.status_code == 400
        assert "quantity" in response.data["fields"]

    def test_the_old_figure_survives_in_the_log(self, admin_client, product, location):
        """
        ⚠️  التسوية **لا تكتب فوق** الرصيد: تُسجَّل حركةً بسببها،
            ويبقى «كم كان قبلها» مقروءًا في `balance_after`.
        """
        services.receive(product, 50, Decimal("2.00"), location=location)

        admin_client.post(
            reverse("v1:inventory:adjust"),
            {"product": str(product.pk), "quantity": -5, "reason": "كسر في الرف"},
            format="json",
        )

        movement = StockMovement.objects.filter(
            product=product, movement_type=MovementType.ADJUSTMENT_DOWN
        ).first()

        assert movement is not None
        assert movement.balance_after == 45
        assert "كسر" in movement.note


# ═══════════════════════════════════════════════════════════
#  التحويل والتلف
# ═══════════════════════════════════════════════════════════


class TestTransferAndDamage:
    def test_transfer_moves_the_quantity_between_locations(
        self, admin_client, product, location, branch
    ):
        services.receive(product, 30, Decimal("5.00"), location=location)

        response = admin_client.post(
            reverse("v1:inventory:transfer"),
            {
                "product": str(product.pk),
                "from_location": str(location.pk),
                "to_location": str(branch.pk),
                "quantity": 12,
            },
            format="json",
        )

        assert response.status_code == 201
        assert services.available_quantity(product, location) == 18
        assert services.available_quantity(product, branch) == 12

    def test_transfer_to_the_same_location_is_refused(self, admin_client, product, location):
        services.receive(product, 10, Decimal("5.00"), location=location)

        response = admin_client.post(
            reverse("v1:inventory:transfer"),
            {
                "product": str(product.pk),
                "from_location": str(location.pk),
                "to_location": str(location.pk),
                "quantity": 1,
            },
            format="json",
        )

        assert response.status_code == 400

    def test_damage_leaves_availability(self, admin_client, product, location):
        services.receive(product, 20, Decimal("5.00"), location=location)

        response = admin_client.post(
            reverse("v1:inventory:damage"),
            {
                "product": str(product.pk),
                "location": str(location.pk),
                "quantity": 4,
                "reason": "كسر أثناء النقل",
            },
            format="json",
        )

        assert response.status_code == 201
        assert services.available_quantity(product, location) == 16


# ═══════════════════════════════════════════════════════════
#  السجل والصلاحية
# ═══════════════════════════════════════════════════════════


class TestLogAndPermissions:
    def test_every_command_leaves_a_movement(self, admin_client, product, location, branch):
        """**كل تغيير في المخزون يترك حركة. بلا استثناء.**"""
        admin_client.post(
            reverse("v1:inventory:receive"),
            {"product": str(product.pk), "quantity": 10, "unit_cost": "1.00"},
            format="json",
        )
        admin_client.post(
            reverse("v1:inventory:adjust"),
            {"product": str(product.pk), "quantity": -2, "reason": "جرد"},
            format="json",
        )
        admin_client.post(
            reverse("v1:inventory:damage"),
            {"product": str(product.pk), "quantity": 1, "reason": "كسر"},
            format="json",
        )

        response = admin_client.get(reverse("v1:inventory:movements"))
        kinds = {row["movement_type"] for row in response.data["results"]}

        assert {"RECEIPT", "ADJUSTMENT_DOWN", "DAMAGE"} <= kinds

    def test_the_log_records_who_did_it(self, admin_client, product, location):
        """«من غيّر الرصيد» هو نصف الجواب عن «أين ذهبت الخمسون علبة؟»."""
        admin_client.post(
            reverse("v1:inventory:receive"),
            {"product": str(product.pk), "quantity": 3, "unit_cost": "1.00"},
            format="json",
        )

        response = admin_client.get(reverse("v1:inventory:movements"))
        assert response.data["results"][0]["performed_by_email"] == "admin@test.local"

    def test_the_log_can_be_filtered_by_type(self, admin_client, product, location):
        services.receive(product, 10, Decimal("1.00"), location=location)
        services.mark_damaged(product, 2, location=location, reason="كسر")

        response = admin_client.get(reverse("v1:inventory:movements"), {"type": "DAMAGE"})
        kinds = {row["movement_type"] for row in response.data["results"]}

        assert kinds == {"DAMAGE"}

    @pytest.mark.parametrize(
        "endpoint,body",
        [
            ("v1:inventory:receive", {"quantity": 1, "unit_cost": "1.00"}),
            ("v1:inventory:adjust", {"quantity": 1, "reason": "محاولة"}),
            ("v1:inventory:damage", {"quantity": 1, "reason": "محاولة"}),
        ],
    )
    def test_customers_cannot_move_stock(self, customer_client, product, endpoint, body):
        """
        ⚠️  حركة المخزون بيد الأدمن وحده — وعميل يستطيع تسجيل
            «استلام» يخلق بضاعة من العدم في كل تقرير.
        """
        response = customer_client.post(
            reverse(endpoint), {"product": str(product.pk), **body}, format="json"
        )

        assert response.status_code == 403
        assert not StockMovement.objects.filter(product=product).exists()

    def test_customers_cannot_read_the_log(self, customer_client):
        """السجل يكشف حجم النشاط ومعدّل الدوران — رقم تجاري لا يُعطى."""
        assert customer_client.get(reverse("v1:inventory:movements")).status_code == 403
