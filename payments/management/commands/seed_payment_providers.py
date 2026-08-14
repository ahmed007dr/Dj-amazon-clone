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
    # ── البوابات الخارجية — **موقوفة حتى تُضاف المفاتيح** ──
    #
    # ⚠️  تُبذر موقوفة وفي وضع التجريب عمدًا.
    #
    #     تفعيلها بلا مفاتيح يجعل العميل يختارها ثم يفشل دفعه؛
    #     ووضع الإنتاج بلا اختبار يحصّل مالًا حقيقيًا في أول تجربة.
    #     الأدمن يضيف المفاتيح من اللوحة ثم يفعّلها.
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

#: المفاتيح المطلوبة لكل بوابة خارجية — تُعرض في تعليمات التشغيل
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

            # ⚠️  **التشغيل والإيقاف قرار الأدمن لا قرار البذرة.**
            #
            #     الشكل السابق كان يفرض `is_active` من هذا الملف في
            #     كل تشغيل — أي أن إعادة بذر بعد أن يضيف الأدمن
            #     مفاتيح Paymob ويفعّلها تُوقفها ثانيةً بصمت،
            #     فيتوقّف الدفع بالبطاقة بلا سبب ظاهر.
            #
            #     القيمة المبذورة تسري على **الإنشاء الأول** فقط.
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
