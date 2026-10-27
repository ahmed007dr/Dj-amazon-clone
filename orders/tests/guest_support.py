"""
Shared fixtures and helpers for the guest-checkout tests.

Loaded with `pytest_plugins` by the test modules that need a sellable public
product, a shipping method and a cash-on-delivery gateway (orders, notifications
and loyalty all test guest orders from their own side of the layer diagram).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.apps import apps
from django.urls import reverse
from rest_framework.test import APIClient

from access.models import AccessPolicy
from catalog.models import Category, Product
from core.models.tax import TaxClass
from inventory import services as inventory_services
from payments.models import PaymentMethodKind, PaymentProvider
from shipping.models import ShippingMethod, ShippingRate, ShippingZone

SESSION = "3f1c2b0e-8a52-4a0e-9f43-5b2e0c6a1d01"
PASSWORD = "Str0ng-Test-Pass!23"

FORM = {
    "recipient_name": "أحمد محمود",
    "phone": "01001234567",
    "email": "Ahmed.Buyer@Example.com",
    "governorate": "القاهرة",
    "city": "مدينة نصر",
    "street": "١٢ شارع التسعين، الدور الثالث",
    "shipping_method_code": "standard",
    "customer_note": "اتصل قبل الوصول",
    "language": "en",
}


# ═══════════════════════════════════════════════════════════
#  World
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def location(db):
    return apps.get_model("inventory", "StockLocation").objects.create(
        code="main", name_ar="الرئيسي", name_en="Main", is_default=True
    )


@pytest.fixture
def policies(db):
    from django.core.management import call_command

    call_command("seed_access_policies", verbosity=0)
    return {p.code: p for p in AccessPolicy.objects.all()}


@pytest.fixture
def tax_class(db):
    return TaxClass.objects.create(
        name_ar="قياسي", name_en="Standard", code="standard", rate=Decimal("14.00"), is_default=True
    )


@pytest.fixture
def shipping(db):
    zone = ShippingZone.objects.create(
        code="cairo", name_ar="القاهرة", name_en="Cairo", governorates=["القاهرة", "الجيزة"]
    )
    method = ShippingMethod.objects.create(code="standard", name_ar="عادي", name_en="Standard")
    ShippingRate.objects.create(zone=zone, method=method, base_fee=Decimal("30.00"))
    return method


@pytest.fixture
def cod(db):
    return PaymentProvider.objects.create(
        code="cod",
        adapter_key="cash_on_delivery",
        name_ar="دفع عند الاستلام",
        name_en="Cash on delivery",
        supported_methods=[PaymentMethodKind.CASH_ON_DELIVERY],
        is_active=True,
    )


@pytest.fixture
def category(db):
    return Category.objects.create(name_ar="فئة", name_en="Category")


def make_product(sku, category, policy, location, tax_class, stock=50):
    product = Product.objects.create(
        sku=sku,
        name_ar=f"منتج {sku}",
        name_en=f"Product {sku}",
        category=category,
        base_price=Decimal("100.00"),
        tax_class=tax_class,
        access_policy=policy,
    )
    inventory_services.receive(product, stock, Decimal("60.00"), location=location)
    return product


@pytest.fixture
def product(category, policies, location, tax_class):
    return make_product("G-001", category, policies["public"], location, tax_class)


@pytest.fixture
def world(product, shipping, cod):
    """A sellable public product, a shipping method and a COD gateway."""
    return product


def guest_client(session=SESSION):
    client = APIClient()
    client.credentials(HTTP_X_CART_SESSION=session)
    return client


def add_to_cart(client, product, quantity=1):
    response = client.post(
        reverse("v1:cart:lines"),
        {"product": str(product.pk), "quantity": quantity},
        format="json",
    )
    assert response.status_code == 201, response.data
    return response


def checkout(client, **overrides):
    body = {**FORM, **overrides}
    body = {k: v for k, v in body.items() if v is not None}
    return client.post(reverse("v1:orders:guest-checkout"), body, format="json")


def place(product, session=SESSION, quantity=1, **overrides):
    """Add to a guest cart and check out — returns (client, response)."""
    client = guest_client(session)
    add_to_cart(client, product, quantity)
    return client, checkout(client, **overrides)


def available(product):
    return inventory_services.available_quantity(product)
