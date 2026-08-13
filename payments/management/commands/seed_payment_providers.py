"""
بذر بوابات الدفع القياسية.

قابل للتشغيل مرارًا — يُحدّث ولا يكرّر.

    python manage.py seed_payment_providers

⚠️  **البوابات التي لا تحتاج بيانات اعتماد تُفعَّل؛ وما عداها لا.**

    تفعيل بوابة بلا مفاتيح يعني عميلًا يختارها ثم يفشل دفعه.
    الأدمن يضيف المفاتيح ثم يفعّلها من اللوحة.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from payments.models import PaymentMethodKind, PaymentProvider

#: القنوات
ONLINE = "ONLINE"
POS = "POS"
EMPLOYEE = "EMPLOYEE"

PROVIDERS = [
    {
        "code": "cod",
        "adapter_key": "cash_on_delivery",
        "name_ar": "الدفع عند الاستلام",
        "name_en": "Cash on delivery",
        "supported_methods": [PaymentMethodKind.CASH_ON_DELIVERY],
        "supported_channels": [ONLINE, EMPLOYEE],
        "priority": 100,
        "is_sandbox": False,
        # ⚠️  لا مال يُقبض الآن — التحصيل يدوي عند التسليم
        "is_active": True,
    },
    {
        "code": "cash",
        "adapter_key": "cash",
        "name_ar": "نقدي",
        "name_en": "Cash",
        "supported_methods": [PaymentMethodKind.CASH],
        # ⚠️  نقطة البيع فقط — «نقدي» في متجر إلكتروني بلا معنى
        "supported_channels": [POS],
        "priority": 90,
        "is_sandbox": False,
        "is_active": True,
    },
    {
        "code": "bank",
        "adapter_key": "bank_transfer",
        "name_ar": "تحويل بنكي",
        "name_en": "Bank transfer",
        "supported_methods": [PaymentMethodKind.BANK_TRANSFER],
        "supported_channels": [ONLINE, EMPLOYEE],
        # ⚠️  التحويل يُراجَع يدويًا — لا يصلح لمبالغ صغيرة
        "min_amount": 500,
        "priority": 50,
        "is_sandbox": False,
        "is_active": True,
    },
]


class Command(BaseCommand):
    help = "بذر بوابات الدفع القياسية"

    @transaction.atomic
    def handle(self, *args, **options):
        created = updated = 0

        for spec in PROVIDERS:
            payload = dict(spec)
            code = payload.pop("code")

            _, was_created = PaymentProvider.objects.update_or_create(code=code, defaults=payload)
            created += was_created
            updated += not was_created

        self.stdout.write(self.style.SUCCESS(f"بوابات الدفع: {created} جديدة · {updated} محدَّثة"))
        self.stdout.write(
            "\nلإضافة بوابة خارجية (Paymob · Fawry · Stripe):\n"
            "  ١. أضف محوّلًا في payments/adapters.py يرث PaymentAdapter\n"
            "  ٢. سجّله بـ register()\n"
            "  ٣. أنشئ البوابة من لوحة الأدمن واختر المحوّل\n"
            "  ٤. أضف بيانات الاعتماد\n"
            "  ٥. فعّلها\n"
            "\nالخطوة ١ وحدها تحتاج مطوّرًا — الباقي من اللوحة."
        )
