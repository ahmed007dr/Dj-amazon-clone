"""
برامج الولاء والإحالة.

⚠️  **البرنامج يُبذر مُفعَّلًا والإحالة موقوفة — عمدًا.**

    الاثنان معًا مفعَّلين يخفيان أهم سلوك في النظام: أن الأدمن
    يشغّل ما يريد ويوقف ما لا يريد. برنامج موقوف في البذرة يجعل
    شاشة «مفتاح موقوف» حالةً تُرى في أول دقيقة من التطوير بدل أن
    تُكتشف في الإنتاج.

⚠️  وبرنامجان لا برنامج واحد.

    الثاني موجَّه للصيدليات وحدها، فيُختبر الاستهداف فعليًا: أيّ
    خطأ في `program_for` يظهر فورًا كصيدلية تكسب بمعدّل الطلاب أو
    العكس. برنامج واحد بلا استهداف يجعل المسار كله غير مُجرَّب.
"""

from decimal import Decimal

from loyalty.models import LoyaltyProgram, ReferralProgram, TierLevel

PROGRAMS = [
    {
        "code": "general",
        "name_ar": "نقاط المتجر",
        "name_en": "Store points",
        "defaults": {
            "is_active": True,
            # ⚠️  فارغ = الجميع: الحالة الافتراضية التي يبدأ بها
            #     أي متجر قبل أن يقرّر تضييقها.
            "account_types": [],
            "customer_segments": [],
            "currency_per_point": Decimal("10.00"),
            "point_value": Decimal("0.0500"),
            "min_order_amount": Decimal("50.00"),
            "expiry_months": 12,
            "max_redemption_percent": Decimal("30.00"),
            "note": "برنامج عام — نقطة لكل ١٠ ج، والنقطة ٥ قروش",
        },
        "tiers": [
            ("bronze", "برونزي", "Bronze", "0.00", "1.00", 1),
            ("silver", "فضي", "Silver", "5000.00", "1.25", 2),
            ("gold", "ذهبي", "Gold", "20000.00", "1.50", 3),
        ],
    },
    {
        # ⚠️  موقوف في البذرة: تفعيله من الشاشة هو أول ما يجرّبه
        #     من يفتح لوحة الولاء.
        "code": "pharmacies",
        "name_ar": "نقاط الصيدليات",
        "name_en": "Pharmacy points",
        "defaults": {
            "is_active": False,
            "account_types": ["PHARMACY", "WAREHOUSE"],
            "customer_segments": [],
            "currency_per_point": Decimal("25.00"),
            "point_value": Decimal("0.1000"),
            "min_order_amount": Decimal("500.00"),
            "expiry_months": 6,
            "max_redemption_percent": Decimal("20.00"),
            "note": "موقوف — للتجربة: فعّله لترى الاستهداف يعمل",
        },
        "tiers": [],
    },
]


def seed() -> dict:
    programs = {}
    tiers = 0

    for payload in PROGRAMS:
        program, _ = LoyaltyProgram.objects.update_or_create(
            code=payload["code"],
            defaults={
                "name_ar": payload["name_ar"],
                "name_en": payload["name_en"],
                **payload["defaults"],
            },
        )
        programs[program.code] = program

        for code, name_ar, name_en, threshold, multiplier, order in payload["tiers"]:
            TierLevel.objects.update_or_create(
                program=program,
                code=code,
                defaults={
                    "name_ar": name_ar,
                    "name_en": name_en,
                    "threshold": Decimal(threshold),
                    "multiplier": Decimal(multiplier),
                    "display_order": order,
                },
            )
            tiers += 1

    referral, _ = ReferralProgram.objects.update_or_create(
        code="friend",
        defaults={
            "name_ar": "أحضر صديقًا",
            "name_en": "Refer a friend",
            "is_active": True,
            "account_types": [],
            "referrer_points": 200,
            "referee_points": 100,
            # ⚠️  سقف منخفض في البذرة: بلوغه أثناء التطوير يكشف
            #     رسالة السقف، وهي رسالة لا تُرى أبدًا بسقف مفتوح.
            "max_referrals_per_user": 10,
            "min_order_amount": Decimal("100.00"),
        },
    )

    return {
        "programs": programs,
        "referral": referral,
        "counts": {"programs": len(programs), "tiers": tiers, "referral_programs": 1},
    }
