"""
بذر بنود المصروفات القياسية.

    python manage.py seed_expense_categories

قابل للتشغيل مرارًا — يُحدّث الأسماء ولا يكرّر.

⚠️  **هذه توصية لا قرار — قاعدة العمل ١٣ لم تُحسم.**

    البنود أدناه تغطية معقولة لنشاط تجزئة طبي في مصر، وهي نقطة
    بداية تُعدَّل من اللوحة. ما يهمّ معماريًا أنها **بيانات لا
    كود**: تغييرها لا يحتاج نشرًا.

⚠️  ولا يُلمَس `is_active` عند التحديث.

    إعادة التشغيل كانت ستُعيد تفعيل بندٍ عطّله المحاسب عمدًا —
    فيظهر في قائمة اختيار كان قد أزاله.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from finance.models import ExpenseCategory

CATEGORIES = [
    ("rent", "إيجار", "Rent", None),
    ("salaries", "رواتب وأجور", "Salaries & wages", None),
    ("shipping", "شحن وتوصيل", "Shipping & delivery", None),
    ("marketing", "تسويق وإعلان", "Marketing & advertising", None),
    ("utilities", "مرافق", "Utilities", None),
    # ⚠️  المرافق تُفصَّل: «كهرباء ارتفعت» معلومة، و«مرافق ارتفعت»
    #     سؤال. والشجرة موجودة لهذا بالضبط.
    ("utilities-power", "كهرباء", "Electricity", "utilities"),
    ("utilities-water", "مياه", "Water", "utilities"),
    ("utilities-internet", "إنترنت واتصالات", "Internet & telecom", "utilities"),
    ("maintenance", "صيانة", "Maintenance", None),
    ("supplies", "مستلزمات تشغيل", "Operating supplies", None),
    # ⚠️  الرسوم البنكية وعمولات البوابات بند مستقل لا «أخرى».
    #     نسبتها من كل عملية دفع إلكتروني، فدفنها يخفي تكلفة
    #     حقيقية للقناة الأونلاين عند مقارنتها بالكاونتر.
    ("fees", "رسوم بنكية وعمولات بوابات", "Bank & gateway fees", None),
    ("licenses", "تراخيص واشتراكات", "Licenses & subscriptions", None),
    ("other", "أخرى", "Other", None),
]


class Command(BaseCommand):
    help = "بذر بنود المصروفات القياسية — قابل للتشغيل مرارًا"

    @transaction.atomic
    def handle(self, *args, **options):
        created = 0
        updated = 0

        # ⚠️  الآباء أولًا: البند الفرعي يحتاج أباه موجودًا.
        #     القائمة مرتّبة كذلك، والفرز هنا حارس لا اعتماد.
        ordered = sorted(CATEGORIES, key=lambda row: row[3] is not None)

        for index, (code, name_ar, name_en, parent_code) in enumerate(ordered):
            parent = (
                ExpenseCategory.objects.filter(code=parent_code).first() if parent_code else None
            )

            _, was_created = ExpenseCategory.objects.update_or_create(
                code=code,
                defaults={
                    "name_ar": name_ar,
                    "name_en": name_en,
                    "parent": parent,
                    "display_order": index * 10,
                },
            )
            created += int(was_created)
            updated += int(not was_created)

        self.stdout.write(self.style.SUCCESS(f"بنود المصروفات: {created} جديد · {updated} محدَّث"))
        self.stdout.write("\n⚠️  قاعدة العمل ١٣ لم تُحسم — هذه توصية تُعدَّل من اللوحة.")
