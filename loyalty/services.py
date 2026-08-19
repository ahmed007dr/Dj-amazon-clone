"""
Loyalty and referral services.

⚠️  **Every earning or redemption path goes through the enablement and targeting check.**

    An off switch checked at one point and forgotten at another is not a switch:
    one path that does not check is enough for the liability to keep
    accumulating after the admin believes they stopped it.
"""

from __future__ import annotations

import logging
import secrets
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

#: ⚠️  No characters confusable with digits (O/0 · I/1) — the code is dictated over the phone
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8


# ═══════════════════════════════════════════════════════════
#  Programme selection — the enablement and targeting gate
# ═══════════════════════════════════════════════════════════


def program_for(user, customer=None) -> LoyaltyProgram | None:
    """
    The programme applying to this customer — **or `None`**.

    ⚠️  **This function is the real switch.**

        Every earning and redemption passes through it. Disabling the programme
        or changing its targeting takes effect immediately across every path,
        with none of them needing a change.

    ⚠️  And `None` **is not an error**.

        An account outside the targeting is a normal, intended state: the system
        may be for students alone. The paths handle it with silence rather than
        an exception.
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
#  Balance
# ═══════════════════════════════════════════════════════════


def balance(customer) -> int:
    """
    The points balance — **derived from the ledger**.

    ⚠️  There is no stored `points_balance` field: its drift means a customer
        redeeming what they do not have, or being denied what they do.
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
    The valid points batches — **soonest to expire first**.

    ⚠️  Consuming the newest first makes the oldest always expire unused, so the
        customer loses points they earned while redeeming others — which reads
        as cheating rather than policy.
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
    ⚠️  Available for redemption ≠ the total balance.

        The balance includes points that have expired and not yet been cleaned
        up. Showing that for redemption makes the customer build on it and then
        be refused.
    """
    total = available_batches(customer).aggregate(
        total=Coalesce(Sum("points_remaining"), Value(0))
    )["total"]
    return total or 0


def tier_for(customer, program: LoyaltyProgram) -> TierLevel | None:
    """
    The customer's tier — **from their stored total spend**.

    ⚠️  Computing it from the orders on the fly makes every display of the tier
        scan the customer's entire history. `total_spent` is already updated by
        the completion event.
    """
    spent = getattr(customer, "total_spent", ZERO) or ZERO

    return (
        TierLevel.objects.filter(program=program, threshold__lte=spent)
        .order_by("-threshold")
        .first()
    )


# ═══════════════════════════════════════════════════════════
#  Earning
# ═══════════════════════════════════════════════════════════


def earnable_amount(order, program: LoyaltyProgram) -> Decimal:
    """
    The amount points are calculated on.

    ⚠️  Tax and shipping are **outside the calculation by default**.

        Tax is collected for the state and we do not own it, and shipping is
        paid to the carrier. Rewarding the customer on them rewards them on what
        we did not profit from — and the difference reaches a quarter of the
        order at times.
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
    Awards a completed order's points — **once, however often the event repeats**.

    ⚠️  The order is deliberate:

          1. the applicable programme  ← enablement and targeting are checked first
          2. the order minimum
          3. the eligible amount       ← excluding tax and shipping by default
          4. the tier multiplier
          5. the entry with an expiry date

    ⚠️  And duplication is prevented by a database constraint, not by the check
        here alone: a pre-check loses the race between two concurrent events.
    """
    customer = order.customer
    if customer is None:
        # A counter sale with no registered customer — there is nobody to reward
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
    ⚠️  Zero months = no expiry, and it is chosen explicitly.

        The default is twelve months, because a liability that never expires
        accumulates uncapped in the ledger.
    """
    if program.expiry_months <= 0:
        return None

    today = timezone.localdate()
    month_index = today.year * 12 + (today.month - 1) + program.expiry_months
    year, month = divmod(month_index, 12)

    # ⚠️  The day is clamped to the month's end: 31 January + a month is not 31 February
    import calendar

    day = min(today.day, calendar.monthrange(year, month + 1)[1])
    return date(year, month + 1, day)


