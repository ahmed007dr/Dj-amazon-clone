"""
Loyalty and referral programmes.

⚠️  **The programme is seeded enabled and the referral disabled — deliberately.**

    Both enabled together hide the most important behaviour in the system: that
    the admin turns on what they want and turns off what they do not. A disabled
    programme in the seed makes the "switch is off" screen a state seen in the
    first minute of development rather than discovered in production.

⚠️  And two programmes, not one.

    The second targets pharmacies alone, so targeting is genuinely exercised:
    any error in `program_for` shows up immediately as a pharmacy earning at the
    student rate or the reverse. A single programme with no targeting leaves the
    whole path untested.
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
            # ⚠️  Empty = everyone: the default state any store starts from
            #     before it decides to narrow it.
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
        # ⚠️  Disabled in the seed: enabling it from the screen is the first thing
        #     anyone opening the loyalty panel tries.
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
            # ⚠️  A low cap in the seed: reaching it during development reveals the
            #     cap message, which is never seen with an open ceiling.
            "max_referrals_per_user": 10,
            "min_order_amount": Decimal("100.00"),
        },
    )

    return {
        "programs": programs,
        "referral": referral,
        "counts": {"programs": len(programs), "tiers": tiers, "referral_programs": 1},
    }
