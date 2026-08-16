"""
خدمات الولاء والإحالة.

⚠️  **كل مسار كسب أو استبدال يمرّ بفحص التشغيل والاستهداف.**

    مفتاح الإيقاف الذي يُفحَص في نقطة واحدة ويُنسى في أخرى ليس
    مفتاحًا: يكفي مسار واحد لا يفحصه ليستمر الالتزام بالتراكم بعد
    أن يظنّ الأدمن أنه أوقفه.
"""

from __future__ import annotations

import logging
import secrets
import string
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Case, F, IntegerField, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.errors import BusinessError, ErrorCode
from core.money import ZERO, quantize
from loyalty.models import (
    CREDIT_KINDS,
    LoyaltyProgram,
    PointsEntry,
    PointsKind,
    Referral,
    ReferralCode,
    ReferralProgram,
    ReferralStatus,
    TierLevel,
)

logger = logging.getLogger(__name__)

#: ⚠️  بلا أحرف تلتبس بالأرقام (O/0 · I/1) — الكود يُملى هاتفيًا
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8


# ═══════════════════════════════════════════════════════════
#  اختيار البرنامج — بوابة التشغيل والاستهداف
# ═══════════════════════════════════════════════════════════


def program_for(user, customer=None) -> LoyaltyProgram | None:
    """
    البرنامج المطبَّق على هذا العميل — **أو `None`**.

    ⚠️  **هذه الدالة هي المفتاح الحقيقي.**

        كل كسب واستبدال يمرّ بها. إيقاف البرنامج أو تغيير استهدافه
        يسري فورًا على كل المسارات، بلا أن يحتاج أيٌّ منها تعديلًا.

    ⚠️  و`None` **ليست خطأً**.

        حساب خارج الاستهداف حالة عادية مقصودة: النظام قد يكون
        للطلاب وحدهم. المسارات تتعامل معها بالصمت لا بالاستثناء.
    """
    if not (user and getattr(user, "is_authenticated", False)):
        return None

    for program in LoyaltyProgram.objects.filter(is_active=True).order_by("code"):
        if program.covers(user, customer):
            return program

    return None


def is_earning_enabled(user, customer=None) -> bool:
    return program_for(user, customer) is not None


# ═══════════════════════════════════════════════════════════
#  الرصيد
# ═══════════════════════════════════════════════════════════


def balance(customer) -> int:
    """
    رصيد النقاط — **مشتق من الدفتر**.

    ⚠️  لا حقل `points_balance` مخزَّن: انحرافه يعني عميلًا يستبدل
        ما لا يملك أو يُمنَع مما يملك.
    """
    total = PointsEntry.objects.filter(customer=customer).aggregate(
        total=Coalesce(
            Sum(
                Case(
                    When(kind__in=list(CREDIT_KINDS), then=F("points")),
                    default=-F("points"),
                    output_field=IntegerField(),
                )
            ),
            Value(0),
        )
    )["total"]
    return max(total or 0, 0)


def available_batches(customer):
    """
    دفعات النقاط الصالحة — **الأقدم انتهاءً أولًا**.

    ⚠️  استهلاك الأحدث أولًا يجعل الأقدم ينتهي دائمًا بلا استعمال،
        فيخسر العميل نقاطًا كسبها بينما يستبدل غيرها — وهو ما
        يُقرأ غشًّا لا سياسة.
    """
    today = timezone.localdate()

    return (
        PointsEntry.objects.filter(
            customer=customer,
            kind__in=list(CREDIT_KINDS),
            points_remaining__gt=0,
        )
        .filter(Q(expires_on__isnull=True) | Q(expires_on__gte=today))
        .order_by(F("expires_on").asc(nulls_last=True), "created_at")
    )


def usable_points(customer) -> int:
    """
    ⚠️  المتاح للاستبدال ≠ الرصيد الإجمالي.

        الرصيد يشمل نقاطًا انتهت صلاحيتها ولم تُنظَّف بعد. عرضه
        للاستبدال يجعل العميل يبني عليه ثم يُرفض.
    """
    total = available_batches(customer).aggregate(
        total=Coalesce(Sum("points_remaining"), Value(0))
    )["total"]
    return total or 0


