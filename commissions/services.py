"""
Commission calculation.

⚠️  **Deterministic and explainable.**

    The same inputs always give the same outputs, and every output carries its
    inputs with it. This is not a luxury: the amount is paid out, and a dispute
    over it is settled from the record, not by re-running the calculation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from commissions.models import (
    CommissionBase,
    CommissionRecord,
    CommissionScheme,
    CommissionStatus,
    CommissionTier,
)
from core.errors import BusinessError, ErrorCode
from core.money import ZERO, quantize
from targets.models import MonthlyTarget, TargetStatus

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TierMatch:
    tier: CommissionTier | None
    rate: Decimal
    label: str


def resolve_tier(scheme: CommissionScheme, achievement: Decimal) -> TierMatch:
    """
    Selects the tier matching the achievement percentage.

    ⚠️  **No matching tier ⟵ zero commission, not an exception.**

        A scheme with no tier covering 0–50% means a struggling rep matches
        nothing. Raising an exception here failed the whole team's calculation
        because of one employee; zero is the commercially correct answer, and it
        is recorded with a readable description.
    """
    for tier in scheme.tiers.order_by("from_percent"):
        if tier.matches(achievement):
            return TierMatch(tier=tier, rate=tier.rate, label=str(tier))

    return TierMatch(tier=None, rate=ZERO, label="لا شريحة مطابقة")


def scheme_for(employee) -> CommissionScheme | None:
    """
    The employee's scheme: their role's, otherwise the active general scheme.

    ⚠️  Absence is **not an error** — a warehouse employee with no commission is normal.
    """
    by_role = CommissionScheme.objects.filter(role=employee.role, is_active=True).first()
    if by_role is not None:
        return by_role

    return CommissionScheme.objects.filter(role__isnull=True, is_active=True).first()


@transaction.atomic
def calculate(target: MonthlyTarget, *, scheme: CommissionScheme | None = None):
    """
    Calculates a month's commission and stores **all of its inputs**.

    ⚠️  The order is deliberate:

          1. the minimum achievement  ← below it there is no commission however much was sold
          2. the tier by achievement
          3. the base (net sales or profit)
          4. the amount = base × rate

        The minimum is checked **before** the tier: a scheme may grant 1% for
        the 0–50% tier while the minimum is 60% — and the minimum is the
        stricter, so it comes first.

    ⚠️  And a negative base is **clamped to zero**.

        A month whose returns exceed its sales gives a negative net; and
        multiplying a negative by a rate produces a negative commission deducted
        from a salary. Deducting from salary is a management decision, not an
        arithmetic result.
    """
    from targets import services as target_services

    employee = target.employee
    scheme = scheme or scheme_for(employee)

    if scheme is None:
        raise BusinessError(
            ErrorCode.VALIDATION_ERROR,
            detail=f"لا خطة عمولة لدور {employee.role.name_ar}",
        )

    existing = CommissionRecord.objects.filter(
        employee=employee, year=target.year, month=target.month
    ).first()

    if existing is not None and existing.is_locked:
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail="العمولة معتمدة أو مصروفة — التصحيح بسجل جديد",
            status_code=409,
        )

    result = target_services.measure(target)

    # ── 1. The minimum ─────────────────────────────────────
    below_minimum = not result.meets_minimum

    # ── 2. The tier ────────────────────────────────────────
    match = resolve_tier(scheme, result.achievement_percent)

    # ── 3. The base ────────────────────────────────────────
    base_amount = (
        result.gross_profit if scheme.base == CommissionBase.GROSS_PROFIT else result.net_sales
    )
    # A negative base is clamped — no negative commission
    base_amount = max(base_amount, ZERO)

    # ── 4. The amount ──────────────────────────────────────
    rate = ZERO if below_minimum else match.rate
    amount = quantize(base_amount * rate / Decimal("100"))

    label = (
        f"دون الحد الأدنى ({target.minimum_achievement_percent}٪)" if below_minimum else match.label
    )

    cost = quantize(result.net_sales - result.gross_profit)

    record, _created = CommissionRecord.objects.update_or_create(
        employee=employee,
        year=target.year,
        month=target.month,
        defaults={
            "target": target,
            "scheme": scheme,
            "orders_count": result.orders_count,
            "gross_sales": result.gross_sales,
            "returns_total": result.returns_total,
            "net_sales": result.net_sales,
            "cost_total": cost,
            "gross_profit": result.gross_profit,
            "target_value": target.target_value,
            "achieved_value": result.achieved_value,
            "achievement_percent": result.achievement_percent,
            "base": scheme.base,
            "base_amount": base_amount,
            "tier_label": label,
            "rate": rate,
            "amount": amount,
            "status": CommissionStatus.CALCULATED,
            "calculated_at": timezone.now(),
        },
    )
    return record


@transaction.atomic
def calculate_month(year: int, month: int) -> dict:
    """
    Calculate a month's commissions for everyone with an active or closed target.

    ⚠️  One employee failing **does not stop the rest**.

        An employee with no commission scheme used to fail the whole team's
        calculation; the result reports the success and skip counts together
        rather than a single number that reads as success.
    """
    targets = MonthlyTarget.objects.filter(
        year=year, month=month, status__in=[TargetStatus.ACTIVE, TargetStatus.CLOSED]
    ).select_related("employee", "employee__role")

    done, skipped = 0, []

    for target in targets:
        try:
            calculate(target)
            done += 1
        except BusinessError as failure:
            skipped.append(
                {
                    "employee": target.employee.employee_number,
                    "reason": failure.error_detail or str(failure),
                }
            )
        except Exception:
            logger.exception("فشل حساب عمولة %s", target.employee.employee_number)
            skipped.append({"employee": target.employee.employee_number, "reason": "خطأ غير متوقع"})

    return {"calculated": done, "skipped": skipped}


@transaction.atomic
def approve(record: CommissionRecord, *, by) -> CommissionRecord:
    """
    ⚠️  Approval is **a separate act** — and it is not repeated.

        A commission starts calculated; automatic approval turns a target error
        or a late return into money paid out before review.
    """
    if record.is_locked:
        raise BusinessError(ErrorCode.CONFLICT, detail="العمولة معتمدة سلفًا", status_code=409)

    record.status = CommissionStatus.APPROVED
    record.approved_by = by
    record.approved_at = timezone.now()
    record.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return record


@transaction.atomic
def mark_paid(record: CommissionRecord, *, by) -> CommissionRecord:
    """
    ⚠️  Payment happens only on an **approved** record.

        Jumping from "calculated" to "paid" bypasses the review entirely — the
        one step that catches a calculation error before the money leaves.
    """
    if record.status != CommissionStatus.APPROVED:
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail="لا تُصرَف إلا عمولة معتمدة",
            status_code=409,
        )

    record.status = CommissionStatus.PAID
    record.save(update_fields=["status", "updated_at"])
    return record


@transaction.atomic
def reject(record: CommissionRecord, *, by, reason: str) -> CommissionRecord:
    if not reason.strip():
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="سبب الرفض إلزامي")

    if record.status == CommissionStatus.PAID:
        raise BusinessError(
            ErrorCode.CONFLICT, detail="العمولة مصروفة — التصحيح بقيد معاكس", status_code=409
        )

    record.status = CommissionStatus.REJECTED
    record.note = reason
    record.approved_by = by
    record.approved_at = timezone.now()
    record.save(update_fields=["status", "note", "approved_by", "approved_at", "updated_at"])
    return record


def explain(record: CommissionRecord) -> dict:
    """
    A full explanation of a commission result — **from the record, not by recomputation**.

    ⚠️  This is what makes "how was it calculated?" a question with one fixed answer.
    """
    return {
        "employee": record.employee.employee_number,
        "period": f"{record.year}-{record.month:02d}",
        "orders_count": record.orders_count,
        "gross_sales": str(record.gross_sales),
        "returns": str(record.returns_total),
        "net_sales": str(record.net_sales),
        "cost": str(record.cost_total),
        "gross_profit": str(record.gross_profit),
        "target": str(record.target_value),
        "achieved": str(record.achieved_value),
        "achievement_percent": str(record.achievement_percent),
        "scheme": record.scheme.code,
        "base": record.base,
        "base_amount": str(record.base_amount),
        "tier": record.tier_label,
        "rate": str(record.rate),
        "amount": str(record.amount),
        "status": record.status,
        "calculated_at": record.calculated_at.isoformat(),
    }
