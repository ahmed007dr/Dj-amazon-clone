"""
خدمات حركة الاستخدام — الواجهة العامة الوحيدة لهذا النطاق.

⚠️  **العدّ في الكاش والتجميع في القاعدة.**

    العدّادات تُزاد ذرّيًا (`incr`) لا بقراءة-ثم-كتابة: طلب كل زائر
    يمرّ من هنا، وقراءة كتلة كاملة وإعادة كتابتها على كل طلب كانت
    ستُضيّع العدّ وتُثقل الشبكة معًا.

⚠️  ولا هوية شخصية تُخزَّن — لا عنوان شبكة ولا متصفح.

    الزائر يُعرَّف ببصمة مُجزّأة تبقى في الكاش ساعتين ثم تزول،
    والقاعدة لا تحفظ إلا **أعدادًا**. سجلّ زيارات باسم كل زائر
    مسؤولية قانونية دائمة مقابل سؤال إجابته رقم.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Sum
from django.db.models.functions import ExtractHour, ExtractIsoWeekDay
from django.utils import timezone

from accounts.models import DeviceType
from accounts.services import device_type_from_user_agent
from analytics.models import TrafficBucket
from core.presence import PresenceRegistry

#: نافذة اعتبار الزائر «متصفِّحًا الآن» — نفس نافذة المستخدمين.
VISITOR_WINDOW = timedelta(minutes=5)
VISITOR_HEARTBEAT = timedelta(seconds=30)

#: سجل الزوار المجهولين — موازٍ لسجل المستخدمين في `accounts`.
visitors = PresenceRegistry(
    "presence:guests", window=VISITOR_WINDOW, heartbeat=VISITOR_HEARTBEAT
)

#: العدّادات تعيش أطول من ساعتها كي ينجو التفريغ من تأخّر الجدولة.
COUNTER_TTL = 60 * 60 * 3

#: بصمة الزائر تُنسى بعد ساعتين — تكفي لتمييز ساعتين متجاورتين.
FINGERPRINT_TTL = 60 * 60 * 2

#: ⚠️  علامات الروبوتات — الزحف ليس ضغطًا بشريًا.
#
#     بدون الاستبعاد يصير «أكثر أوقات استخدام المتجر» انعكاسًا
#     لجدول زحف محرك بحث لا لسلوك العملاء، فتُبنى المناوبات على
#     ساعة لا يوجد فيها إنسان واحد.
BOT_MARKERS = (
    "bot",
    "crawler",
    "spider",
    "slurp",
    "bingpreview",
    "headless",
    "python-requests",
    "curl/",
    "wget",
    "postman",
    "lighthouse",
    "monitor",
)


# ═══════════════════════════════════════════════════════════
#  الهوية
# ═══════════════════════════════════════════════════════════


def is_bot(user_agent: str) -> bool:
    ua = (user_agent or "").lower()
    return any(marker in ua for marker in BOT_MARKERS)


def fingerprint(ip: str | None, user_agent: str) -> str:
    """
    بصمة الزائر — **مُجزَّأة لا قابلة للعكس**.

    ⚠️  الملح من `SECRET_KEY`: بلاه تصير القيمة قابلة للربط بعنوان
        شبكة معروف بتجربة الاحتمالات، فتتحوّل «إحصاءة مجهولة» إلى
        سجل تتبّع كامل.
    """
    material = f"{settings.SECRET_KEY}|{ip or ''}|{user_agent or ''}"
    return hashlib.sha256(material.encode()).hexdigest()[:32]


# ═══════════════════════════════════════════════════════════
#  العدّ
# ═══════════════════════════════════════════════════════════


def bucket_of(moment: datetime) -> datetime:
    return moment.replace(minute=0, second=0, microsecond=0)


def _key(kind: str, bucket: datetime, suffix: str) -> str:
    return f"traffic:{kind}:{bucket:%Y%m%d%H}:{suffix}"


def _bump(key: str) -> None:
    """
    ⚠️  `add` ثم `incr` — لا `get` ثم `set`.

        الثانية تفقد كل زيادة تقع بين القراءة والكتابة، وهو ما يقع
        باستمرار حين يتزامن عاملان على نفس الساعة.
    """
    cache.add(key, 0, COUNTER_TTL)
    try:
        cache.incr(key)
    except ValueError:
        # المفتاح انتهت صلاحيته بين السطرين — نادر ولا يستحق قفلًا
        cache.set(key, 1, COUNTER_TTL)


def record_visit(*, ip: str | None, user_agent: str, authenticated: bool) -> None:
    """
    تسجيل زيارة واحدة — يُستدعى من الوسيط على كل طلب متجر.

    ⚠️  المسجَّل والمجهول يُعدّان منفصلين.

        دمجهما يجعل «العملاء الأونلاين» رقمًا لا يُقرأ: عشرة
        متصفّحين مجهولين وعشرة مشترين مسجَّلين حالتان مختلفتان
        تمامًا في قرار التشغيل، ومجموعهما «٢٠» لا يقول أيًّا منهما.
    """
    if is_bot(user_agent):
        return

    now = timezone.now()
    bucket = bucket_of(now)
    device = device_type_from_user_agent(user_agent)
    identity = fingerprint(ip, user_agent)

    _bump(_key("req", bucket, device))

    # ⚠️  `add` يُرجع True مرة واحدة لكل بصمة في الساعة — وهذا بالضبط
    #     تعريف «زائر فريد»، بلا مجموعة تُقرأ وتُكتب في كل طلب.
    if cache.add(_key("seen", bucket, identity), 1, FINGERPRINT_TTL):
        _bump(_key("known" if authenticated else "guest", bucket, device))

    # ⚠️  المسجَّل لا يُضاف هنا: نبضته تقع في طبقة المصادقة حيث
    #     يُعرَف **من هو**، وعدّه مرتين يضخّم «المتصلون الآن».
    if not authenticated:
        visitors.touch(identity)


def guests_online() -> int:
    """عدد المتصفّحين المجهولين الآن."""
    return visitors.count()


# ═══════════════════════════════════════════════════════════
#  التفريغ
# ═══════════════════════════════════════════════════════════


def flush_traffic() -> int:
    """
    تفريغ عدّادات الساعة إلى `TrafficBucket`.

    ⚠️  الساعة السابقة تُفرَّغ مع الحالية.

        تفريغ الحالية وحدها يفقد آخر دقائق كل ساعة إذا تأخّرت
        الجدولة لحظة عبور الساعة — وهي لحظة الذروة أحيانًا.

    ⚠️  والقيم تُكتب **بالأكبر لا بالإحلال**.

        العدّادات تعيش في الكاش؛ إعادة تشغيله تُصفّرها، فالكتابة
        المباشرة كانت ستمحو ساعةً مسجَّلة وتضع صفرًا مكانها.
    """
    now = timezone.now()
    buckets = (bucket_of(now) - timedelta(hours=1), bucket_of(now))

    written = 0
    for bucket in buckets:
        for device in DeviceType.values:
            counts = {
                "requests": cache.get(_key("req", bucket, device)) or 0,
                "guest_visitors": cache.get(_key("guest", bucket, device)) or 0,
                "known_visitors": cache.get(_key("known", bucket, device)) or 0,
            }
            if not any(counts.values()):
                continue

            row, created = TrafficBucket.objects.get_or_create(
                bucket_start=bucket, device_type=device, defaults=counts
            )

            if not created:
                changed = [
                    field for field, value in counts.items() if value > getattr(row, field)
                ]
                if not changed:
                    continue
                for field in changed:
                    setattr(row, field, counts[field])
                row.save(update_fields=changed)

            written += 1

    return written


def purge_traffic(days: int = 90) -> int:
    """
    ⚠️  الاحتفاظ محدود عمدًا.

        حركة لا يقرأها أحد بعد ثلاثة أشهر تبقى مسؤوليةً بلا فائدة —
        والسؤال التشغيلي («متى الضغط؟») موسمي لا تاريخي.
    """
    cutoff = bucket_of(timezone.now()) - timedelta(days=days)
    deleted, _ = TrafficBucket.objects.filter(bucket_start__lt=cutoff).delete()
    return deleted


# ═══════════════════════════════════════════════════════════
#  القراءة
# ═══════════════════════════════════════════════════════════


def _period_rows(start: date, end: date):
    return TrafficBucket.objects.filter(
        bucket_start__date__gte=start, bucket_start__date__lte=end
    )


def traffic_summary(start: date, end: date) -> dict:
    """حركة فترة — مجمّعة ومقسّمة على الأجهزة."""
    rows = _period_rows(start, end)

    totals = rows.aggregate(
        requests=Sum("requests"),
        guests=Sum("guest_visitors"),
        known=Sum("known_visitors"),
    )

    by_device = [
        {
            "device_type": row["device_type"],
            "requests": row["requests"] or 0,
            "guest_visitors": row["guests"] or 0,
            "known_visitors": row["known"] or 0,
        }
        for row in rows.values("device_type")
        .annotate(
            requests=Sum("requests"),
            guests=Sum("guest_visitors"),
            known=Sum("known_visitors"),
        )
        .order_by("-requests")
    ]

    return {
        "start": str(start),
        "end": str(end),
        "requests": totals["requests"] or 0,
        "guest_visitors": totals["guests"] or 0,
        "known_visitors": totals["known"] or 0,
        "by_device": by_device,
    }


def traffic_peak_hours(start: date, end: date) -> dict:
    """
    توزيع الزوار على ساعات الأسبوع — نفس شبكة `reporting.peak_hours`.

    ⚠️  السؤالان مختلفان: هذه ذروة **التصفّح**، وتلك ذروة **الشراء**.

        والفجوة بينهما هي المعلومة الحقيقية: ساعة يتصفّح فيها الناس
        ولا يشترون تعني مشكلة سعر أو مخزون لا نقص زيارات.

    ⚠️  والشبكة مكتملة دائمًا — خريطة حرارية بخلايا ناقصة تُرسم مشوّهة.
    """
    rows = (
        _period_rows(start, end)
        .annotate(
            weekday=ExtractIsoWeekDay("bucket_start"),
            hour=ExtractHour("bucket_start"),
        )
        .values("weekday", "hour")
        .annotate(
            requests=Sum("requests"),
            guests=Sum("guest_visitors"),
            known=Sum("known_visitors"),
        )
    )

    grid = {(row["weekday"], row["hour"]): row for row in rows}

    cells = []
    for weekday in range(1, 8):
        for hour in range(24):
            row = grid.get((weekday, hour))
            visitor_count = ((row["guests"] or 0) + (row["known"] or 0)) if row else 0
            cells.append(
                {
                    "weekday": weekday,
                    "hour": hour,
                    "requests": (row["requests"] or 0) if row else 0,
                    "visitors": visitor_count,
                }
            )

    busiest = max(cells, key=lambda cell: cell["visitors"])

    return {
        "start": str(start),
        "end": str(end),
        "timezone": str(timezone.get_current_timezone()),
        "cells": cells,
        # ⚠️  فترة بلا حركة تُرجع `None` لا الخلية الأولى بصفر زائر
        "peak_cell": busiest if busiest["visitors"] else None,
    }
