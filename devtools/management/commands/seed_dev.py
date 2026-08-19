"""
Development environment seed — a runnable, explorable system in one command.

    python manage.py seed_dev

⚠️  **Not present in production.** `devtools` is installed in
    `config/settings/dev.py` alone, because the seed creates accounts with a
    well-known password. See `devtools/README.md`.

⚠️  Re-runnable: every module uses `update_or_create` with a natural key. The
    sole exception is stock and orders — re-receiving a batch or creating a
    second order changes real balances, so both have an explicit guard.

Options:
    --minimal   settings and structure only — no products and no users
    --reset     delete all data, then re-seed
"""

from io import StringIO

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from devtools.seeds import (
    academia,
    branding,
    catalog,
    configuration,
    counter,
    logistics,
    loyalty,
    mailing,
    people,
    pricing,
    staffing,
    stock,
    trade,
    traffic,
    transactions,
)


class Command(BaseCommand):
    help = "بذرة بيئة التطوير — بيانات كاملة قابلة للتجربة فورًا"

    def add_arguments(self, parser):
        parser.add_argument(
            "--minimal",
            action="store_true",
            help="الإعدادات والبنية فقط — بلا منتجات ولا مستخدمين",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="حذف كل البيانات ثم إعادة البذر",
        )

    def handle(self, *args, **options):
        # ⚠️  A second seatbelt on top of not being installed in production.
        #
        #     The first is that the command does not exist outside development;
        #     this catches the case where the app is installed by mistake.
        if not settings.DEBUG:
            raise CommandError(
                "seed_dev لا يعمل إلا في وضع التطوير — البذرة تُنشئ حسابات بكلمة مرور معروفة."
            )

        if options["reset"]:
            self._reset()

        with transaction.atomic():
            report = self._seed(minimal=options["minimal"])

        self._report(report, minimal=options["minimal"])

    # ── Execution ──────────────────────────────────────────

    def _seed(self, *, minimal: bool) -> dict:
        report = {}

        self._step("الإعدادات والضرائب")
        report["configuration"] = configuration.seed()["counts"]

        # ⚠️  The identity is seeded even in minimal mode — a frontend with no
        #     colours looks broken rather than "not configured yet".
        self._step("الهوية البصرية")
        report["branding"] = branding.seed()["counts"]

        # ⚠️  Email is infrastructure like the identity: a screen with not one
        #     account looks broken, and shows no difference between security and marketing (ADR-76).
        self._step("حسابات البريد")
        report["mailing"] = mailing.seed()["counts"]

        # ⚠️  Output is muted: the two commands print their own instructions, which
        #     are noise in the middle of the seed report rather than information.
        self._step("سياسات الوصول")
        call_command("seed_access_policies", verbosity=0, stdout=StringIO())

        self._step("بوابات الدفع")
        call_command("seed_payment_providers", verbosity=0, stdout=StringIO())

        # ⚠️  Roles are infrastructure: the staff portal does not open with not one
        #     role, and `EmployeeProfile.role` is a mandatory key.
        self._step("الأدوار الوظيفية")
        call_command("seed_employee_roles", verbosity=0, stdout=StringIO())

        # ⚠️  Expense categories are infrastructure, not sample data.
        #
        #     The expenses screen accepts no input at all with not one category,
        #     and the empty list looks like a fault rather than "not configured yet".
        self._step("بنود المصروفات")
        call_command("seed_expense_categories", verbosity=0, stdout=StringIO())

        self._step("المواقع والشحن")
        logistics_data = logistics.seed()
        report["logistics"] = logistics_data["counts"]

        # ⚠️  Registers are seeded even in minimal mode.
        #
        #     Point of sale does not open at all with not one register: the gate
        #     shows "no register available" and there is no way past it from the frontend.
        #     And it is infrastructure like locations, not sample data like products.
        # ⚠️  Loyalty programmes are infrastructure, not sample data.
        #
        #     The loyalty screen accepts no configuration with not one programme, and
        #     the empty list looks like a fault rather than "not configured yet". One of
        #     them is deliberately disabled so the switch can be seen in the off position.
        self._step("برامج الولاء والإحالة")
        report["loyalty"] = loyalty.seed()["counts"]

        self._step("أجهزة نقطة البيع")
        report["counter"] = counter.seed(logistics_data["locations"])["counts"]

        if minimal:
            return report

        self._step("الكتالوج")
        catalog_data = catalog.seed()
        report["catalog"] = catalog_data["counts"]
        products = catalog_data["products"]

        self._step("قوائم الأسعار والكوبونات")
        report["pricing"] = pricing.seed(products)["counts"]

        self._step("المخزون")
        report["stock"] = stock.seed(
            products, catalog_data["variants"], logistics_data["locations"]
        )["counts"]

        self._step("الجامعات فئات الطلاب")
        academia_data = academia.seed(products)
        report["academia"] = academia_data["counts"]

        self._step("المستخدمون والملفات")
        people_data = people.seed(academia_data["faculties"])
        report["people"] = people_data["counts"]

        # ⚠️  Business accounts come after users and before orders:
        #     they need the users, and credit orders need them.
        self._step("الحسابات التجارية")
        report["trade"] = trade.seed(people_data["users"])["counts"]

        self._step("الموظفون والإسناد")
        report["staffing"] = staffing.seed(people_data["users"], people_data["customers"])["counts"]

        self._step("الطلبات والتقييمات")
        report["transactions"] = transactions.seed(
            people_data["users"], people_data["customers"], products
        )["counts"]

        # ⚠️  **Deliberately last** — it spreads what was created before it across time.
        #
        #     Every seeded order lands at the moment the command runs, so the load
        #     screen shows one lit cell and 167 empty ones — which looks like a
        #     broken screen rather than an empty one.
        self._step("الحركة وتوزيع الزمن")
        report["traffic"] = traffic.seed()["counts"]

        return report

    def _reset(self):
        """
        ⚠️  It deletes **all** data, not the seeded data alone.

            Telling them apart would need a marker on every row, and the
            development environment does not warrant that complexity. The
            command does not run outside development anyway.

        ⚠️  `hard_delete`, not `delete`.

            Most domains inherit `SoftDeleteModel`, where `delete()` writes
            `deleted_at` and removes not a single row. Using it here leaves the
            database full while the command says it emptied it — and then the
            seed fails on uniqueness constraints with errors that give no hint
            of the cause.
        """
        from django.apps import apps
        from django.db.models import ProtectedError, RestrictedError

        self.stdout.write(self.style.WARNING("حذف كل البيانات…"))

        models = []
        for label in reversed(
            [app for app in settings.INSTALLED_APPS if not app.startswith("django.")]
        ):
            try:
                config = apps.get_app_config(label.split(".")[-1])
            except LookupError:
                continue
            models.extend(reversed(list(config.get_models())))

        # ⚠️  Break the self-references first (`Category.parent`).
        #
        #     A tree protected by PROTECT cannot be deleted in one pass whatever
        #     the order: every parent is protected by its child. Nulling the
        #     nullable self-key turns them into independent rows.
        for model in models:
            for field in model._meta.get_fields():
                if (
                    getattr(field, "many_to_one", False)
                    and field.related_model is model
                    and field.null
                ):
                    manager = getattr(model, "all_objects", model.objects)
                    manager.all().update(**{field.name: None})

        # ⚠️  Repeated passes instead of a hand-written deletion order.
        #
        #     A fixed order is enough today and breaks at the first new foreign
        #     key — and the failure shows up as an obscure `ProtectedError` months
        #     later. Repetition settles it with no upkeep.
        remaining = models
        while remaining:
            blocked = []
            for model in remaining:
                manager = getattr(model, "all_objects", model.objects)
                queryset = manager.all()
                try:
                    getattr(queryset, "hard_delete", queryset.delete)()
                except (ProtectedError, RestrictedError):
                    blocked.append(model)

            if len(blocked) == len(remaining):
                names = ", ".join(model.__name__ for model in blocked)
                raise CommandError(f"تعذّر حذف: {names} — دورة مفاتيح أجنبية")

            remaining = blocked

    # ── Output ─────────────────────────────────────────────

    def _step(self, label: str):
        self.stdout.write(f"  › {label}…")

    def _report(self, report: dict, *, minimal: bool):
        self.stdout.write("")
        for section, counts in report.items():
            line = " · ".join(f"{key}: {value}" for key, value in counts.items())
            self.stdout.write(f"  {section:<16} {line}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("تمت البذرة."))

        if minimal:
            self.stdout.write("\nالوضع المختصر — بلا منتجات ولا مستخدمين.")
            return

        self.stdout.write(
            f"\n  الدخول — كلمة المرور للجميع: {people.PASSWORD}\n"
            "\n"
            "    owner@dev.local        مالك النظام — صلاحية كاملة\n"
            "    catalog@dev.local      مدير الكتالوج\n"
            "    finance@dev.local      المدير المالي\n"
            "    support@dev.local      خدمة العملاء\n"
            "    warehouse@dev.local    موظف مخزن\n"
            "    cashier@dev.local      كاشير\n"
            "    customer@dev.local     عميل تجزئة — له طلبات\n"
            "    vip@dev.local          عميل مميّز\n"
            "    suspended@dev.local    حساب موقوف\n"
            "    doctor@dev.local       طبيب موثّق\n"
            "    pharmacist@dev.local   صيدلي ينتظر التوثيق\n"
            "    rejected@dev.local     توثيق مرفوض\n"
            "    pharmacy@dev.local     صيدلية — أسعار جملة\n"
            "    trader@dev.local       تاجر — عنوان بمنطقة نائية\n"
            "    student@dev.local      طالب موثّق — أسعار طلاب\n"
            "    student3@dev.local     طالب غير موثّق\n"
        )
        self.stdout.write(
            "  الكوبونات: WELCOME10 · FREESHIP · STUDENT50 · EXPIRED2025 (منتهٍ عمدًا)\n"
            "\n"
            "  ⚠️  الضريبة ١٤٪ والأسعار غير شاملة — توصية لقاعدة عمل\n"
            "     لم تُحسم بعد (البند ١ب). تُعدَّل من إعدادات النظام.\n"
        )
