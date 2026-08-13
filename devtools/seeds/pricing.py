"""
قوائم الأسعار وقواعدها والخصومات والكوبونات.

⚠️  **قائمة منفصلة للطلاب لا نسبة خصم** — قاعدة العمل ٩.

    الفارق ليس شكليًا: النسبة تجعل سعر الطالب مشتقًا من سعر
    التجزئة، فيستحيل تسعير صنف للطلاب بأقل من التكلفة ترويجيًا،
    ويستحيل تدقيق ما دفعه الطالب فعلًا بعد تغيّر السعر الأصلي.
"""

from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from accounts.models import AccountType
from pricing.models import DiscountKind, PriceList, PriceListKind, PriceOverride, PriceRule
from promotions.models import Coupon

PRICE_LISTS = [
    {
        "code": "retail",
        "name_ar": "أسعار التجزئة",
        "name_en": "Retail prices",
        "kind": PriceListKind.RETAIL,
        "account_types": [],
        "priority": 0,
        "is_default": True,
    },
    {
        "code": "student",
        "name_ar": "أسعار الطلاب",
        "name_en": "Student prices",
        "kind": PriceListKind.STUDENT,
        "account_types": [AccountType.STUDENT],
        "priority": 10,
        "is_default": False,
    },
    {
        "code": "wholesale",
        "name_ar": "أسعار الجملة",
        "name_en": "Wholesale prices",
        "kind": PriceListKind.WHOLESALE,
        "account_types": [
            AccountType.PHARMACY,
            AccountType.WAREHOUSE,
            AccountType.TRADER,
            AccountType.SUPPLIER,
        ],
        "priority": 20,
        "is_default": False,
    },
    {
        "code": "professional",
        "name_ar": "أسعار المهنيين",
        "name_en": "Professional prices",
        "kind": PriceListKind.PROFESSIONAL,
        "account_types": [AccountType.DOCTOR, AccountType.PHARMACIST],
        "priority": 15,
        "is_default": False,
    },
]

#: (رمز القائمة، SKU، الكمية الدنيا، سعر الوحدة)
#: ⚠️  شرائح الكمية **صفوف** لا حقول — أي عدد شرائح بلا هجرة
PRICE_RULES = [
    # ── التجزئة: السعر المرجعي هو الأساس، والاستثناءات هنا ──
    ("retail", "GLV-NIT", 1, "185.00"),
    ("retail", "GLV-NIT", 6, "172.00"),
    ("retail", "GLV-NIT", 12, "160.00"),
    ("retail", "MSK-SRG", 1, "45.00"),
    ("retail", "MSK-SRG", 10, "40.00"),
    ("retail", "SYR-3ML", 1, "1.75"),
    ("retail", "SYR-3ML", 100, "1.40"),
    # ── الطلاب: أسعار مستقلة لا مشتقّة ─────────────────────
    ("student", "STE-CLS", 1, "690.00"),
    ("student", "LAB-COAT", 1, "245.00"),
    ("student", "SCR-SET", 1, "365.00"),
    ("student", "DIS-KIT", 1, "195.00"),
    ("student", "BOK-ANA", 1, "410.00"),
    ("student", "GLV-NIT", 1, "165.00"),
    # ── الجملة ─────────────────────────────────────────────
    ("wholesale", "GZE-BULK", 1, "980.00"),
    ("wholesale", "GZE-BULK", 5, "910.00"),
    ("wholesale", "GLV-NIT", 12, "142.00"),
    ("wholesale", "GLV-NIT", 50, "128.00"),
    ("wholesale", "MSK-SRG", 20, "34.00"),
    ("wholesale", "SYR-3ML", 500, "1.10"),
    # ── المهنيون ───────────────────────────────────────────
    ("professional", "INS-PEN", 1, "148.00"),
    ("professional", "BPM-DIG", 1, "1320.00"),
]