def tier_for(customer, program: LoyaltyProgram) -> TierLevel | None:
    """
    فئة العميل — **بإجمالي إنفاقه المخزَّن**.

    ⚠️  الحساب من الطلبات لحظيًا يجعل كل عرض للفئة يمسح تاريخ
        العميل كاملًا. `total_spent` مُحدَّث بحدث الاكتمال أصلًا.
    """
    spent = getattr(customer, "total_spent", ZERO) or ZERO

    return (
        TierLevel.objects.filter(program=program, threshold__lte=spent)
        .order_by("-threshold")
        .first()
    )


# ═══════════════════════════════════════════════════════════
#  الكسب
# ═══════════════════════════════════════════════════════════


def earnable_amount(order, program: LoyaltyProgram) -> Decimal:
    """
    المبلغ الذي تُحسب عليه النقاط.

    ⚠️  الضريبة والشحن **خارج الحساب افتراضيًا**.

        الضريبة تُحصَّل للدولة ولا نملكها، والشحن يُدفَع للناقل.
        مكافأة العميل عليهما تكافئه على ما لم نربح منه — والفارق
        يبلغ ربع الطلب أحيانًا.
    """
    amount = order.grand_total

    if not program.earns_on_tax:
        amount -= order.tax_total
    if not program.earns_on_shipping:
        amount -= order.shipping_total

    return max(quantize(amount), ZERO)


@transaction.atomic
def award_for_order(order) -> PointsEntry | None:
    """
    يمنح نقاط طلب مكتمل — **مرة واحدة مهما تكرّر الحدث**.

    ⚠️  الترتيب مقصود:

          ١. البرنامج المطبَّق  ← الإيقاف والاستهداف يُفحصان أولًا
          ٢. الحد الأدنى للطلب
          ٣. المبلغ المؤهَّل    ← بلا ضريبة ولا شحن افتراضيًا
          ٤. مضاعِف الفئة
          ٥. القيد بتاريخ انتهاء

    ⚠️  والازدواج يمنعه قيد قاعدة البيانات لا الفحص هنا وحده:
        الفحص المسبق يخسر السباق بين حدثين متزامنين.
    """
    customer = order.customer
    if customer is None:
        # بيعة كاونتر بلا عميل مسجَّل — لا أحد يُكافأ
        return None

    program = program_for(customer.user, customer)
    if program is None:
        return None

    if order.grand_total < program.min_order_amount:
        return None

    existing = PointsEntry.objects.filter(order=order, kind=PointsKind.EARN).first()
    if existing is not None:
        logger.info("نقاط الطلب %s ممنوحة سلفًا — تجاهل", order.number)
        return existing

    amount = earnable_amount(order, program)
    points = program.points_for(amount)

    tier = tier_for(customer, program)
    if tier is not None:
        points = int(points * tier.multiplier)

    if points <= 0:
        return None

    return PointsEntry.objects.create(
        customer=customer,
        program=program,
        kind=PointsKind.EARN,
        points=points,
        points_remaining=points,
        order=order,
        expires_on=_expiry_for(program),
        reference=order.number,
    )


def _expiry_for(program: LoyaltyProgram) -> date | None:
    """
    ⚠️  صفر شهرًا = بلا انتهاء، ويُختار صراحةً.

        الافتراضي اثنا عشر شهرًا لأن الالتزام غير المنتهي يتراكم
        بلا سقف في الدفتر.
    """
    if program.expiry_months <= 0:
        return None

    today = timezone.localdate()
    month_index = today.year * 12 + (today.month - 1) + program.expiry_months
    year, month = divmod(month_index, 12)

    # ⚠️  اليوم يُقصَّ إلى آخر الشهر: ٣١ يناير + شهر ليس ٣١ فبراير
    import calendar

    day = min(today.day, calendar.monthrange(year, month + 1)[1])
    return date(year, month + 1, day)


