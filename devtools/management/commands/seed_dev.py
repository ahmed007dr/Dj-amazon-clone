"""
بذرة بيئة التطوير — نظام قابل للتشغيل والتجربة في أمر واحد.

    python manage.py seed_dev

⚠️  **غير موجود في الإنتاج.** `devtools` مُثبَّت في
    `config/settings/dev.py` وحده، لأن البذرة تُنشئ حسابات بكلمة
    مرور معروفة. انظر `devtools/README.md`.

⚠️  قابل للتشغيل مرارًا: كل وحدة تستخدم `update_or_create` بمفتاح
    طبيعي. الاستثناء الوحيد هو المخزون والطلبات — إعادة استلام
    دفعة أو إنشاء طلب ثانٍ تُغيّر أرصدة حقيقية، فلهما حارس صريح.

الخيارات:
    --minimal   الإعدادات والبنية فقط — بلا منتجات ولا مستخدمين
    --reset     حذف كل البيانات ثم إعادة البذر
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
    people,
    pricing,
    staffing,
    stock,
    trade,
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
        # ⚠️  حزام أمان ثانٍ فوق عدم التثبيت في الإنتاج.
        #
        #     الأول هو أن الأمر غير موجود أصلًا خارج التطوير؛ وهذا
        #     يمسك الحالة التي يُثبَّت فيها التطبيق بالخطأ.
        if not settings.DEBUG:
            raise CommandError(
                "seed_dev لا يعمل إلا في وضع التطوير — البذرة تُنشئ حسابات بكلمة مرور معروفة."
            )

        if options["reset"]:
            self._reset()

        with transaction.atomic():
            report = self._seed(minimal=options["minimal"])

        self._report(report, minimal=options["minimal"])

    # ── التنفيذ ────────────────────────────────────────────

    def _seed(self, *, minimal: bool) -> dict:
        report = {}

        self._step("الإعدادات والضرائب")
        report["configuration"] = configuration.seed()["counts"]

        # ⚠️  الهوية تُبذر حتى في الوضع المختصر — الواجهة بلا ألوان
        #     تبدو معطّلة لا «غير مضبوطة بعد».
        self._step("الهوية البصرية")
        report["branding"] = branding.seed()["counts"]

        # ⚠️  الإخراج مكتوم: الأمران يطبعان تعليماتهما الخاصة، وهي
        #     ضجيج وسط تقرير البذرة لا معلومة.
        self._step("سياسات الوصول")
        call_command("seed_access_policies", verbosity=0, stdout=StringIO())

        self._step("بوابات الدفع")
        call_command("seed_payment_providers", verbosity=0, stdout=StringIO())

        # ⚠️  الأدوار بنية تحتية: بوابة الموظفين بلا دور واحد لا
        #     تُفتح، و`EmployeeProfile.role` مفتاح إلزامي.
        self._step("الأدوار الوظيفية")
        call_command("seed_employee_roles", verbosity=0, stdout=StringIO())

        # ⚠️  بنود المصروفات بنية تحتية لا بيانات تجريبية.
        #
        #     شاشة المصروفات بلا بند واحد لا تقبل إدخالًا إطلاقًا،
        #     والقائمة الفارغة تبدو عطلًا لا «لم تُضبَط بعد».
        self._step("بنود المصروفات")
        call_command("seed_expense_categories", verbosity=0, stdout=StringIO())

        self._step("المواقع والشحن")
        logistics_data = logistics.seed()
        report["logistics"] = logistics_data["counts"]

        # ⚠️  الأجهزة تُبذر حتى في الوضع المختصر.
        #
        #     نقطة البيع بلا جهاز واحد لا تُفتح إطلاقًا: البوابة
        #     تعرض «لا جهاز متاح» ولا سبيل لتجاوزها من الواجهة.
        #     وهي بنية تحتية كالمواقع لا بيانات تجريبية كالمنتجات.
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

        self._step("الجامعات وحزم الطلاب")
        academia_data = academia.seed(products)
        report["academia"] = academia_data["counts"]

        self._step("المستخدمون والملفات")
        people_data = people.seed(academia_data["faculties"])
        report["people"] = people_data["counts"]

        # ⚠️  الحسابات التجارية بعد المستخدمين وقبل الطلبات:
        #     تحتاج المستخدمين، والطلبات الآجلة تحتاجها.
        self._step("الحسابات التجارية")
        report["trade"] = trade.seed(people_data["users"])["counts"]

        self._step("الموظفون والإسناد")
        report["staffing"] = staffing.seed(people_data["users"], people_data["customers"])["counts"]

        self._step("الطلبات والتقييمات")
        report["transactions"] = transactions.seed(
            people_data["users"], people_data["customers"], products
        )["counts"]

        return report

    def _reset(self):
        """
        ⚠️  حذف **كل** البيانات لا بيانات البذرة وحدها.

            التمييز بينهما يحتاج علامة على كل صف؛ وبيئة التطوير لا
            تستحق هذا التعقيد. الأمر لا يعمل خارج التطوير أصلًا.

        ⚠️  `hard_delete` لا `delete`.

            معظم النطاقات ترث `SoftDeleteModel` حيث `delete()`
            تكتب `deleted_at` ولا تحذف صفًّا واحدًا. استخدامها هنا
            يترك القاعدة ممتلئة بينما يقول الأمر إنه أفرغها — ثم
            تفشل البذرة على قيود التفرّد بأخطاء لا تدل على السبب.
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

        # ⚠️  فكّ الروابط الذاتية أولًا (`Category.parent`).
        #
        #     الشجرة المحمية بـ PROTECT لا تُحذف دفعةً واحدة مهما
        #     كان الترتيب: كل أب يحميه ابنه. تصفير المفتاح الذاتي
        #     القابل للتفريغ يحوّلها إلى صفوف مستقلة.
        for model in models:
            for field in model._meta.get_fields():
                if (
                    getattr(field, "many_to_one", False)
                    and field.related_model is model
                    and field.null
                ):
                    manager = getattr(model, "all_objects", model.objects)
                    manager.all().update(**{field.name: None})

        # ⚠️  تمريرات متكرّرة بدل ترتيب حذف مكتوب يدويًا.
        #
        #     ترتيب ثابت يكفي اليوم ويتعطّل عند أول مفتاح أجنبي
        #     جديد — والفشل يظهر كخطأ `ProtectedError` غامض بعد
        #     شهور. التكرار يحسمه بلا صيانة.
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

    # ── العرض ──────────────────────────────────────────────

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
