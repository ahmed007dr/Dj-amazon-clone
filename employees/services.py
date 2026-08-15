"""
خدمات الموظفين.

⚠️  **الأداء يُحسب من الطلبات لا يُخزَّن.**

    رقم مبيعات مخزَّن على ملف الموظف ينحرف عند أول إلغاء أو مرتجع
    لا يمرّ بمسار التحديث. والمندوب يقرأ رقمه يوميًا ويبني عليه
    توقّع عمولته — فانحرافه شكوى مباشرة.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.errors import BusinessError, ErrorCode
from core.money import ZERO, quantize
from employees.models import (
    AssignmentStatus,
    CustomerAssignment,
    EmployeeProfile,
)

logger = logging.getLogger(__name__)


def _money(queryset, field: str) -> Decimal:
    total = queryset.aggregate(
        total=Coalesce(
            Sum(field),
            Value(ZERO),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
    )["total"]
    return quantize(total)


# ═══════════════════════════════════════════════════════════
#  الأدوار والصلاحيات
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def sync_role_permissions(role) -> None:
    """
    يزامن صلاحيات الدور إلى مجموعة Django التي تسندها فعلًا.

    ⚠️  **بدون هذا الاستدعاء تكون الصلاحيات زينة.**

        `user.has_perm()` يقرأ صلاحيات المستخدم ومجموعاته، ولا
        يعرف بوجود جدول `EmployeeRole.permissions` إطلاقًا. تركه
        بلا مزامنة يعني دورًا يبدو مضبوطًا في اللوحة بينما كل فحص
        صلاحية يفشل — ثم يُكتب فاحص خاص يتجاوز نظام Django.
    """
    from django.contrib.auth.models import Group

    if role.group is None:
        group, _created = Group.objects.get_or_create(name=f"employee:{role.code}")
        role.group = group
        role.save(update_fields=["group", "updated_at"])

    role.group.permissions.set(role.permissions.all())


@transaction.atomic
def apply_role_permissions(employee: EmployeeProfile) -> None:
    """
    يضع الموظف في مجموعة دوره — **بلا حفظ للملف**.

    ⚠️  **الفصل عن `set_role` ليس تنظيمًا بل ضرورة.**

        الإشارة على `post_save` تستدعي هذه؛ ولو حفظت الملف لأعادت
        إطلاق الإشارة إلى ما لا نهاية. وقع ذلك فعلًا: التكرار كان
        يبتلعه `except Exception` في الإشارة، فيبدو الحفظ ناجحًا
        بينما كل عملية تحرق ألف إطار مكدس وتسجّل استثناءً لا يقرأه
        أحد.

    ⚠️  و**ينزع مجموعات الأدوار الأخرى**.

        تركها يجعل الموظف يجمع صلاحيات كل دور مرّ به — فمندوب
        نُقل إلى خدمة العملاء يبقى قادرًا على إنشاء الطلبات، ولا
        يظهر ذلك في أي شاشة.
    """
    from django.contrib.auth.models import Group

    sync_role_permissions(employee.role)

    employee.user.groups.remove(
        *Group.objects.filter(name__startswith="employee:").exclude(pk=employee.role.group_id)
    )
    employee.user.groups.add(employee.role.group)


@transaction.atomic
def set_role(employee: EmployeeProfile, role) -> EmployeeProfile:
    """
    يغيّر دور الموظف — والإشارة تتولّى المجموعات بعد الحفظ.
    """
    employee.role = role
    employee.save(update_fields=["role", "updated_at"])
    return employee


def revoke_permissions(employee: EmployeeProfile) -> None:
    """
    ⚠️  إيقاف الموظف **يسحب مجموعته فورًا**.

        الاكتفاء بـ`is_active` يحمي نقاط هذا النطاق وحدها؛ أما
        `has_perm` في بقية النظام فيبقى يقول «نعم» لموظف انتهت
        خدمته ما دام في المجموعة.
    """
    from django.contrib.auth.models import Group

    employee.user.groups.remove(*Group.objects.filter(name__startswith="employee:"))


# ═══════════════════════════════════════════════════════════
#  الإسناد
# ═══════════════════════════════════════════════════════════


def assigned_customers(employee: EmployeeProfile):
    """
    عملاء هذا الموظف **القائمون**.

    ⚠️  الأساس الوحيد لكل ما يراه المندوب.

        كل استعلام في بوابته يمرّ من هنا؛ ونسيان التصفية في نقطة
        واحدة يكشف قائمة العملاء كاملة لمن أُسند له ثلاثة.
    """
    from customers.models import CustomerProfile

    return CustomerProfile.objects.filter(
        assignments__employee=employee,
        assignments__status=AssignmentStatus.ACTIVE,
    ).distinct()


def is_assigned(employee: EmployeeProfile, customer) -> bool:
    return CustomerAssignment.objects.filter(
        employee=employee, customer=customer, status=AssignmentStatus.ACTIVE
    ).exists()


@transaction.atomic
def assign_customer(customer, employee: EmployeeProfile, *, actor=None, note: str = ""):
    """
    ينقل عميلًا إلى موظف — **وينهي إسناده السابق**.

    ⚠️  الإنهاء قبل الإنشاء وفي نفس المعاملة.

        القيد الفريد يمنع إسنادين قائمين؛ والإنشاء قبل الإنهاء
        يرفضه بخطأ تكامل خام لا يفهمه الأدمن. والعكس — إنهاء بلا
        إنشاء بعده — يترك عميلًا بلا مسؤول لو فشل ما بعده.
    """
    if not employee.is_active:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الموظف ليس على رأس العمل")

    current = CustomerAssignment.objects.filter(
        customer=customer, status=AssignmentStatus.ACTIVE
    ).first()

    if current is not None:
        if current.employee_id == employee.pk:
            return current

        current.status = AssignmentStatus.ENDED
        current.ended_at = timezone.now()
        current.save(update_fields=["status", "ended_at", "updated_at"])

    return CustomerAssignment.objects.create(
        customer=customer,
        employee=employee,
        assigned_by=actor,
        note=note,
    )


@transaction.atomic
def end_assignment(customer, *, actor=None) -> int:
    """
    ⚠️  الإنهاء **لا يحذف السجل**.

        العمولة تُحسب على من كان مسؤولًا وقت البيع؛ وحذف الإسناد
        المنتهي يجعل كل طلب قديم بلا نسبة.
    """
    return CustomerAssignment.objects.filter(
        customer=customer, status=AssignmentStatus.ACTIVE
    ).update(status=AssignmentStatus.ENDED, ended_at=timezone.now())


# ═══════════════════════════════════════════════════════════
#  الأداء
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Performance:
    """
    أداء موظف في فترة.

    ⚠️  **بلا هدف ولا عمولة — المرحلة ١١.**

        وضع صفر مكانهما كان يجعل المندوب يقرأ «تحقيقك ٠٪» ويظنه
        أداءً سيئًا لا نظامًا لم يُضبَط بعد. الغياب يُعلَن صراحةً
        بدل أن يُملأ برقم كاذب.
    """

    employee: EmployeeProfile
    start: date
    end: date

    orders_count: int
    gross_sales: Decimal
    returns_total: Decimal
    net_sales: Decimal

    customers_count: int
    new_customers: int

    @property
    def average_order(self) -> Decimal:
        if self.orders_count == 0:
            return ZERO
        return quantize(self.net_sales / self.orders_count)


def performance(employee: EmployeeProfile, start: date, end: date) -> Performance:
    """
    ⚠️  المنسوب للموظف هو `owner_employee` لا `created_by`.

        المندوب مسؤول عن كل طلبات عملائه — بما فيها ما طلبوه
        بأنفسهم من الموقع. الحصر بما أنشأه بيده يجعل نجاحه في
        تحويل العميل إلى الطلب الذاتي **يخفض** رقمه.
    """
    from orders.models import Order, OrderStatus

    if start > end:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="بداية الفترة بعد نهايتها")

    period = Order.objects.filter(
        owner_employee=employee.user,
        created_at__date__gte=start,
        created_at__date__lte=end,
    )

    # ⚠️  الملغى خارج الحساب تمامًا: لم يُبَع شيء.
    #     أما المرتجع فقد بيع ثم عاد — يُطرح ولا يُتجاهَل.
    sold = period.exclude(status__in=[OrderStatus.CANCELLED, OrderStatus.REFUNDED])
    returned = period.filter(status=OrderStatus.REFUNDED)

    gross = _money(sold, "grand_total")
    returns_total = _money(returned, "grand_total")

    customers = assigned_customers(employee)

    return Performance(
        employee=employee,
        start=start,
        end=end,
        orders_count=sold.count(),
        gross_sales=gross,
        returns_total=returns_total,
        net_sales=quantize(gross - returns_total),
        customers_count=customers.count(),
        new_customers=CustomerAssignment.objects.filter(
            employee=employee,
            started_at__date__gte=start,
            started_at__date__lte=end,
        ).count(),
    )


def monthly_history(employee: EmployeeProfile, months: int = 6) -> list[dict]:
    """
    أداء الأشهر السابقة.

    ⚠️  **استعلام واحد بالتجميع لا استعلام لكل شهر.**

        حلقة على اثني عشر شهرًا تعني اثني عشر استعلامًا في كل فتح
        للوحة — وهي أول شاشة يفتحها كل مندوب كل صباح.
    """
    from django.db.models.functions import TruncMonth

    from orders.models import Order, OrderStatus

    # ⚠️  الطرح بالأشهر لا بـ«٣١ يومًا».
    #
    #     الطرح بعدد أيام ثابت ينزلق: ستة أشهر × ٣١ يومًا تتجاوز
    #     نصف السنة بأيام، فيدخل شهر سابع ناقص ويبدو كأن أداء
    #     المندوب انهار في أقدم صف.
    today = timezone.localdate()
    month_index = today.year * 12 + (today.month - 1) - (months - 1)
    first_month = date(month_index // 12, month_index % 12 + 1, 1)

    rows = (
        Order.objects.filter(
            owner_employee=employee.user,
            created_at__date__gte=first_month,
        )
        .exclude(status=OrderStatus.CANCELLED)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(
            orders=Count("id"),
            gross=Sum("grand_total"),
            returned=Sum("grand_total", filter=Q(status=OrderStatus.REFUNDED), default=Value(ZERO)),
        )
        .order_by("-month")
    )

    return [
        {
            "month": row["month"].date().isoformat()[:7],
            "orders": row["orders"],
            "gross": str(quantize(row["gross"] or ZERO)),
            "returns": str(quantize(row["returned"] or ZERO)),
            "net": str(quantize((row["gross"] or ZERO) - (row["returned"] or ZERO))),
        }
        for row in rows
    ]


# ═══════════════════════════════════════════════════════════
#  البيع نيابةً عن العميل
# ═══════════════════════════════════════════════════════════


def assert_may_act_for(employee: EmployeeProfile, customer) -> None:
    """
    ⚠️  **الحارس الذي يمنع بيع مندوب على عميل ليس له.**

        بلا هذا الفحص يُنشئ أي مندوب طلبًا لأي عميل بتمرير معرّف
        — فتُنسب المبيعة لغير صاحبها وتُحسب عمولتها للشخص الخطأ،
        ويكتشفه صاحب الحق في نهاية الشهر لا قبلها.
    """
    if not employee.is_active:
        raise BusinessError(
            ErrorCode.PERMISSION_DENIED, detail="الحساب موقوف عن العمل", status_code=403
        )

    if not is_assigned(employee, customer):
        # ⚠️  404 لا 403: الفارق بينهما يكشف وجود العميل ونشاطه
        #     لمن يجرّب معرّفات.
        raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)
