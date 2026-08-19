"""
Seed the standard access policies.

Re-runnable — it updates rather than duplicating.

    python manage.py seed_access_policies
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from access.models import AccessLevel, AccessPolicy
from accounts.models import AccountType

PROFESSIONALS = [
    AccountType.DOCTOR,
    AccountType.PHARMACIST,
    AccountType.PHARMACY,
]

TRADE = [
    AccountType.PHARMACY,
    AccountType.WAREHOUSE,
    AccountType.TRADER,
    AccountType.SUPPLIER,
]

POLICIES = [
    {
        "code": "public",
        "name_ar": "عام",
        "name_en": "Public",
        "level": AccessLevel.PUBLIC,
        "is_default": True,
        "description_ar": "متاح للجميع بما فيهم الزوار.",
        "description_en": "Available to everyone including guests.",
    },
    {
        "code": "registered",
        "name_ar": "يتطلب تسجيل دخول",
        "name_en": "Registered only",
        "level": AccessLevel.REGISTERED,
        "denial_message_ar": "سجّل الدخول لعرض هذا المنتج.",
        "denial_message_en": "Sign in to view this product.",
    },
    {
        "code": "students",
        "name_ar": "طلاب فقط",
        "name_en": "Students only",
        "level": AccessLevel.RESTRICTED,
        "allowed_account_types": [AccountType.STUDENT],
        "denial_message_ar": "هذا المنتج متاح لحسابات الطلاب فقط.",
        "denial_message_en": "This product is available to student accounts only.",
    },
    {
        "code": "professionals",
        "name_ar": "مهنيون موثّقون",
        "name_en": "Verified professionals",
        "level": AccessLevel.PROFESSIONAL,
        "allowed_account_types": PROFESSIONALS,
        "requires_verification": True,
        "denial_message_ar": "هذا المنتج يتطلب حساب مهني موثّق.",
        "denial_message_en": "This product requires a verified professional account.",
    },
    {
        "code": "pharmacy_only",
        "name_ar": "صيدليات فقط",
        "name_en": "Pharmacies only",
        "level": AccessLevel.PROFESSIONAL,
        "allowed_account_types": [AccountType.PHARMACY],
        "requires_verification": True,
        "denial_message_ar": "هذا المنتج متاح للصيدليات الموثّقة فقط.",
        "denial_message_en": "Available to verified pharmacies only.",
    },
    {
        "code": "wholesale",
        "name_ar": "جملة",
        "name_en": "Wholesale",
        "level": AccessLevel.RESTRICTED,
        "allowed_account_types": TRADE,
        "requires_verification": True,
        "denial_message_ar": "أسعار الجملة متاحة للحسابات التجارية الموثّقة.",
        "denial_message_en": "Wholesale is available to verified business accounts.",
    },
    {
        "code": "otc_regulated",
        "name_ar": "دواء بلا وصفة",
        "name_en": "OTC medicine",
        "level": AccessLevel.REGISTERED,
        "denial_message_ar": "سجّل الدخول لعرض المنتجات الدوائية.",
        "denial_message_en": "Sign in to view pharmaceutical products.",
        "description_ar": (
            "أدوية تُصرف بلا وصفة. حين تُضاف الأدوية الموصوفة تُنشأ "
            "سياسة منفصلة تشترط مراجعة الوصفة — لا تُعدَّل هذه."
        ),
        "description_en": (
            "Over-the-counter medicines. When prescription products are "
            "introduced, a separate policy is created — this one is not changed."
        ),
    },
]


class Command(BaseCommand):
    help = "بذر سياسات الوصول القياسية"

    @transaction.atomic
    def handle(self, *args, **options):
        created = updated = 0

        for spec in POLICIES:
            code = spec.pop("code")
            _, was_created = AccessPolicy.objects.update_or_create(code=code, defaults=spec)
            spec["code"] = code  # For repeated runs inside the same process

            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"سياسات الوصول: {created} جديدة · {updated} محدَّثة"))