@transaction.atomic
def reverse_for_order(order, *, reason: str = "مرتجع") -> PointsEntry | None:
    """
    Withdraws the points of a returned order.

    ⚠️  Without it: buy · earn · return · and keep the points — the simplest
        possible exploit in any loyalty system.

    ⚠️  And the withdrawal **does not take the balance below zero**.

        The customer may have redeemed their points before returning. Deducting
        into the negative makes them owe points, a concept that does not exist —
        and the difference is recorded as a note rather than inventing a debt.
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

    # ⚠️  Consume what remains of the earning batch itself first: leaving it makes
    #     withdrawn points remain redeemable.
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
    Consumes points from the batches — **soonest to expire first**.

    ⚠️  It returns what was actually consumed: it may fall short of the request
        when the available batches total less than the overall balance (points
        that expired and were not cleaned up).
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
#  Redemption
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
    ⚠️  The cap is a percentage of the order, not an absolute figure.

        Without a cap a whole order is paid in points, so the store parts with
        goods and no cash — and points do not pay suppliers' invoices.
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
    Redeems points for a personal coupon.

    ⚠️  **Redemption produces a coupon, not a direct discount.**

        A direct discount would have required `orders` and `cart` to know
        loyalty exists — and they sit **below** it in the layer order. And the
        coupon is a fully tested path: usage limits, validity, and filtering by
        customer.

    ⚠️  And the points are deducted **before** the coupon is created.

        The reverse leaves a valid coupon with no deduction should the
        consumption fail.
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
        # ⚠️  One use for one user: the coupon is the price of points consumed,
        #     and sharing it means a free discount for someone who did not pay for it.
        usage_limit=1,
        usage_limit_per_user=1,
        # ⚠️  Tied to its owner: `usage_limit=1` alone limits the count, not the
        #     person, so a photograph of the code is enough for someone else to
        #     spend it — on points that were theirs.
        owner=customer.user,
        starts_at=timezone.now(),
        # ⚠️  A limited validity: a coupon with no end is redeemed today and used
        #     two years later, leaving the liability open in the ledger forever.
        ends_at=timezone.now() + timedelta(days=30),
        is_active=True,
    )

    entry.reference = coupon.code
    PointsEntry.objects.filter(pk=entry.pk).update(reference=coupon.code)

    return {"entry": entry, "coupon": coupon, "value": result.value}


@transaction.atomic
def adjust_points(customer, points: int, *, reason: str, actor=None) -> PointsEntry:
    """
    A manual adjustment by the admin — **positive or negative**.

    ⚠️  **The reason is mandatory.**

        An adjustment with no reason becomes a number nobody can explain a month
        later, and a ledger that cannot be explained cannot be audited. And this
        is the most dangerous movement in the system: points created or erased
        with no order against them.

    ⚠️  And a withdrawal **does not take the balance below zero**: a customer
        does not owe points, and the difference is recorded in the note rather
        than inventing a debt.
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
    ⚠️  **Points are a liability, not a marketing balance.**

        Every outstanding point is a promise of a future discount. Displaying it
        as a count alone hides its value in pounds — which is what appears on
        the balance sheet when it is redeemed.
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
    Expires the due points — **with a recorded movement, not by deletion**.

    ⚠️  Deletion makes the customer see their balance drop with no reason in
        their statement. The movement says when it expired and how much it was.
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
#  Referrals
# ═══════════════════════════════════════════════════════════


def active_referral_program(user) -> ReferralProgram | None:
    for program in ReferralProgram.objects.filter(is_active=True).order_by("code"):
        if not program.account_types or user.account_type in program.account_types:
            return program
    return None


@transaction.atomic
def ensure_referral_code(user) -> ReferralCode:
    """
    ⚠️  The code is generated on request, not for every user.

        Generating it for everyone fills the table with codes that are never
        used, and consumes the space of short codes that can be dictated over
        the phone.
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
    Records a referral at registration — **with no reward yet**.

    ⚠️  **Four barriers against abuse, all of them necessary:**

          1. no self-referral            ← the most obvious exploit
          2. the referee is recorded once ← enforced by a `OneToOne` constraint
          3. a cap per referrer          ← it limits account farms
          4. the reward on the first completed order ← goods went out and money came in

        Dropping any of them makes the rest meaningless: someone able to open a
        hundred accounts is not stopped by a cap alone.
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
    Rewards the referral on the referee's **first completed order**.

    ⚠️  "First order" is measured by their count of completed orders, not by
        their registration date.

        Measuring by date makes someone who registered and did not buy until a
        year later ineligible — and they are a real customer brought in by a
        real referrer.
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

    # ⚠️  **Each side is checked against their own programme.**
    #
    #     Awarding both sides from the referrer's programme punched a hole in the
    #     targeting: a pharmacy inside the programme refers a student outside it,
    #     so the student earns points from a programme that does not cover them —
    #     and the admin who confined the system to pharmacies finds it spent on others.
    referrer_program = program_for(referral.referrer, referrer_customer)
    referee_program = program_for(customer.user, customer)

    if referrer_program is None and referee_program is None:
        # ⚠️  The reward is points, and with no active loyalty programme there is no vessel for them.
        #     They are left pending rather than refused: enabling the programme later rewards them.
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
    """Referrer statistics — for the ambassador dashboard."""
    rows = Referral.objects.filter(referrer=user)

    return {
        "total": rows.count(),
        "pending": rows.filter(status=ReferralStatus.PENDING).count(),
        "rewarded": rows.filter(status=ReferralStatus.REWARDED).count(),
        "rejected": rows.filter(status=ReferralStatus.REJECTED).count(),
    }