#: (SKU، نوع الخصم، القيمة، عدد أيام السريان)
PRICE_OVERRIDES = [
    ("VTC-1000", DiscountKind.PERCENTAGE, "15.00", 21),
    ("THR-IRD", DiscountKind.FIXED, "60.00", 14),
    ("MSK-N95", DiscountKind.PERCENTAGE, "10.00", 30),
]

COUPONS = [
    {
        "code": "WELCOME10",
        "name_ar": "خصم الطلب الأول",
        "name_en": "First order discount",
        "kind": "PERCENTAGE",
        "value": Decimal("10.00"),
        # ⚠️  سقف إلزامي على الخصم النسبي.
        #
        #     «١٠٪ بلا سقف» على طلب جملة بعشرات الآلاف خسارةٌ لم
        #     يقصدها أحد — ويُكتشف بعد الشحن.
        "max_discount_amount": Decimal("50.00"),
        "min_order_amount": Decimal("200.00"),
        "first_order_only": True,
        "usage_limit_per_user": 1,
    },
    {
        "code": "FREESHIP",
        "name_ar": "شحن مجاني",
        "name_en": "Free shipping",
        "kind": "FREE_SHIPPING",
        "value": Decimal("0.00"),
        "min_order_amount": Decimal("300.00"),
        "usage_limit": 500,
        "usage_limit_per_user": 2,
    },
    {
        "code": "STUDENT50",
        "name_ar": "خصم الطلاب",
        "name_en": "Student discount",
        "kind": "FIXED",
        "value": Decimal("50.00"),
        "min_order_amount": Decimal("400.00"),
        "account_types": [AccountType.STUDENT],
        "usage_limit_per_user": 3,
    },
    {
        "code": "EXPIRED2025",
        "name_ar": "كوبون منتهٍ — للاختبار",
        "name_en": "Expired coupon — for testing",
        "kind": "PERCENTAGE",
        "value": Decimal("25.00"),
        "min_order_amount": Decimal("0.00"),
        # ⚠️  كوبون منتهٍ **مقصود**.
        #
        #     رسالة الرفض مسار لا يمرّ به أحد إلا حين يشتكي عميل.
        #     وجوده في البذرة يجعله قابلًا للتجربة في أول دقيقة.
        "_expired": True,
    },
]


def seed(products: dict):
    price_lists = {}
    for spec in PRICE_LISTS:
        payload = dict(spec)
        code = payload.pop("code")
        price_list, _created = PriceList.objects.update_or_create(
            code=code, defaults={**payload, "is_active": True}
        )
        price_lists[code] = price_list

    rules = 0
    for list_code, sku, min_quantity, unit_price in PRICE_RULES:
        if sku not in products:
            continue
        PriceRule.objects.update_or_create(
            price_list=price_lists[list_code],
            product=products[sku],
            variant=None,
            min_quantity=min_quantity,
            defaults={"unit_price": Decimal(unit_price), "is_active": True},
        )
        rules += 1

    now = timezone.now()
    overrides = 0
    for sku, kind, value, days in PRICE_OVERRIDES:
        if sku not in products:
            continue
        PriceOverride.objects.update_or_create(
            product=products[sku],
            variant=None,
            price_list=None,
            defaults={
                "discount_kind": kind,
                "discount_value": Decimal(value),
                "starts_at": now - timedelta(days=1),
                "ends_at": now + timedelta(days=days),
                "is_active": True,
            },
        )
        overrides += 1

    coupons = {}
    for spec in COUPONS:
        payload = dict(spec)
        code = payload.pop("code")
        expired = payload.pop("_expired", False)

        payload["starts_at"] = now - timedelta(days=90 if expired else 7)
        payload["ends_at"] = now - timedelta(days=30) if expired else now + timedelta(days=60)

        coupon, _created = Coupon.objects.update_or_create(
            code=code, defaults={**payload, "is_active": True}
        )
        coupons[code] = coupon

    return {
        "price_lists": price_lists,
        "coupons": coupons,
        "counts": {
            "price_lists": len(price_lists),
            "price_rules": rules,
            "price_overrides": overrides,
            "coupons": len(coupons),
        },
    }
