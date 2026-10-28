"""
Fixtures for the coupon analytics tests: a hand-built shop with known numbers.

⚠️  `orders` sits above `promotions` in the layer contract, so its models are
    resolved by name through the app registry — the same way the production
    analytics reads them. A test that imported `orders.models` would break the
    contract it is testing.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.apps import apps
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from catalog.models import Category, Product
from core.testing import grant_all_domains
from customers.models import CustomerProfile
from promotions.models import Coupon, CouponRedemption

PASSWORD = "Str0ng-Test-Pass!23"


def order_model():
    return apps.get_model("orders", "Order")


def line_model():
    return apps.get_model("orders", "OrderLine")


def make_user(email: str, *, name: str = "") -> User:
    user = User.objects.create_user(email=email, password=PASSWORD, first_name=name)
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def admin_client(db):
    admin = make_user("promo-analytics-admin@test.local")
    admin.account_type = AccountType.ADMIN
    admin.save()
    apps.get_model("administration", "AdminProfile").objects.create(user=admin)
    grant_all_domains(admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture
def customer_client(db):
    client = APIClient()
    client.force_authenticate(user=make_user("not-staff@test.local"))
    return client


@pytest.fixture
def category(db):
    return Category.objects.create(slug="analytics-cat", name_ar="فئة", name_en="Cat")


@pytest.fixture
def other_category(db):
    return Category.objects.create(slug="analytics-other", name_ar="أخرى", name_en="Other")


@pytest.fixture
def p1(db, category):
    return Product.objects.create(
        sku="AN-1", name_ar="منتج واحد", name_en="One", category=category, base_price=Decimal("100")
    )


@pytest.fixture
def p2(db, other_category):
    return Product.objects.create(
        sku="AN-2",
        name_ar="منتج اثنان",
        name_en="Two",
        category=other_category,
        base_price=Decimal("50"),
    )


def make_coupon(code="DRX10", **overrides) -> Coupon:
    fields = {
        "name_ar": code,
        "name_en": code,
        "kind": "PERCENTAGE",
        "value": Decimal("10"),
        "starts_at": timezone.now() - timedelta(days=60),
    }
    fields.update(overrides)
    return Coupon.objects.create(code=code, **fields)


def make_order(
    coupon: Coupon,
    user: User,
    lines: list[tuple],
    *,
    coupon_discount: str,
    line_discount: str = "0.00",
    shipping: str = "0.00",
    status: str = "DELIVERED",
    payment_status: str = "PAID",
    days_ago: int = 0,
    redemption_cancelled: bool = False,
):
    """
    A coupon order with the same money invariants the real checkout writes:

        subtotal       = Σ unit_price × qty
        discount_total = line discounts + coupon discount
        grand_total    = subtotal − discount_total + shipping      (no tax in these tests)

    `lines` = [(product, quantity, unit_price, line_discount), ...]
    """
    profile, _ = CustomerProfile.objects.get_or_create(
        user=user, defaults={"display_name_ar": user.first_name}
    )
    subtotal = sum((Decimal(price) * qty for _p, qty, price, _d in lines), Decimal("0"))
    line_total = sum((Decimal(d) for _p, _q, _pr, d in lines), Decimal("0"))
    discount_total = line_total + Decimal(coupon_discount)

    order = order_model().objects.create(
        customer=profile,
        status=status,
        payment_status=payment_status,
        subtotal=subtotal,
        discount_total=discount_total,
        coupon_discount=Decimal(coupon_discount),
        shipping_total=Decimal(shipping),
        grand_total=subtotal - discount_total + Decimal(shipping),
        coupon_code=coupon.code,
    )
    for product, quantity, price, discount in lines:
        line_model().objects.create(
            order=order,
            product=product,
            product_sku=product.sku,
            product_name_ar=product.name_ar,
            product_name_en=product.name_en,
            quantity=quantity,
            unit_price=Decimal(price),
            discount_amount=Decimal(discount),
        )

    redemption = CouponRedemption.objects.create(
        coupon=coupon,
        user=user,
        discount_amount=Decimal(coupon_discount),
        order_amount=order.grand_total,
        reference_type="order",
        reference_id=str(order.pk),
        is_cancelled=redemption_cancelled,
    )

    if days_ago:
        moment = timezone.now() - timedelta(days=days_ago)
        order_model().objects.filter(pk=order.pk).update(created_at=moment)
        CouponRedemption.objects.filter(pk=redemption.pk).update(created_at=moment)

    return order


@pytest.fixture
def scenario(db, p1, p2):
    """
    One coupon, six orders, every number known in advance.

        order  status      pay     lines                         coupon  counts?
        O1     DELIVERED   PAID    P1 2×100, P2 1×50              25.00   yes
        O2     PENDING     UNPAID  P1 1×100 (line discount 10)     9.00   yes
        O3     CANCELLED   UNPAID  P1 1×100                      10.00   no (cancelled)
        O4     REFUNDED    PAID    P1 2×100                      20.00   no (refunded)
        O5     PENDING     FAILED  P2 2×50                       10.00   no (payment failed)
        O6     DELIVERED   PAID    P2 4×50, 40 days ago           20.00   yes (outside 30d)
    """
    coupon = make_coupon(holder_name="Dr. Test", holder_note="gave at the conference")
    users = [make_user(f"buyer{i}@test.local", name=f"Buyer{i}") for i in range(1, 5)]
    u1, u2, u3, u4 = users

    orders = {
        "O1": make_order(
            coupon,
            u1,
            [(p1, 2, "100", "0"), (p2, 1, "50", "0")],
            coupon_discount="25.00",
            shipping="20.00",
        ),
        "O2": make_order(
            coupon,
            u2,
            [(p1, 1, "100", "10")],
            coupon_discount="9.00",
            status="PENDING",
            payment_status="UNPAID",
        ),
        "O3": make_order(
            coupon,
            u3,
            [(p1, 1, "100", "0")],
            coupon_discount="10.00",
            status="CANCELLED",
            payment_status="UNPAID",
            redemption_cancelled=True,
        ),
        "O4": make_order(
            coupon,
            u4,
            [(p1, 2, "100", "0")],
            coupon_discount="20.00",
            status="REFUNDED",
        ),
        "O5": make_order(
            coupon,
            u4,
            [(p2, 2, "50", "0")],
            coupon_discount="10.00",
            status="PENDING",
            payment_status="FAILED",
        ),
        "O6": make_order(
            coupon,
            u3,
            [(p2, 4, "50", "0")],
            coupon_discount="20.00",
            days_ago=40,
        ),
    }
    return coupon, orders
