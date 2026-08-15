"""
حساب العمولات.

⚠️  **حتمي وقابل للتفسير.**

    نفس المدخلات تعطي نفس المخرجات دائمًا، وكل مخرج يحمل مدخلاته
    معه. هذا ليس ترفًا: المبلغ يُصرَف، والخلاف عليه يُحسم بالسجل
    لا بإعادة تشغيل الحساب.
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
    يختار الشريحة المطابقة لنسبة التحقيق.

    ⚠️  **لا شريحة مطابقة ⟵ عمولة صفر لا استثناء.**

        خطة بلا شريحة تغطي ٠–٥٠٪ تعني أن المندوب المتعثّر لا
        يطابق شيئًا. رفع استثناء هنا كان يُفشل حساب الفريق كله
        بسبب موظف واحد؛ والصفر هو الجواب الصحيح تجاريًا ويُسجَّل
        بوصف مقروء.
    """
    for tier in scheme.tiers.order_by("from_percent"):
        if tier.matches(achievement):
            return TierMatch(tier=tier, rate=tier.rate, label=str(tier))

    return TierMatch(tier=None, rate=ZERO, label="لا شريحة مطابقة")


def scheme_for(employee) -> CommissionScheme | None:
    """
    خطة الموظف: خطة دوره، وإلا الخطة العامة المفعّلة.

    ⚠️  الغياب **ليس خطأً** — موظف مخزن بلا عمولة حالة طبيعية.
    """
    by_role = CommissionScheme.objects.filter(role=employee.role, is_active=True).first()
    if by_role is not None:
        return by_role

    return CommissionScheme.objects.filter(role__isnull=True, is_active=True).first()


@transaction.atomic
def calculate(target: MonthlyTarget, *, scheme: CommissionScheme | None = None):
    """
    يحسب عمولة شهر ويحفظ **كل مدخلاته**.

    ⚠️  الترتيب مقصود:

          ١. الحد الأدنى للتحقيق  ← دونه لا عمولة مهما بيع
          ٢. الشريحة حسب التحقيق
          ٣. الأساس (صافي مبيعات أو ربح)
          ٤. المبلغ = الأساس × النسبة

        فحص الحد الأدنى **قبل** الشريحة: خطة قد تمنح ١٪ لشريحة
        ٠–٥٠٪ بينما الحد الأدنى ٦٠٪ — والحد الأدنى هو الأشدّ
        فيسبق.

    ⚠️  والأساس السالب **يُقصَّ إلى صفر**.

        شهر مرتجعاته أكبر من مبيعاته يعطي صافيًا سالبًا؛ وضرب
        السالب في نسبة يُنتج عمولة سالبة تُخصم من راتب. الخصم من
        الراتب قرار إداري لا نتيجة حسابية.
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

    # ── ١. الحد الأدنى ─────────────────────────────────────
    below_minimum = not result.meets_minimum

    # ── ٢. الشريحة ─────────────────────────────────────────
    match = resolve_tier(scheme, result.achievement_percent)

    # ── ٣. الأساس ──────────────────────────────────────────
    base_amount = (
        result.gross_profit if scheme.base == CommissionBase.GROSS_PROFIT else result.net_sales
    )
    # الأساس السالب يُقصّ — لا عمولة سالبة
    base_amount = max(base_amount, ZERO)

    # ── ٤. المبلغ ──────────────────────────────────────────
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
    حساب عمولات شهر لكل من له هدف نشط أو مقفل.

    ⚠️  فشل موظف **لا يوقف البقية**.

        موظف بلا خطة عمولة كان سيُفشل حساب الفريق كله؛ والنتيجة
        تُبلَّغ بعدد النجاح والتخطّي معًا لا برقم واحد يُقرأ نجاحًا.
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
    ⚠️  الاعتماد **فعل منفصل** — ولا يُعاد.

        العمولة تبدأ محسوبة؛ والاعتماد التلقائي يجعل خطأ هدف أو
        مرتجعًا متأخرًا يتحوّل إلى مبلغ مصروف قبل مراجعة.
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
    ⚠️  الصرف لا يقع إلا على **معتمدة**.

        القفز من «محسوبة» إلى «مصروفة» يتجاوز المراجعة كلها —
        وهي الخطوة الوحيدة التي تمسك خطأ الحساب قبل خروج المال.
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
    تفسير كامل لنتيجة عمولة — **من السجل لا بإعادة حساب**.

    ⚠️  هذا هو ما يجعل «كيف حُسبت؟» سؤالًا له جواب واحد ثابت.
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
