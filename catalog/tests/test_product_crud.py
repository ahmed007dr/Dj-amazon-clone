"""
إنشاء المنتجات وحذفها واسترجاعها من بوابة الأدمن.

⚠️  هذه العمليات كانت متاحة عبر الـ API ولوحة Django وحدهما، ولم
    يكن لها طريق من لوحة الأدمن. الاختبارات هنا تحرس **العقد** الذي
    تعتمد عليه الشاشة: خيارات النموذج، والفلاتر، والحذف الناعم
    القابل للاسترجاع.

⚠️  و`administration` يُوصَل إليه بـ `apps.get_model` لا بالاستيراد —
    هو و`catalog` صنوان مستقلان في نفس الطبقة.
"""

from decimal import Decimal

import pytest
from django.apps import apps
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from catalog.models import Category, Product, ProductKind

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


@pytest.fixture
def category(db):
    return Category.objects.create(name_ar="مستلزمات", name_en="Supplies")


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


def draft(category, **overrides) -> dict:
    body = {
        "sku": "NEW-001",
        "name_ar": "شاش طبي",
        "name_en": "Medical gauze",
        "kind": ProductKind.SUPPLY,
        "category": str(category.pk),
        "base_price": "35.00",
    }
    body.update(overrides)
    return body


# ═══════════════════════════════════════════════════════════
#  الإنشاء
# ═══════════════════════════════════════════════════════════


class TestCreate:
    def test_admin_creates_a_product(self, admin_client, category):
        response = admin_client.post(
            reverse("v1:catalog:admin-products"), draft(category), format="json"
        )

        assert response.status_code == 201
        product = Product.objects.get(sku="NEW-001")
        assert product.name_ar == "شاش طبي"
        assert product.category_id == category.pk

    def test_slug_is_generated_not_supplied(self, admin_client, category):
        """
        ⚠️  `slug` للقراءة فقط — تغييره يكسر الروابط الخارجية
            وفهرسة محركات البحث. وإرساله يجب أن يُتجاهَل لا أن يُقبل.
        """
        response = admin_client.post(
            reverse("v1:catalog:admin-products"),
            draft(category, slug="attacker-chosen"),
            format="json",
        )

        assert response.status_code == 201
        assert Product.objects.get(sku="NEW-001").slug != "attacker-chosen"

    def test_duplicate_sku_is_refused(self, admin_client, category):
        """رمز مكرر يعني صنفين على رفّ واحد لا يميّزهما الماسح."""
        admin_client.post(reverse("v1:catalog:admin-products"), draft(category), format="json")

        response = admin_client.post(
            reverse("v1:catalog:admin-products"),
            draft(category, name_ar="آخر"),
            format="json",
        )

        assert response.status_code == 400
        assert "sku" in response.data["fields"]

    def test_creation_is_written_to_the_audit_log(self, admin_client, category):
        admin_client.post(reverse("v1:catalog:admin-products"), draft(category), format="json")

        entry = (
            apps.get_model("core", "AuditLog")
            .objects.filter(action="CREATE", object_repr__contains="NEW-001")
            .first()
        )
        assert entry is not None

    def test_customer_cannot_create(self, category):
        customer = User.objects.create_user(email="c@test.local", password=PASSWORD)
        customer.is_active = True
        customer.save()

        client = APIClient()
        client.force_authenticate(user=customer)

        response = client.post(reverse("v1:catalog:admin-products"), draft(category), format="json")
        assert response.status_code == 403
        assert not Product.objects.filter(sku="NEW-001").exists()


# ═══════════════════════════════════════════════════════════
#  الحذف والاسترجاع
# ═══════════════════════════════════════════════════════════


class TestDeleteAndRestore:
    def test_deleted_product_can_be_restored(self, admin_client, category):
        """
        ⚠️  الحذف الناعم بلا استرجاع حذفٌ نهائي من منظور المستخدم —
            وأول سؤال بعد حذف بالخطأ هو «كيف أرجعه؟».
        """
        product = Product.objects.create(
            sku="DEL-001", name_ar="صنف", name_en="Item", category=category
        )

        admin_client.delete(reverse("v1:catalog:admin-product-detail", args=[product.pk]))
        assert not Product.objects.filter(pk=product.pk).exists()

        response = admin_client.post(reverse("v1:catalog:admin-product-restore", args=[product.pk]))

        assert response.status_code == 200
        assert Product.objects.filter(pk=product.pk).exists()

    def test_restoring_a_live_product_is_a_conflict(self, admin_client, category):
        product = Product.objects.create(
            sku="LIVE-001", name_ar="صنف", name_en="Item", category=category
        )

        response = admin_client.post(reverse("v1:catalog:admin-product-restore", args=[product.pk]))
        assert response.status_code == 409

    def test_deleted_products_are_hidden_unless_asked_for(self, admin_client, category):
        product = Product.objects.create(
            sku="DEL-002", name_ar="صنف", name_en="Item", category=category
        )
        product.delete()

        hidden = admin_client.get(reverse("v1:catalog:admin-products"))
        assert [row["sku"] for row in hidden.data["results"]] == []

        shown = admin_client.get(reverse("v1:catalog:admin-products"), {"include_deleted": "true"})
        assert [row["sku"] for row in shown.data["results"]] == ["DEL-002"]

    def test_deleted_product_leaves_the_public_catalog(self, admin_client, category):
        product = Product.objects.create(
            sku="PUB-9", name_ar="صنف", name_en="Item", category=category
        )
        admin_client.delete(reverse("v1:catalog:admin-product-detail", args=[product.pk]))

        public = APIClient().get(reverse("v1:catalog:products"))
        assert [row["sku"] for row in public.data["results"]] == []


