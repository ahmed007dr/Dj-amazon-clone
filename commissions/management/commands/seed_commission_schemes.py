"""
Seed the standard commission schemes.

    python manage.py seed_commission_schemes

⚠️  **A recommendation, not a decision — business rule 15 is not settled.**

    The rates below are graduated tiers on net sales, and they are the
    recommendation written in the decision log. What matters architecturally is
    that they are **data**: editable from the panel with no deployment.

⚠️  And the top tier has **no ceiling**.

    A written ceiling makes someone who achieved 500% match no tier at all, so
    they come out with zero commission as a reward for the best month of their life.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from commissions.models import CommissionBase, CommissionScheme, CommissionTier

#: (from %, to % or None, commission rate %)
TIERS = [
    (Decimal("0"), Decimal("50"), Decimal("0")),
    (Decimal("50"), Decimal("80"), Decimal("1")),
    (Decimal("80"), Decimal("100"), Decimal("2")),
    (Decimal("100"), None, Decimal("3")),
]

SCHEMES = [
    {
        "code": "sales-standard",
        "name_ar": "عمولة المبيعات القياسية",
        "name_en": "Standard sales commission",
        "base": CommissionBase.NET_SALES,
        "role_code": "sales-rep",
    },
    {
        # ⚠️  The senior rep is paid on **profit**, not sales.
        #
        #     A rep rewarded on sales alone sells the low-margin items at a
        #     discount — their number rises and the store's profit falls.
        "code": "senior-profit",
        "name_ar": "عمولة المندوب الأول — على الربح",
        "name_en": "Senior commission — on profit",
        "base": CommissionBase.GROSS_PROFIT,
        "role_code": "senior-sales",
    },
]


class Command(BaseCommand):
    help = "بذر خطط العمولة — قابل للتشغيل مرارًا"

    @transaction.atomic
    def handle(self, *args, **options):
        from employees.models import EmployeeRole

        created = 0

        for payload in SCHEMES:
            role = EmployeeRole.objects.filter(code=payload["role_code"]).first()

            scheme, was_created = CommissionScheme.objects.update_or_create(
                code=payload["code"],
                defaults={
                    "name_ar": payload["name_ar"],
                    "name_en": payload["name_en"],
                    "base": payload["base"],
                    "role": role,
                },
            )
            created += int(was_created)

            # ⚠️  The tiers are replaced wholesale, never appended to.
            #
            #     Appending on a second run produces overlapping tiers, so the
            #     amount depends on query ordering rather than on the rule.
            scheme.tiers.all().delete()
            for low, high, rate in TIERS:
                CommissionTier.objects.create(
                    scheme=scheme, from_percent=low, to_percent=high, rate=rate
                )

        self.stdout.write(
            self.style.SUCCESS(f"خطط العمولة: {created} جديدة · {len(SCHEMES) - created} محدَّثة")
        )
        self.stdout.write("\n⚠️  قاعدة العمل ١٥ لم تُحسم — هذه توصية تُعدَّل من اللوحة.")
