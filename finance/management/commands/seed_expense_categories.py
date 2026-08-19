"""
Seed the standard expense categories.

    python manage.py seed_expense_categories

Re-runnable — it updates the names and does not duplicate.

⚠️  **This is a recommendation, not a decision — business rule 13 is not settled.**

    The categories below are reasonable coverage for a medical retail business
    in Egypt, and are a starting point to be edited from the panel. What matters
    architecturally is that they are **data, not code**: changing them needs no
    deployment.

⚠️  And `is_active` is not touched on update.

    Re-running would have reactivated a category the accountant deliberately
    disabled — so it would reappear in a select list they had removed it from.
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
    # ⚠️  Utilities are broken out: "electricity went up" is information, and
    #     "utilities went up" is a question. The tree exists for exactly this.
    ("utilities-power", "كهرباء", "Electricity", "utilities"),
    ("utilities-water", "مياه", "Water", "utilities"),
    ("utilities-internet", "إنترنت واتصالات", "Internet & telecom", "utilities"),
    ("maintenance", "صيانة", "Maintenance", None),
    ("supplies", "مستلزمات تشغيل", "Operating supplies", None),
    # ⚠️  Bank charges and gateway commissions are their own category, not "other".
    #     They are a percentage of every electronic payment, so burying them
    #     hides a real cost of the online channel when comparing it to the counter.
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

        # ⚠️  Parents first: a subcategory needs its parent to exist.
        #     The list is ordered accordingly, and the sort here is a guard, not a reliance.
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