# ═══════════════════════════════════════════════════════════
#  الفلاتر
# ═══════════════════════════════════════════════════════════


class TestFilters:
    def test_status_filter_actually_filters(self, admin_client, category):
        """
        ⚠️  **انحدار**: الواجهة ترسل `is_active` وكان الخادم يقرأ
            `inactive` وحده — فيمرّ الفلتر بلا أثر والشاشة تعرض
            «مفعّل» بينما النتائج تشمل الموقوف.

            الفلتر الذي لا يفلتر أسوأ من غيابه، لأنه يُصدَّق.
        """
        Product.objects.create(
            sku="ON-1", name_ar="مفعّل", name_en="On", category=category, is_active=True
        )
        Product.objects.create(
            sku="OFF-1", name_ar="موقوف", name_en="Off", category=category, is_active=False
        )

        url = reverse("v1:catalog:admin-products")

        on = admin_client.get(url, {"is_active": "true"})
        off = admin_client.get(url, {"is_active": "false"})

        assert [row["sku"] for row in on.data["results"]] == ["ON-1"]
        assert [row["sku"] for row in off.data["results"]] == ["OFF-1"]

    def test_barcode_search_is_exact(self, admin_client, category):
        """الماسح يرسل رقمًا كاملًا — والمطابقة الجزئية تعيد صنفًا آخر."""
        Product.objects.create(
            sku="BC-1",
            name_ar="صنف",
            name_en="Item",
            category=category,
            barcode="6221033000012",
        )

        response = admin_client.get(
            reverse("v1:catalog:admin-products"), {"search": "6221033000012"}
        )
        assert [row["sku"] for row in response.data["results"]] == ["BC-1"]


# ═══════════════════════════════════════════════════════════
#  خيارات النموذج
# ═══════════════════════════════════════════════════════════


class TestFormOptions:
    def test_options_carry_every_list_the_form_needs(self, admin_client, category):
        response = admin_client.get(reverse("v1:catalog:admin-product-options"))

        assert response.status_code == 200
        for key in (
            "kinds",
            "regulatory_classes",
            "dosage_forms",
            "storage_conditions",
            "categories",
            "brands",
            "manufacturers",
        ):
            assert key in response.data, key

        assert response.data["kinds"][0].keys() == {"value", "label"}

    def test_categories_hidden_from_the_menu_are_still_selectable(self, admin_client):
        """
        ⚠️  `show_in_menu` تصنيف **عرضي** لا تصنيف صلاحية.

            نقطة الفئات العامة تُصفّي به، والاعتماد عليها هنا كان
            يمنع الأدمن من إسناد منتج إلى فئة موجودة فعلًا.
        """
        hidden = Category.objects.create(
            name_ar="فئة داخلية", name_en="Internal", show_in_menu=False
        )

        response = admin_client.get(reverse("v1:catalog:admin-product-options"))
        ids = {row["id"] for row in response.data["categories"]}

        assert str(hidden.pk) in ids

    def test_category_label_shows_the_full_path(self, admin_client, category):
        """«أقراص» وحدها غامضة حين توجد تحت «أدوية» و«مكمّلات» معًا."""
        child = Category.objects.create(name_ar="شاش", name_en="Gauze", parent=category)

        response = admin_client.get(reverse("v1:catalog:admin-product-options"))
        labels = {row["id"]: row["path_label"] for row in response.data["categories"]}

        assert labels[str(child.pk)] == "مستلزمات ← شاش"

    def test_customer_cannot_read_options(self, category):
        customer = User.objects.create_user(email="c2@test.local", password=PASSWORD)
        customer.is_active = True
        customer.save()

        client = APIClient()
        client.force_authenticate(user=customer)

        assert client.get(reverse("v1:catalog:admin-product-options")).status_code == 403


# ═══════════════════════════════════════════════════════════
#  التعديل
# ═══════════════════════════════════════════════════════════


class TestUpdate:
    def test_partial_update_leaves_untouched_fields_alone(self, admin_client, category):
        """
        ⚠️  الشاشة ترسل الحقول المعروضة وحدها؛ وحقول SEO ليست منها.
            الحفظ يجب ألا يمسحها.
        """
        product = Product.objects.create(
            sku="UPD-1",
            name_ar="قديم",
            name_en="Old",
            category=category,
            base_price=Decimal("10.00"),
            meta_title_ar="عنوان أرشفة",
        )

        response = admin_client.patch(
            reverse("v1:catalog:admin-product-detail", args=[product.pk]),
            {"name_ar": "جديد", "base_price": "12.50"},
            format="json",
        )

        assert response.status_code == 200
        product.refresh_from_db()
        assert product.name_ar == "جديد"
        assert product.base_price == Decimal("12.50")
        assert product.meta_title_ar == "عنوان أرشفة"