@transaction.atomic
def reverse_for_order(order, *, reason: str = "مرتجع") -> PointsEntry | None:
    """
    يسحب نقاط طلب مُرتجَع.

    ⚠️  بدونه: يشتري · يكسب · يُرجِع · ويحتفظ بالنقاط — وهو أبسط
        استغلال ممكن في أي نظام ولاء.

    ⚠️  والسحب **لا يُنقص الرصيد تحت الصفر**.

        العميل قد يكون استبدل نقاطه قبل الإرجاع. الخصم إلى السالب
        يجعله مدينًا بنقاط، وهو مفهوم لا وجود له — والفارق يُسجَّل
        ملاحظةً بدل أن يُخترَع دين.
    """
    if PointsEntry.objects.filter(order=order, kind=PointsKind.REVERSE).exists():
        return None

    earned = PointsEntry.objects.filter(order=order, kind=PointsKind.EARN).first()
    if earned is None:
        return None

    program = earned.program
    if not program.reverse_on_refund:
        return None

    current = balance(earned.customer)
    points = min(earned.points, current)

    if points <= 0:
        return None

    # ⚠️  استهلاك ما تبقّى من دفعة الكسب نفسها أولًا: تركه يجعل
    #     نقاطًا سُحبت تبقى قابلة للاستبدال.
    _consume(earned.customer, points)

    note = reason
    if points < earned.points:
        note = f"{reason} — سُحب {points} من {earned.points} (الباقي استُبدل سلفًا)"

    return PointsEntry.objects.create(
        customer=earned.customer,
        program=program,
        kind=PointsKind.REVERSE,
        points=points,
        order=order,
        reference=order.number,
        note=note,
    )


def _consume(customer, points: int) -> int:
    """
    يستهلك النقاط من الدفعات — **الأقدم انتهاءً أولًا**.

    ⚠️  يعيد ما استُهلك فعلًا: قد يقلّ عن المطلوب حين تنقص
        الدفعات المتاحة عن الرصيد الإجمالي (نقاط انتهت ولم تُنظَّف).
    """
    remaining = points

    for batch in available_batches(customer).select_for_update():
        if remaining <= 0:
            break

        take = min(batch.points_remaining, remaining)
        PointsEntry.objects.filter(pk=batch.pk).update(
            points_remaining=F("points_remaining") - take
        )
        remaining -= take

    return points - remaining


# ═══════════════════════════════════════════════════════════
#  الاستبدال
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RedemptionQuote:
    allowed: bool
    reason: str = ""
    points: int = 0
    value: Decimal = ZERO
    max_points: int = 0


def quote_redemption(customer, points: int, order_total: Decimal) -> RedemptionQuote:
    """
    ⚠️  السقف نسبة من الطلب لا رقم مطلق.

        بلا سقف يُدفَع طلب كامل بالنقاط، فيخرج المتجر ببضاعة بلا
        نقد — والنقاط لا تدفع أجور الموردين.
    """
    program = program_for(customer.user, customer)

    if program is None:
        return RedemptionQuote(False, "لا برنامج ولاء على هذا الحساب")

    if not program.redemption_enabled:
        return RedemptionQuote(False, "الاستبدال موقوف مؤقتًا")

    if points <= 0:
        return RedemptionQuote(False, "عدد النقاط يجب أن يكون موجبًا")

    available = usable_points(customer)
    if points > available:
        return RedemptionQuote(False, f"المتاح {available} نقطة", max_points=available)

    ceiling = quantize(order_total * program.max_redemption_percent / Decimal("100"))
    value = quantize(points * program.point_value)

    if value > ceiling:
        max_points = (
            int(ceiling / program.point_value) if program.point_value > ZERO else 0
        )
        return RedemptionQuote(
            False,
            f"أقصى استبدال {program.max_redemption_percent}٪ من الطلب ({ceiling})",
            max_points=min(max_points, available),
        )

    return RedemptionQuote(True, points=points, value=value, max_points=available)


