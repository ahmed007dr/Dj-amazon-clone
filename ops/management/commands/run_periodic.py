"""
تشغيل المهام الدورية.

    python manage.py run_periodic
    python manage.py run_periodic --job inventory
    python manage.py run_periodic --dry-run

⚠️  **هذا هو طابور المهام — لا Celery.**

    الأعمال الدورية هنا أربعة، أثقلها يمرّ على دفعات المخزون مرة
    يوميًا. عامل Celery وبروكر Redis وطبقة مراقبة لأربع دوال تُنفَّذ
    في ثوانٍ ليست بنيةً بل عبئًا تشغيليًا: خدمتان إضافيتان تُراقَبان
    وتُعاد تشغيلهما وتُحدَّثان.

    الجدولة تقع خارج التطبيق — `cron` أو Task Scheduler. التفصيل
    في `ops/README.md`.

    وحين يظهر عمل **يستحق** طابورًا حقيقيًا (تقارير ثقيلة · آلاف
    الرسائل · معالجة صور) يُضاف Celery حينها ولذلك العمل وحده.
    البنية لا تمنعه: كل مهمة دالة مستقلة قابلة للاستدعاء من أي
    مُشغِّل.

⚠️  وفشل مهمة **لا يوقف البقية**.

    دفعة تالفة تمنع الحجر يجب ألا تمنع إفراج الحجوزات — وإلا صار
    خطأ واحد يعطّل الصيانة كلها إلى أن يلاحظه أحد.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from django.core.management.base import BaseCommand

from accounts import services as account_services
from analytics import services as analytics_services
from cart import services as cart_services
from inventory import services as inventory_services
from loyalty import services as loyalty_services
from mailing import inbound as mail_inbound
from mailing import services as mail_services

logger = logging.getLogger(__name__)


def _expire_points() -> int:
    """⚠️  المهام تُرجع عددًا؛ خدمة الولاء تُرجع تفصيلًا."""
    return loyalty_services.expire_points()["batches"]


#: المهمة → (المجموعة، الوصف، الدالة)
#
# ⚠️  الترتيب مقصود: الإفراج عن الحجوزات **قبل** التنبيهات.
#
#     الحجز المنتهي يخصم من المتاح؛ فحساب التنبيهات قبل الإفراج
#     ينتج تنبيه «مخزون حرج» لمخزون سيعود بعد ثانية — ثم يُحسم
#     التنبيه في اليوم التالي، فيبدو النظام مضطربًا.
JOBS: dict[str, tuple[str, str, Callable[[], int]]] = {
    "release_reservations": (
        "inventory",
        "إفراج الحجوزات المنتهية",
        inventory_services.release_expired_reservations,
    ),
    "quarantine_batches": (
        "inventory",
        "حجر الدفعات المنتهية",
        inventory_services.quarantine_expired_batches,
    ),
    "expiry_alerts": (
        "inventory",
        "تنبيهات قرب انتهاء الصلاحية",
        inventory_services.check_expiring_batches,
    ),
    "abandon_carts": (
        "cart",
        "إهمال السلال الراكدة",
        cart_services.abandon_stale_carts,
    ),
    # ⚠️  إسقاط النقاط المنتهية **مهمة دورية لا حساب لحظي**.
    #
    #     بدونها يبقى الالتزام في الدفتر منتفخًا بنقاط لا تُصرَف،
    #     ويرى العميل رصيدًا يُرفض عند أول محاولة استبدال — وهو
    #     أسوأ من رصيد أقل يراه صحيحًا.
    "expire_points": (
        "loyalty",
        "إسقاط نقاط الولاء المنتهية",
        _expire_points,
    ),
    # ⚠️  **شبكة أمان لا مسار رئيسي.**
    #
    #     التسليم يبدأ على `on_commit` فور وقوع الحدث — أي في ثوانٍ.
    #     هذه المهمة تلتقط ما فشل (خادم متوقف · مهلة) وما عَلِق (عملية
    #     سقطت بين الحجز والإرسال). وبدونها كان الفشل المؤقت يعني
    #     رسالة ضائعة إلى الأبد.
    #
    #     ولذلك تُجدوَل **كل بضع دقائق** لا يوميًا كبقية المهام:
    #     أول إعادة محاولة بعد دقيقة، وتأخيرها يوميًا يجعل بريد
    #     إعادة تعيين كلمة المرور يصل بعد أن ينساه صاحبه.
    "send_outbound_mail": (
        "mail",
        "تسليم بريد الطابور",
        mail_services.deliver_pending,
    ),
    # ⚠️  السحب **بعد** التسليم في الترتيب.
    #
    #     الصندوق الوارد يمتلئ بردود على ما أرسلناه؛ وسحبه قبل تسليم
    #     ما ينتظر يجعل ردّ العميل يصل قبل الرسالة التي يردّ عليها —
    #     فيقرأ الموظف جوابًا بلا سؤال.
    "fetch_inbound_mail": (
        "mail",
        "سحب البريد الوارد",
        mail_inbound.fetch_all,
    ),
    # ⚠️  **تُجدوَل بالدقيقة لا باليوم** (ADR-17).
    #
    #     التواجد يُكتب في الكاش على كل طلب، والقاعدة تحفظ التاريخ.
    #     بلا تفريغ يبقى «آخر ظهور» في جدول الحسابات عند لحظة الدخول
    #     إلى الأبد، ويضيع سجل الجلسة كله إذا أُعيد تشغيل الكاش.
    #
    #     والأمر خفيف عمدًا: استعلام واحد لكل دقيقة متميّزة، ولا
    #     استعلام إطلاقًا حين لا يكون أحد متصلًا.
    "flush_presence": (
        "presence",
        "تفريغ سجل التواجد إلى الجلسات",
        account_services.flush_presence,
    ),
    # ⚠️  بالدقيقة أيضًا — العدّادات في الكاش، وإعادة تشغيله بين
    #     تفريغين تُضيّع ما بينهما. والساعة السابقة تُفرَّغ مع
    #     الحالية فلا تضيع دقائق عبور الساعة.
    "flush_traffic": (
        "presence",
        "تفريغ عدّادات الحركة",
        analytics_services.flush_traffic,
    ),
    # ⚠️  الاحتفاظ ٩٠ يومًا — حركة لا يقرأها أحد بعدها تبقى
    #     مسؤولية بلا فائدة. تُجدوَل يوميًا لا بالدقيقة.
    "purge_traffic": (
        "traffic",
        "حذف الحركة الأقدم من ٩٠ يومًا",
        analytics_services.purge_traffic,
    ),
}


class Command(BaseCommand):
    help = "تشغيل المهام الدورية (الجدولة من cron أو Task Scheduler)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--job",
            help=(
                "اسم مهمة واحدة أو مجموعة "
                "(inventory · cart · loyalty · mail · presence · traffic)"
            ),
        )
        parser.add_argument("--dry-run", action="store_true", help="عرض ما سيُنفَّذ بلا تنفيذ")

    def handle(self, *args, **options):
        selected = self._select(options.get("job"))

        if not selected:
            self.stderr.write(self.style.ERROR(f"لا مهمة بهذا الاسم: {options.get('job')}"))
            self.stderr.write(
                f"المتاح: {' · '.join(JOBS)} — "
                "أو مجموعة: inventory · cart · loyalty · mail · presence · traffic"
            )
            raise SystemExit(2)

        if options["dry_run"]:
            self.stdout.write("سيُنفَّذ:")
            for name, (_group, label, _fn) in selected.items():
                self.stdout.write(f"  {name:24} {label}")
            return

        failed = 0

        for name, (_group, label, job) in selected.items():
            started = time.monotonic()

            try:
                count = job()
            except Exception:
                # ⚠️  الفشل يُسجَّل ولا يوقف البقية
                failed += 1
                logger.exception("فشلت المهمة الدورية %s", name)
                self.stdout.write(self.style.ERROR(f"  ✕ {label} — فشلت (انظر السجل)"))
                continue

            elapsed = time.monotonic() - started
            self.stdout.write(self.style.SUCCESS(f"  ✓ {label}: {count} ({elapsed:.2f}s)"))

        if failed:
            # ⚠️  رمز خروج غير صفري — الجدولة تكتشف الفشل بلا قراءة سجل
            self.stderr.write(self.style.ERROR(f"\n{failed} مهمة فشلت"))
            raise SystemExit(1)

    def _select(self, job: str | None) -> dict:
        if not job:
            return JOBS
        if job in JOBS:
            return {job: JOBS[job]}
        return {name: entry for name, entry in JOBS.items() if entry[0] == job}
