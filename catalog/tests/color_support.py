"""
Shared builders for the colour tests.

Plain functions rather than a `conftest.py`: a conftest in this directory would
add fixtures to every older catalogue test, and the older ones define their own
`product` / `admin_client` with different shapes.
"""

from decimal import Decimal

from django.apps import apps
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from catalog import colors as color_services
from catalog.models import Category, Product
from core.testing import grant_all_domains

PASSWORD = "Str0ng-Test-Pass!23"


def make_admin_client(email: str = "color-admin@test.local") -> APIClient:
    admin = User.objects.create_user(email=email, password=PASSWORD, account_type=AccountType.ADMIN)
    admin.is_active = True
    admin.save()
    apps.get_model("administration", "AdminProfile").objects.create(user=admin)
    grant_all_domains(admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


def make_customer_client(
    email: str = "color-customer@test.local", account_type=AccountType.DOCTOR
) -> APIClient:
    user = User.objects.create_user(email=email, password=PASSWORD, account_type=account_type)
    user.is_active = True
    user.save()

    client = APIClient()
    client.force_authenticate(user=user)
    return client


def make_product(sku: str = "CLR-001", price: str = "100.00", **extra) -> Product:
    category = Category.objects.filter(slug="colors-cat").first() or Category.objects.create(
        slug="colors-cat", name_ar="ملابس", name_en="Apparel"
    )
    return Product.objects.create(
        sku=sku,
        name_ar=extra.pop("name_ar", "قميص سكراب"),
        name_en=extra.pop("name_en", "Scrub top"),
        category=category,
        base_price=Decimal(price),
        **extra,
    )


def add_color(product: Product, name_en: str = "Blue", name_ar: str | None = None, **extra):
    names = {"Blue": "أزرق", "Green": "أخضر", "Red": "أحمر", "Black": "أسود"}
    price = extra.pop("price_override", None)
    return color_services.create_color(
        product,
        name_ar=name_ar or names.get(name_en, name_en),
        name_en=name_en,
        hex=extra.pop("hex", "#1E40AF"),
        price_override=None if price is None else Decimal(str(price)),
        **extra,
    )