@transaction.atomic
def redeem(customer, points: int, order_total: Decimal, *, actor=None):
    """
    يستبدل نقاطًا بكوبون شخصي.

    ⚠️  **الاستبدال يُنتج كوبونًا لا خصمًا مباشرًا.**

        الخصم المباشر كان يتطلّب أن يعرف `orders` و`cart` بوجود
        الولاء — وهما **تحته** في ترتيب الطبقات. والكوبون مسار
        مُختبَر بالكامل: حدود استخدام، وصلاحية، وتصفية بالعميل.

    ⚠️  والنقاط تُخصم **قبل** إنشاء الكوبون.

        العكس يترك كوبونًا صالحًا بلا خصم لو فشل الاستهلاك.
    """
    from promotions.models import Coupon, CouponKind

    result = quote_redemption(customer, points, order_total)
    if not result.allowed:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail=result.reason)

    program = program_for(customer.user, customer)

    consumed = _consume(customer, points)
    if consumed < points:
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail=f"تعذّر استهلاك {points} نقطة — المتاح {consumed}",
            status_code=409,
        )

    entry = PointsEntry.objects.create(
        customer=customer,
        program=program,
        kind=PointsKind.REDEEM,
        points=points,
        reference="",
        recorded_by=actor,
    )

    code = f"PTS-{_random_code(6)}"
    coupon = Coupon.objects.create(
        code=code,
        name_ar=f"استبدال {points} نقطة",
        name_en=f"Redeem {points} points",
        kind=CouponKind.FIXED,
        value=result.value,
        # ⚠️  استخدام واحد لمستخدم واحد: الكوبون ثمن نقاط استُهلكت،
        #     ومشاركته تعني خصمًا مجانيًا لمن لم يدفع ثمنه.
        usage_limit=1,
        usage_limit_per_user=1,
        # ⚠️  مربوط بصاحبه: `usage_limit=1` وحده يحدّ العدد لا
        #     الشخص، فيكفي أن يُصوَّر الكود ليصرفه غيرُه — ونقاطه
        #     هو التي استُهلكت.
        owner=customer.user,
        starts_at=timezone.now(),
        # ⚠️  صلاحية محدودة: كوبون بلا نهاية يُستبدَل اليوم ويُستعمل
        #     بعد سنتين، فيبقى الالتزام مفتوحًا في الدفتر إلى الأبد.
        ends_at=timezone.now() + timedelta(days=30),
        is_active=True,
    )

    entry.reference = coupon.code
    PointsEntry.objects.filter(pk=entry.pk).update(reference=coupon.code)

    return {"entry": entry, "coupon": coupon, "value": result.value}


@transaction.atomic
def adjust_points(customer, points: int, *, reason: str, actor=None) -> PointsEntry:
    """
    تسوية يدوية من الأدمن — **موجبة أو سالبة**.

    ⚠️  **السبب إلزامي.**

        تسوية بلا سبب تصير رقمًا لا يُفسَّر بعد شهر، والدفتر
        الذي لا يُفسَّر لا يُدقَّق. وهذه أخطر حركة في النظام:
        نقاط تُخلَق أو تُمحى بلا طلب يقابلها.

    ⚠️  والسحب **لا ينزل بالرصيد تحت الصفر**: العميل لا يَدين
        بنقاط، والفارق يُسجَّل في الملاحظة بدل أن يُخترَع دين.
    """
    reason = (reason or "").strip()
    if not reason:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="سبب التسوية إلزامي")

    if points == 0:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="التسوية بصفر بلا معنى")

    program = program_for(customer.user, customer)
    if program is None:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR, detail="لا برنامج ولاء يشمل هذا العميل"
        )

    if points > 0:
        return PointsEntry.objects.create(
            customer=customer,
            program=program,
            kind=PointsKind.ADJUSTMENT,
            points=points,
            points_remaining=points,
            expires_on=_expiry_for(program),
            note=reason,
            recorded_by=actor,
        )

    wanted = abs(points)
    taken = min(wanted, balance(customer))
    if taken <= 0:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="رصيد العميل صفر")

    _consume(customer, taken)

    note = reason
    if taken < wanted:
        note = f"{reason} — سُحب {taken} من {wanted} (الرصيد لا يكفي)"

    return PointsEntry.objects.create(
        customer=customer,
        program=program,
        kind=PointsKind.DEDUCTION,
        points=taken,
        note=note,
        recorded_by=actor,
    )


