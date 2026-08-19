"""
Business accounts and their credit limits.

⚠️  **Three credit situations, not one.**

    A single account with sound credit makes every test take the easy path: no
    limit exceeded · no overdue invoice · no expired licence. And those three
    situations are precisely what the blocking screens are built on — and are
    the ones never seen in development unless they are seeded.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from b2b.models import BusinessKind, BusinessProfile, CreditStatus

PROFILES = [
    {
        "email": "pharmacy@dev.local",
        "kind": BusinessKind.PHARMACY,
        "legal_name": "صيدلية النور",
        "license_number": "PH-2024-8891",
        "license_days": 400,
        "credit_status": CreditStatus.ACTIVE,
        "credit_limit": Decimal("50000.00"),
        "payment_terms_days": 30,
    },
    {
        # ⚠️  An expired licence — the state that blocks credit and does not block the sale
        "email": "trader@dev.local",
        "kind": BusinessKind.TRADER,
        "legal_name": "مؤسسة الشفاء للتجارة",
        "license_number": "TR-2022-1140",
        "license_days": -20,
        "credit_status": CreditStatus.ACTIVE,
        "credit_limit": Decimal("25000.00"),
        "payment_terms_days": 45,
    },
    {
        # ⚠️  No credit — the default state of any new account
        "email": "wholesale@dev.local",
        "kind": BusinessKind.WAREHOUSE,
        "legal_name": "مخزن الدلتا للأدوية",
        "license_number": "WH-2025-3320",
        "license_days": 700,
        "credit_status": CreditStatus.NONE,
        "credit_limit": Decimal("0.00"),
        "payment_terms_days": 0,
    },
]


def seed(users: dict) -> dict:
    """`users` is a `{email: User}` map from the people seed."""
    from customers.models import CustomerProfile

    businesses = {}
    today = timezone.localdate()

    # ⚠️  A business profile is for a business account only.
    #
    #     Giving one to an employee account — as genuinely happened with
    #     `warehouse@dev.local`, who is a warehouse employee rather than a
    #     warehouse — creates a meaningless row, and every B2B endpoint answers it with 403 because the account type does not match.
    from accounts.models import AccountType

    trade_types = {
        AccountType.PHARMACY,
        AccountType.WAREHOUSE,
        AccountType.TRADER,
        AccountType.SUPPLIER,
    }

    for payload in PROFILES:
        user = users.get(payload["email"])
        if user is None or user.account_type not in trade_types:
            continue

        customer, _ = CustomerProfile.objects.get_or_create(user=user)

        business, _ = BusinessProfile.objects.update_or_create(
            customer=customer,
            defaults={
                "kind": payload["kind"],
                "legal_name": payload["legal_name"],
                "license_number": payload["license_number"],
                "license_expires_on": today + timedelta(days=payload["license_days"]),
                "credit_status": payload["credit_status"],
                "credit_limit": payload["credit_limit"],
                "payment_terms_days": payload["payment_terms_days"],
            },
        )
        businesses[payload["email"]] = business

    return {"businesses": businesses, "counts": {"businesses": len(businesses)}}
