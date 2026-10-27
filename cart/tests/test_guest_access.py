"""
A guest and the seeded access policies — add-to-cart and re-validation.

⚠️  Guest checkout lets a visitor *buy*. Owner decision: only PUBLIC products;
    everything else (registered, otc_regulated, students, professionals,
    pharmacy_only, wholesale) stays login-only exactly as today. The engine
    already denies a non-PUBLIC policy to anyone unauthenticated; these tests
    pin that for every seeded policy so a future change to `evaluate()` cannot
    quietly open a restricted product to a guest. (The checkout leg of the same
    matrix lives in `orders/tests/test_guest_checkout.py`.)
"""

from decimal import Decimal

import pytest
from django.apps import apps
from django.urls import reverse
from rest_framework.test import APIClient

from access.models import AccessPolicy
from cart.models import CartLine
from catalog.models import Category, Product
from inventory import services as inventory_services

KEY = "9a1d3a1e-0c64-4f58-8d63-0f1d2a5e0b01"

#: policy code -> may a guest buy it?
GUEST_MATRIX = {
    "public": True,
    "students": False,
    "professionals": False,
    "pharmacy_only": False,
    "wholesale": False,
    "registered": False,
    "otc_regulated": False,
}


@pytest.fixture
def world(db):
    from django.core.management import call_command

    call_command("seed_access_policies", verbosity=0)
    location = apps.get_model("inventory", "StockLocation").objects.create(
        code="main", name_ar="الرئيسي", name_en="Main", is_default=True
    )
    category = Category.objects.create(name_ar="فئة", name_en="Category")
    products = {}
    for code, policy in {p.code: p for p in AccessPolicy.objects.all()}.items():
        product = Product.objects.create(
            sku=f"POL-{code}",
            name_ar=f"منتج {code}",
            name_en=f"Product {code}",
            category=category,
            base_price=Decimal("100.00"),
            access_policy=policy,
        )
        inventory_services.receive(product, 20, Decimal("60.00"), location=location)
        products[code] = product
    return products


def test_the_matrix_covers_every_seeded_policy(world):
    assert set(GUEST_MATRIX) == set(world), "a seeded policy has no guest expectation"


@pytest.mark.django_db
@pytest.mark.parametrize(("code", "allowed"), list(GUEST_MATRIX.items()))
class TestGuestPerPolicy:
    def test_add_to_cart(self, world, code, allowed):
        response = APIClient().post(
            reverse("v1:cart:lines"),
            {"product": str(world[code].pk), "quantity": 1},
            format="json",
            HTTP_X_CART_SESSION=KEY,
        )

        if allowed:
            assert response.status_code == 201
        else:
            # 404, not 403 — the difference would list the restricted products
            assert response.status_code == 404
            assert not CartLine.objects.exists()

    def test_revalidation_flags_a_line_that_got_in_anyway(self, world, code, allowed):
        """
        A line can exist that the add-time check would now refuse (the policy
        tightened after it was added). The cart must show it and close checkout.
        """
        guest = APIClient()
        guest.get(reverse("v1:cart:detail"), HTTP_X_CART_SESSION=KEY)  # opens the cart
        from cart.models import Cart

        CartLine.objects.create(cart=Cart.objects.get(session_key=KEY), product=world[code])

        response = guest.get(reverse("v1:cart:detail"), HTTP_X_CART_SESSION=KEY)

        assert response.status_code == 200
        assert response.data["is_checkoutable"] is allowed
        if not allowed:
            assert [i["code"] for i in response.data["issues"]] == ["PRODUCT_ACCESS_DENIED"]