def outstanding_liability() -> dict:
    """
    ⚠️  **النقاط التزام لا رصيد تسويقي.**

        كل نقطة قائمة وعدٌ بخصم مستقبلي. عرضها عددًا فقط يخفي
        قيمتها بالجنيه — وهي ما يظهر في الميزانية حين تُصرَف.
    """
    today = timezone.localdate()

    rows = (
        PointsEntry.objects.filter(
            kind__in=list(CREDIT_KINDS),
            points_remaining__gt=0,
        )
        .filter(Q(expires_on__isnull=True) | Q(expires_on__gte=today))
        .values("program__point_value")
        .annotate(points=Coalesce(Sum("points_remaining"), Value(0)))
    )

    points = 0
    value = ZERO
    for row in rows:
        points += row["points"]
        value += (row["program__point_value"] or ZERO) * row["points"]

    return {"points": points, "value": quantize(value)}


def _random_code(length: int) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


@transaction.atomic
def expire_points() -> dict:
    """
    يُسقط النقاط المنتهية — **بحركة مسجَّلة لا بحذف**.

    ⚠️  الحذف يجعل العميل يرى رصيده ينقص بلا سبب في كشفه.
        الحركة تقول متى انتهت وكم كانت.
    """
    today = timezone.localdate()

    stale = PointsEntry.objects.filter(
        kind__in=list(CREDIT_KINDS),
        points_remaining__gt=0,
        expires_on__isnull=False,
        expires_on__lt=today,
    ).select_related("customer", "program")

    expired_points = 0
    affected = 0

    for batch in stale:
        points = batch.points_remaining

        PointsEntry.objects.filter(pk=batch.pk).update(points_remaining=0)
        PointsEntry.objects.create(
            customer=batch.customer,
            program=batch.program,
            kind=PointsKind.EXPIRE,
            points=points,
            reference=batch.reference,
            note=f"انتهت في {batch.expires_on}",
        )

        expired_points += points
        affected += 1

    if affected:
        logger.info("أُسقطت %s نقطة من %s دفعة", expired_points, affected)

    return {"batches": affected, "points": expired_points}


# ═══════════════════════════════════════════════════════════
#  الإحالة
# ═══════════════════════════════════════════════════════════


def active_referral_program(user) -> ReferralProgram | None:
    for program in ReferralProgram.objects.filter(is_active=True).order_by("code"):
        if not program.account_types or user.account_type in program.account_types:
            return program
    return None


@transaction.atomic
def ensure_referral_code(user) -> ReferralCode:
    """
    ⚠️  الكود يُولَّد عند الطلب لا لكل مستخدم.

        توليده للجميع يملأ الجدول بأكواد لا تُستعمل، ويستهلك مساحة
        الأكواد القصيرة القابلة للإملاء هاتفيًا.
    """
    existing = ReferralCode.objects.filter(user=user).first()
    if existing is not None:
        return existing

    for _ in range(10):
        code = _random_code(CODE_LENGTH)
        if not ReferralCode.objects.filter(code=code).exists():
            return ReferralCode.objects.create(user=user, code=code)

    raise BusinessError(ErrorCode.INTERNAL_ERROR, detail="تعذّر توليد كود إحالة")


@transaction.atomic
def register_referral(referee, code: str, *, ip: str = "") -> Referral:
    """
    يسجّل إحالة عند التسجيل — **بلا مكافأة بعد**.

    ⚠️  **أربعة حواجز ضد التلاعب، وكلها لازمة:**

          ١. لا إحالة ذاتية       ← أوضح استغلال
          ٢. المُحال مرة واحدة    ← يفرضه قيد `OneToOne`
          ٣. سقف لكل مُحيل        ← يحدّ من مزارع الحسابات
          ٤. المكافأة عند أول طلب مكتمل ← البضاعة خرجت والمال دخل

        إسقاط أيٍّ منها يجعل الباقي بلا معنى: من يستطيع فتح مئة
        حساب لا يوقفه سقف وحده.
    """
    referral_program = active_referral_program(referee)
    if referral_program is None:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="لا برنامج إحالة نشط")

    entry = ReferralCode.objects.filter(code=code.upper(), is_active=True).first()
    if entry is None:
        raise BusinessError(ErrorCode.NOT_FOUND, detail="كود إحالة غير صالح", status_code=404)

    if entry.user_id == referee.pk:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="لا تصحّ إحالة النفس")

    if Referral.objects.filter(referee=referee).exists():
        raise BusinessError(
            ErrorCode.CONFLICT, detail="هذا الحساب مُحال سلفًا", status_code=409
        )

    if referral_program.max_referrals_per_user > 0:
        made = Referral.objects.filter(
            referrer=entry.user, status=ReferralStatus.REWARDED
        ).count()
        if made >= referral_program.max_referrals_per_user:
            raise BusinessError(
                ErrorCode.VALIDATION_ERROR, detail="بلغ المُحيل سقف إحالاته"
            )

    return Referral.objects.create(
        program=referral_program,
        referrer=entry.user,
        referee=referee,
        signup_ip=ip or None,
    )


