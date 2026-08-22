"""
Seed the standard payment gateways.

Re-runnable — it updates and does not duplicate.

    python manage.py seed_payment_providers

⚠️  **Gateways needing no credentials are enabled; the rest are not.**

    Enabling a gateway with no keys means a customer choosing it and then having
    their payment fail. The admin adds the keys and then enables it from the panel.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from payments.models import PaymentMethodKind, PaymentProvider

#: Channels
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
        # ⚠️  No money is taken now — the capture is manual on delivery
        "is_active": True,
    },
    {
        "code": "cash",
        "adapter_key": "cash",
        "name_ar": "نقدي",
        "name_en": "Cash",
        "supported_methods": [PaymentMethodKind.CASH],
        # ⚠️  Point of sale only — "cash" in an online store is meaningless
        "supported_channels": [POS],
        "priority": 90,
        "is_sandbox": False,
        "is_active": True,
    },
    {
        # ⚠️  The card terminal at the counter — **a gateway in its own right.**
        #
        #     Split payment (half cash and half by card) is a daily occurrence
        #     at the counter. Without a gateway accepting `CARD` on the `POS`
        #     channel, half the sale was refused with "payment method unavailable" —
        #     and the cashier recorded it as two sales, breaking the receipt and the return
        #     together.
        #
        # ⚠️  And `adapter_key="cash"` is deliberate: the terminal is operated by hand
        #     and prints its own receipt. The system records that the amount was
        #     collected and contacts no payment network — and therefore **it does not enter the
        #     drawer** either.
        "code": "pos-card",
        "adapter_key": "cash",
        "name_ar": "بطاقة على الطرفية",
        "name_en": "Card terminal",
        "supported_methods": [PaymentMethodKind.CARD],
        "supported_channels": [POS],
        "priority": 85,
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
        # ⚠️  A transfer is reviewed by hand — unsuitable for small amounts
        "min_amount": 500,
        "priority": 50,
        "is_sandbox": False,
        "is_active": True,
    },
    # ── External gateways — **disabled until the keys are added** ──
    #
    # ⚠️  Seeded disabled and in test mode deliberately.
    #
    #     Enabling them with no keys makes a customer choose one and then have
    #     their payment fail; and production mode with no testing collects real money on the first
    #     attempt.
    #     The admin adds the keys from the panel and then enables them.
    {
        "code": "paymob",
        "adapter_key": "paymob",
        "name_ar": "Paymob — بطاقة ومحفظة",
        "name_en": "Paymob — card and wallet",
        "supported_methods": [
            PaymentMethodKind.CARD,
            PaymentMethodKind.WALLET,
            PaymentMethodKind.INSTALLMENT,
        ],
        "supported_channels": [ONLINE],
        "priority": 80,
        "is_sandbox": True,
        "is_active": False,
    },
    {
        "code": "fawry",
        "adapter_key": "fawry",
        "name_ar": "فوري",
        "name_en": "Fawry",
        "supported_methods": [PaymentMethodKind.CARD, PaymentMethodKind.WALLET],
        "supported_channels": [ONLINE],
        "priority": 70,
        "is_sandbox": True,
        "is_active": False,
    },
]

#: The keys each external gateway requires — shown in the setup instructions
REQUIRED_CREDENTIALS = {
    "paymob": ["api_key", "integration_id", "iframe_id", "hmac_secret"],
    "fawry": ["merchant_code", "secure_key"],
}


class Command(BaseCommand):
    help = "بذر بوابات الدفع القياسية"

    @transaction.atomic
    def handle(self, *args, **options):
        created = updated = 0

        for spec in PROVIDERS:
            payload = dict(spec)
            code = payload.pop("code")

            existing = PaymentProvider.objects.filter(code=code).first()

            # ⚠️  **Enabling and disabling are the admin's decision, not the seed's.**
            #
            #     The previous form forced `is_active` from this file on every
            #     run — meaning a re-seed after the admin had added the Paymob
            #     keys and enabled it disabled it again silently,
            #     so card payment stopped for no evident reason.
            #
            #     The seeded value applies to the **first creation** only.
            if existing is not None:
                payload.pop("is_active", None)
                payload.pop("is_sandbox", None)

            _, was_created = PaymentProvider.objects.update_or_create(code=code, defaults=payload)
            created += was_created
            updated += not was_created

        self.stdout.write(self.style.SUCCESS(f"بوابات الدفع: {created} جديدة · {updated} محدَّثة"))

        pending = PaymentProvider.objects.filter(
            code__in=REQUIRED_CREDENTIALS, is_active=False
        ).values_list("code", flat=True)

        if pending:
            self.stdout.write("\nبوابات خارجية موقوفة بانتظار المفاتيح:")
            for code in pending:
                keys = " · ".join(REQUIRED_CREDENTIALS[code])
                self.stdout.write(f"  {code:8} ← {keys}")

            self.stdout.write(
                "\n  التشغيل:\n"
                "    ١. افتح حساب البيئة التجريبية لدى المزوّد\n"
                "    ٢. أضف المفاتيح من لوحة الأدمن (وضع تجريبي)\n"
                "    ٣. نفّذ عملية كاملة: دفع · ويب‌هوك · استرداد\n"
                "    ٤. حوّلها إلى وضع الإنتاج ثم فعّلها\n"
                "\n  ⚠️  المحوّلان مكتوبان ولم يُختبرا مقابل حساب حقيقي.\n"
                "     الاستجابة الخام تُحفَظ كاملة، فأي اسم حقل مختلف\n"
                "     يظهر في أول عملية تجريبية."
            )
