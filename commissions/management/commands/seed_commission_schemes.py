"""
بذر خطط العمولة القياسية.

    python manage.py seed_commission_schemes

⚠️  **توصية لا قرار — قاعدة العمل ١٥ لم تُحسم.**

    النسب أدناه شرائح متدرّجة على صافي المبيعات، وهي التوصية
    المكتوبة في سجل القرارات. ما يهمّ معماريًا أنها **بيانات**:
    تعديلها من اللوحة بلا نشر.

⚠️  والشريحة العليا **بلا سقف**.

    سقف مكتوب يجعل من حقّق ٥٠٠٪ لا يطابق أي شريحة، فيخرج بعمولة
    صفر مكافأةً على أفضل شهر في حياته.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from commissions.models import CommissionBase, CommissionScheme, CommissionTier

#: (من ٪، إلى ٪ أو None، نسبة العمولة ٪)
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
        # ⚠️  المندوب الأول على **الربح** لا المبيعات.
        #
        #     مندوب يُكافأ على المبيعات وحدها يبيع الأصناف رخيصة
        #     الهامش بخصومات — فيرتفع رقمه وينخفض ربح المتجر.
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

            # ⚠️  الشرائح تُستبدَل كاملةً لا تُضاف.
            #
            #     الإضافة على تشغيل ثانٍ تُنتج شرائح متداخلة، فيصير
            #     المبلغ تابعًا لترتيب الاستعلام لا للقاعدة.
            scheme.tiers.all().delete()
            for low, high, rate in TIERS:
                CommissionTier.objects.create(
                    scheme=scheme, from_percent=low, to_percent=high, rate=rate
                )

        self.stdout.write(
            self.style.SUCCESS(f"خطط العمولة: {created} جديدة · {len(SCHEMES) - created} محدَّثة")
        )
        self.stdout.write("\n⚠️  قاعدة العمل ١٥ لم تُحسم — هذه توصية تُعدَّل من اللوحة.")