@transaction.atomic
def reward_referral(order) -> Referral | None:
    """
    يكافئ الإحالة عند **أول طلب مكتمل** للمُحال.

    ⚠️  «أول طلب» يُقاس بعدد طلباته المكتملة لا بتاريخ تسجيله.

        القياس بالتاريخ يجعل من سجّل ولم يشترِ إلا بعد سنة غير
        مؤهَّل — وهو عميل حقيقي جلبه مُحيل حقيقي.
    """
    customer = order.customer
    if customer is None:
        return None

    referral = Referral.objects.filter(
        referee=customer.user, status=ReferralStatus.PENDING
    ).select_related("program").first()

    if referral is None:
        return None

    if order.grand_total < referral.program.min_order_amount:
        return None

    from customers.models import CustomerProfile

    referrer_customer = CustomerProfile.objects.filter(user=referral.referrer).first()

    # ⚠️  **كل طرف يُفحَص ببرنامجه هو.**
    #
    #     منح الطرفين من برنامج المُحيل كان يثقب الاستهداف: صيدلية
    #     داخل البرنامج تُحيل طالبًا خارجه، فيكسب الطالب نقاطًا من
    #     برنامج لا يشمله — والأدمن الذي حصر النظام في الصيدليات
    #     يجدها تُصرَف على غيرهم.
    referrer_program = program_for(referral.referrer, referrer_customer)
    referee_program = program_for(customer.user, customer)

    if referrer_program is None and referee_program is None:
        # ⚠️  المكافأة نقاط، وبلا برنامج ولاء نشط لا وعاء لها.
        #     تُترك معلَّقة لا مرفوضة: تفعيل البرنامج لاحقًا يكافئها.
        logger.info("إحالة %s معلَّقة — لا برنامج ولاء لأيٍّ من الطرفين", referral.pk)
        return None

    if (
        referrer_customer is not None
        and referrer_program is not None
        and referral.program.referrer_points > 0
    ):
        PointsEntry.objects.create(
            customer=referrer_customer,
            program=referrer_program,
            kind=PointsKind.REFERRAL,
            points=referral.program.referrer_points,
            points_remaining=referral.program.referrer_points,
            expires_on=_expiry_for(referrer_program),
            reference=f"referral:{referral.pk}",
            note="مكافأة إحالة",
        )

    if referee_program is not None and referral.program.referee_points > 0:
        PointsEntry.objects.create(
            customer=customer,
            program=referee_program,
            kind=PointsKind.REFERRAL,
            points=referral.program.referee_points,
            points_remaining=referral.program.referee_points,
            expires_on=_expiry_for(referee_program),
            reference=f"referral:{referral.pk}",
            note="مكافأة انضمام بإحالة",
        )

    referral.status = ReferralStatus.REWARDED
    referral.qualifying_order = order
    referral.rewarded_at = timezone.now()
    referral.save(update_fields=["status", "qualifying_order", "rewarded_at", "updated_at"])

    return referral


def referral_stats(user) -> dict:
    """إحصاءات المُحيل — للوحة السفير."""
    rows = Referral.objects.filter(referrer=user)

    return {
        "total": rows.count(),
        "pending": rows.filter(status=ReferralStatus.PENDING).count(),
        "rewarded": rows.filter(status=ReferralStatus.REWARDED).count(),
        "rejected": rows.filter(status=ReferralStatus.REJECTED).count(),
    }
