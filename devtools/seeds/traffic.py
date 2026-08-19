"""
بذرة الزمن — حركة الزوار وتوزيع الطلبات على ساعات الأسبوع.

⚠️  **بذرة يقع فيها كل شيء في الثانية نفسها لا تُظهر شيئًا.**

    شاشة الضغط تجيب «متى؟»، وبيانات كلها في لحظة الإنشاء تُنتج خلية
    واحدة مضيئة و١٦٧ فارغة — فتبدو الشاشة معطّلة لا فارغة. ولذلك
    هذه البذرة تُوزّع الزمن قبل أي شيء آخر.

⚠️  والشكل **ليس عشوائيًا منتظمًا**.

    توزيع مسطّح يجعل الخريطة رمادية بلا ذروة، فلا يُرى الفرق بين
    «تعمل» و«لا تعمل». الشكل هنا يحاكي متجرًا حقيقيًا: ذروة مساء،
    وهدوء فجرًا، ونهاية أسبوع أعلى — وهو ما يجعل خطأً في حساب
    المنطقة الزمنية **مرئيًا** بدل أن يمرّ.
"""

from __future__ import annotations

import random
from datetime import timedelta

from django.utils import timezone

from accounts.models import DeviceType
from analytics.models import TrafficBucket

#: عدد الأيام المبذورة — يطابق النافذة الافتراضية في شاشة الضغط.
DAYS = 30

#: وزن كل ساعة (٠–٢٣) — ذروة مساء وهدوء فجرًا.
HOUR_WEIGHTS = [
    2, 1, 1, 1, 1, 2, 4, 7, 11, 14, 16, 18,
    17, 15, 14, 16, 20, 26, 30, 28, 22, 15, 9, 4,
]

#: وزن كل يوم بترتيب ISO — الاثنين ١ … الأحد ٧.
#
# ⚠️  الجمعة أدنى: عطلة الأسبوع في السوق المصري، والذروة تسبقها
#     وتليها. رقمٌ يخالف الواقع المحلي يجعل الشاشة تُقرأ ولا تُصدَّق.
WEEKDAY_WEIGHTS = {1: 1.0, 2: 1.05, 3: 1.0, 4: 1.1, 5: 0.55, 6: 0.9, 7: 0.95}

#: توزيع الأجهزة — الهاتف أولًا، وهو واقع أي متجر تجزئة.
DEVICE_SHARE = {
    DeviceType.MOBILE: 0.62,
    DeviceType.DESKTOP: 0.28,
    DeviceType.TABLET: 0.08,
    DeviceType.UNKNOWN: 0.02,
}

#: ⚠️  بذرة ثابتة — تشغيلان متتاليان يُنتجان نفس الشاشة.
#
#     أرقام تتغيّر في كل تشغيل تجعل «هل تغيّر شيء بعد تعديلي؟»
#     سؤالًا بلا إجابة.
SEED = 20260818


def _shape(moment) -> float:
    local = timezone.localtime(moment)
    return HOUR_WEIGHTS[local.hour] * WEEKDAY_WEIGHTS[local.isoweekday()]


def seed() -> dict:
    """
    ⚠️  تُنادى **بعد** بذرة الطلبات لا قبلها — توزّع ما أُنشئ.
    """
    from orders.models import Order

    rng = random.Random(SEED)
    now = timezone.localtime(timezone.now())

    # ── توزيع الطلبات على الزمن ────────────────────────────
    #
    # ⚠️  `update` لا `save`: `created_at` حقل `auto_now_add`،
    #     و`save()` تُعيد كتابته بلحظة الحفظ فيُلغي التوزيع كله.
    spread = 0
    for order_id in Order.objects.values_list("pk", flat=True):
        Order.objects.filter(pk=order_id).update(created_at=_pick_moment(rng, now))
        spread += 1

    # ── حركة الزوار ────────────────────────────────────────
    buckets = []
    for day_offset in range(DAYS):
        day = now - timedelta(days=day_offset)

        for hour in range(24):
            moment = day.replace(hour=hour, minute=0, second=0, microsecond=0)
            if moment > now:
                continue

            visitors = int(_shape(moment) * rng.uniform(0.6, 1.4))
            if visitors <= 0:
                continue

            for device, share in DEVICE_SHARE.items():
                count = int(visitors * share)
                if count <= 0:
                    continue

                # ⚠️  الزائر المسجَّل أقلية — معظم من يتصفّح متجرًا
                #     لا يسجّل دخولًا، وهو سبب وجود العدّ المجهول.
                known = int(count * 0.22)

                buckets.append(
                    TrafficBucket(
                        bucket_start=moment,
                        device_type=device,
                        # الطلبات أكثر من الزوار: كل زائر يتصفّح صفحات
                        requests=count * rng.randint(4, 11),
                        guest_visitors=count - known,
                        known_visitors=known,
                    )
                )

    TrafficBucket.objects.bulk_create(buckets, ignore_conflicts=True)

    return {
        "counts": {
            "traffic_buckets": len(buckets),
            "orders_spread": spread,
            "days": DAYS,
        }
    }


def _pick_moment(rng: random.Random, now):
    """
    لحظة داخل آخر `DAYS` يومًا **موزونة بشكل المتجر**.

    ⚠️  الرفض-وإعادة-المحاولة لا الاختيار المنتظم: الأخير يجعل
        ذروة الشراء مسطّحة بينما ذروة التصفّح حادّة — تناقضٌ في
        نفس الشاشة يبدو خطأً في الحساب لا في البذرة.
    """
    peak = max(HOUR_WEIGHTS) * max(WEEKDAY_WEIGHTS.values())

    for _ in range(64):
        moment = now - timedelta(
            days=rng.randint(0, DAYS - 1),
            hours=rng.randint(0, 23),
            minutes=rng.randint(0, 59),
        )
        if rng.uniform(0, peak) <= _shape(moment):
            return moment

    return now - timedelta(days=rng.randint(0, DAYS - 1))
