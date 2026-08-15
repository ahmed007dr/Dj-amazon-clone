"""
الحسابات التجارية وحدودها الائتمانية.

⚠️  **ثلاث حالات ائتمانية لا واحدة.**

    حساب واحد بائتمان سليم يجعل كل اختبار يمرّ بالمسار السهل: لا
    تجاوز حد · لا فاتورة متأخرة · لا ترخيص منتهٍ. والحالات الثلاث
    هي بالضبط ما تُبنى عليه شاشات المنع — وهي التي لا تُرى في
    التطوير إن لم تُبذَر.
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
        # ⚠️  ترخيص منتهٍ — الحالة التي تمنع الآجل ولا تمنع البيع
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
        # ⚠️  بلا ائتمان — الحالة الافتراضية لأي حساب جديد
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
    """`users` خريطة `{email: User}` من بذرة الأشخاص."""
    from customers.models import CustomerProfile

    businesses = {}
    today = timezone.localdate()

    # ⚠️  الملف التجاري لحساب تجاري فقط.
    #
    #     منحه لحساب موظف — كما وقع فعلًا مع `warehouse@dev.local`
    #     الذي هو موظف مخزن لا مخزن — يُنشئ صفًّا لا معنى له،
    #     وتردّ عليه كل نقاط B2B بـ٤٠٣ لأن نوع الحساب لا يطابق.
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
