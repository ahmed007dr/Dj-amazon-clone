"""
اختبارات إدارة الكتالوج من بوابة الأدمن.

⚠️  `catalog` و`administration` **صنوان مستقلان** في نفس الطبقة —
    لا يستورد أحدهما الآخر بأي اتجاه.

    الاختبار يحتاج `AdminProfile` لبناء عميل أدمن، فيصل إليه بـ
    `apps.get_model` — بحث نصي في سجل التطبيقات لا استيراد،
    فلا ينشئ تبعية يرصدها import-linter.

    نفس التقنية المستخدمة في `core/tests/test_foundations.py`.
"""

from decimal import Decimal

import pytest
from django.apps import apps
from django.urls import reverse
from rest_framework.test import APIClient

from access.models import AccessPolicy
from accounts.models import AccountType, User
from catalog.models import Category, Product, ProductKind

PASSWORD = "Str0ng-Test-Pass!23"


@pytest.fixture
def policies(db):
    from django.core.management import call_command

    call_command("seed_access_policies", verbosity=0)
    return {p.code: p for p in AccessPolicy.objects.all()}


@pytest.fixture
def category(db):
    return Category.objects.create(name_ar="مستلزمات", name_en="Supplies")


@pytest.fixture
def catalog(policies, category):
    return {
        "public": Product.objects.create(
            sku="PUB-001",
            name_ar="قفازات",
            name_en="Gloves",
            category=category,
            base_price=Decimal("50.00"),
            access_policy=policies["public"],
        ),
        "restricted": Product.objects.create(
            sku="RES-001",
            name_ar="دواء مقيّد",
            name_en="Restricted",
            category=category,
            kind=ProductKind.MEDICINE,
            base_price=Decimal("120.00"),
            access_policy=policies["pharmacy_only"],
            regulatory_class="OTC",
        ),
    }


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_user(
        email="admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    admin.is_active = True
    admin.save()
    # مرجع نصي — لا استيراد يكسر عزل النطاقين
    apps.get_model("administration", "AdminProfile").objects.create(user=admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.mark.django_db
class TestAdminCatalog:
    def test_admin_sees_restricted_products(self, admin_client, catalog):
        """الأدمن يدير كل المنتجات بما فيها المقيّدة."""
        response = admin_client.get(reverse("v1:catalog:admin-products"))

        skus = {p["sku"] for p in response.data["results"]}
        assert skus == {"PUB-001", "RES-001"}

    def test_customer_cannot_reach_admin_catalog(self, catalog):
        customer = User.objects.create_user(email="c@test.local", password=PASSWORD)
        customer.is_active = True
        customer.save()

        client = APIClient()
        client.force_authenticate(user=customer)
        assert client.get(reverse("v1:catalog:admin-products")).status_code == 403

    def test_delete_is_soft(self, admin_client, catalog):
        """المنتج المباع تشير إليه طلبات تاريخية وحركات مخزون."""
        product = catalog["public"]

        response = admin_client.delete(
            reverse("v1:catalog:admin-product-detail", args=[product.pk])
        )
        assert response.status_code == 204

        assert not Product.objects.filter(pk=product.pk).exists()
        assert Product.all_objects.filter(pk=product.pk).exists()

    def test_prescription_flag_must_match_regulatory_class(self, admin_client, category):
        """
        ⚠️  منتج يتطلب وصفة وتصنيفه OTC تناقض صامت — يظهر عند أول
            مراجعة تنظيمية لا قبلها.
        """
        response = admin_client.post(
            reverse("v1:catalog:admin-products"),
            {
                "sku": "BAD-001",
                "name_ar": "متناقض",
                "name_en": "Contradictory",
                "category": str(category.pk),
                "kind": "MEDICINE",
                "requires_prescription": True,
                "regulatory_class": "OTC",
                "base_price": "10.00",
            },
            format="json",
        )

        assert response.status_code == 400
        assert "regulatory_class" in response.data["fields"]

    def test_medicine_requires_regulatory_class(self, admin_client, category):
        response = admin_client.post(
            reverse("v1:catalog:admin-products"),
            {
                "sku": "MED-001",
                "name_ar": "دواء",
                "name_en": "Medicine",
                "category": str(category.pk),
                "kind": "MEDICINE",
                "regulatory_class": "NOT_APPLICABLE",
                "base_price": "10.00",
            },
            format="json",
        )
        assert response.status_code == 400
