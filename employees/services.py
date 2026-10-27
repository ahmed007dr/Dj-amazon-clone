"""
Employee services.

⚠️  **Performance is computed from the orders, never stored.**

    A sales figure stored on the employee profile drifts at the first
    cancellation or return that does not pass through the update path. And the
    rep reads their number daily and builds a commission expectation on it — so
    drift is a complaint waiting to happen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts import services as account_services
from accounts.models import AccountStatus, AccountType, User
from administration.models import AdminProfile
from core.errors import BusinessError, ErrorCode
from core.identifiers import business_number
from core.models.audit import AuditAction, AuditLog
from core.money import ZERO, quantize
from employees.models import (
    AssignmentStatus,
    CustomerAssignment,
    EmployeeProfile,
)
from mailing import services as mail_services
from mailing import templates as mail_templates

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
#  Roles and permissions
# ═══════════════════════════════════════════════════════════


@transaction.atomic
def sync_role_permissions(role) -> None:
    """
    Synchronises the role's permissions into the Django group that actually confers them.

    ⚠️  **Without this call the permissions are decoration.**

        `user.has_perm()` reads the user's own permissions and their groups, and
        knows nothing at all about the `EmployeeRole.permissions` table. Leaving
        it unsynchronised means a role that looks configured in the panel while
        every permission check fails — and then a custom checker gets written
        that bypasses Django's system.
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
    Puts the employee into their role's group — **without saving the profile**.

    ⚠️  **The separation from `set_role` is a necessity, not tidiness.**

        The `post_save` signal calls this one; and were it to save the profile,
        it would re-fire the signal endlessly. That genuinely happened: the
        recursion was swallowed by the signal's `except Exception`, so the save
        looked successful while every operation burned a thousand stack frames
        and logged an exception nobody read.

    ⚠️  And it **removes the other roles' groups**.

        Leaving them makes the employee accumulate the permissions of every role
        they have passed through — so a rep moved to customer service remains
        able to create orders, and it shows on no screen.
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
    Changes the employee's role — and the signal handles the groups after the save.
    """
    employee.role = role
    employee.save(update_fields=["role", "updated_at"])
    return employee


def revoke_permissions(employee: EmployeeProfile) -> None:
    """
    ⚠️  Deactivating an employee **withdraws their group immediately**.

        Relying on `is_active` alone protects this domain's endpoints only; in
        the rest of the system `has_perm` keeps saying "yes" to a departed
        employee for as long as they remain in the group.
    """
    from django.contrib.auth.models import Group

    employee.user.groups.remove(*Group.objects.filter(name__startswith="employee:"))


# ═══════════════════════════════════════════════════════════
#  Creating staff — an account, a profile and an invite link
# ═══════════════════════════════════════════════════════════
#
#  Before this existed there was no way to add a staff member from the panel at
#  all: the only paths were the Django admin (whose add form even left the
#  account inactive) and the development seed.


class StaffAccess:
    """
    Which door the new person walks through.

    ⚠️  **Both doors give permissions the same way: through the role.**

        `STAFF_PORTAL` → `account_type=EMPLOYEE` — reaches `/staff` only.
        `ADMIN_PANEL`  → `account_type=ADMIN`    — reaches `/admin`, and there only
                         the screens their role's permissions open.

        `administration.AdminRole` confers nothing (it is never synchronised to a
        Django group), and the `system-admins` group that `grant_admin_permissions`
        fills holds *every* domain permission — joining it would make each new panel
        user an all-powerful admin. So a panel user also gets an `EmployeeProfile`
        with the chosen role: the existing signal then puts them in that role's
        `employee:<code>` group, `has_perm` / `/auth/me` / the sidebar all honour it,
        and the role is the single place permissions are reviewed. The `AdminProfile`
        is created non-owner, so nothing is inherited implicitly.
    """

    STAFF_PORTAL = "STAFF_PORTAL"
    ADMIN_PANEL = "ADMIN_PANEL"
    CHOICES = (STAFF_PORTAL, ADMIN_PANEL)


#: Words the invite mail needs per recipient language.
_ACCESS_LABELS = {
    StaffAccess.STAFF_PORTAL: {"ar": "بوابة الموظفين", "en": "Staff portal"},
    StaffAccess.ADMIN_PANEL: {"ar": "لوحة الإدارة", "en": "Admin panel"},
}


@dataclass(frozen=True)
class StaffCreated:
    employee: EmployeeProfile
    #: `False` when a temporary password was set instead of mailing a link
    invite_sent: bool


def _new_employee_number() -> str:
    """A generated, unguessable, non-sequential number (`EMP-2026-7K3M9P`)."""
    for _attempt in range(10):
        number = business_number("EMP", random_length=6)
        if not EmployeeProfile.all_objects.filter(employee_number=number).exists():
            return number
    # ⚠️  Practically unreachable (31^6 per year) — failing loudly beats looping forever.
    raise BusinessError(ErrorCode.INTERNAL_ERROR, status_code=500)


def _duplicate_errors(email: str, phone: str) -> dict[str, list[str]]:
    errors: dict[str, list[str]] = {}
    if User.objects.filter(email__iexact=email).exists():
        errors["email"] = ["هذا البريد مسجل بالفعل"]
    if phone and User.objects.filter(phone=phone).exists():
        errors["phone"] = ["هذا الرقم مسجل بالفعل"]
    return errors


def _access_of(user) -> str:
    if user.account_type == AccountType.ADMIN:
        return StaffAccess.ADMIN_PANEL
    return StaffAccess.STAFF_PORTAL


def _audit_staff(
    actor, employee: EmployeeProfile, action: str, object_repr: str, changes: dict, request
) -> None:
    AuditLog.objects.create(
        actor=actor,
        action=action,
        content_type=ContentType.objects.get_for_model(EmployeeProfile),
        object_id=str(employee.pk),
        object_repr=object_repr[:200],
        changes=changes,
        ip_address=request.META.get("REMOTE_ADDR") if request is not None else None,
    )


def send_invite(user, role, *, inviter=None, access: str, request=None) -> None:
    """
    Issue a fresh invite token (revoking any earlier one) and mail the link.

    ⚠️  The plaintext token exists only in this function's local variable and the
        email body — it is never logged, stored or returned by the API.
    """
    _record, raw_token = account_services.issue_invite_token(user, request=request)

    language = user.preferred_language if user.preferred_language in ("ar", "en") else "ar"
    days = account_services.STAFF_INVITE_TTL.days
    mail_services.send_to_user(
        mail_templates.STAFF_INVITE.key,
        user,
        {
            "inviter": (inviter.full_name if inviter is not None else "") or "—",
            "role": role.name_en if language == "en" else role.name_ar,
            "access": _ACCESS_LABELS[access][language],
            "link": account_services.frontend_url(f"/auth/reset-password?token={raw_token}"),
            "expiry": f"{days} days" if language == "en" else f"{days} أيام",
        },
    )


@transaction.atomic
def create_staff(
    *,
    actor,
    email: str,
    first_name: str,
    access: str,
    role,
    last_name: str = "",
    phone: str = "",
    manager: EmployeeProfile | None = None,
    phone_extension: str = "",
    language: str = "ar",
    temporary_password: str = "",
    request=None,
) -> StaffCreated:
    """
    Creates the login, the employee profile (and the admin profile for panel
    access) and mails the invite — all or nothing.

    ⚠️  **One transaction.** A user without a profile can log in and see nothing; a
        profile without a mail leaves a person nobody told. If anything below
        raises, none of it is written (and, because delivery is `on_commit`, no
        mail leaves either).

    ⚠️  The account is created **active with a verified email and an unusable
        password** — the invite link, which proves control of the mailbox, is the
        only way in. A temporary password (the owner's fallback for when mail is
        not set up) replaces the link; no mail is sent then, and the admin hands
        the password over out-of-band.
    """
    if access not in StaffAccess.CHOICES:
        raise ValidationError({"access": ["نوع الوصول غير معروف"]})

    email = email.strip().lower()
    phone = (phone or "").strip()

    errors = _duplicate_errors(email, phone)
    if errors:
        raise ValidationError(errors)

    try:
        # A savepoint, so a race on the unique columns surfaces as a field error
        # instead of a 500 that poisons the outer transaction.
        with transaction.atomic():
            is_panel = access == StaffAccess.ADMIN_PANEL
            user = User(
                email=email,
                first_name=first_name.strip(),
                last_name=(last_name or "").strip(),
                phone=phone or None,
                account_type=AccountType.ADMIN if is_panel else AccountType.EMPLOYEE,
                status=AccountStatus.ACTIVE,
                preferred_language=language,
                is_active=True,
                email_verified_at=timezone.now(),
            )
            if temporary_password:
                user.set_password(temporary_password)
            else:
                user.set_unusable_password()
            user.save()

            employee = EmployeeProfile.objects.create(
                user=user,
                employee_number=_new_employee_number(),
                role=role,
                manager=manager,
                phone_extension=(phone_extension or "").strip(),
                hired_on=timezone.localdate(),
            )

            if is_panel:
                AdminProfile.objects.create(user=user, job_title=role.name_ar[:100])
    except IntegrityError:
        errors = _duplicate_errors(email, phone)
        if errors:
            raise ValidationError(errors) from None
        raise

    invite_sent = not temporary_password
    if invite_sent:
        send_invite(user, role, inviter=actor, access=access, request=request)

    # ⚠️  No secrets in the entry: whether a temporary password was used is
    #     recorded, the password itself and the invite link never are.
    _audit_staff(
        actor,
        employee,
        AuditAction.CREATE,
        f"موظف {employee.employee_number} · {user.email}",
        {
            "access": access,
            "role": role.code,
            "manager": manager.employee_number if manager else None,
            "invite_sent": invite_sent,
            "temporary_password": bool(temporary_password),
        },
        request,
    )

    return StaffCreated(employee=employee, invite_sent=invite_sent)


@transaction.atomic
def resend_invite(employee: EmployeeProfile, *, actor, request=None) -> None:
    """
    Mail a fresh invite link to someone who has not signed in yet.

    ⚠️  Only while the invite is still pending (`last_login_at` empty). Mailing a
        password-setting link to an account that is already in use is an account
        takeover vector for anyone who can read that mailbox later, and there is
        nothing a working employee needs it for — they use "forgot password".
    """
    user = employee.user

    if not employee.is_active:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="الموظف ليس على رأس العمل")
    if user.last_login_at is not None:
        raise BusinessError(
            ErrorCode.CONFLICT,
            detail="هذا الموظف فعّل حسابه بالفعل",
            status_code=409,
        )

    send_invite(user, employee.role, inviter=actor, access=_access_of(user), request=request)

    _audit_staff(
        actor,
        employee,
        AuditAction.UPDATE,
        f"إعادة إرسال دعوة {employee.employee_number} · {user.email}",
        {"invite_resent": True},
        request,
    )


# ═══════════════════════════════════════════════════════════
#  Assignment
# ═══════════════════════════════════════════════════════════


def assigned_customers(employee: EmployeeProfile):
    """
    This employee's **current** customers.

    ⚠️  The sole basis for everything the rep sees.

        Every query in their portal goes through here; and forgetting the filter
        on one endpoint exposes the entire customer list to someone assigned three.
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
    Transfers a customer to an employee — **and ends their previous assignment**.

    ⚠️  Ending before creating, and in the same transaction.

        The unique constraint forbids two current assignments; creating before
        ending is rejected with a raw integrity error the admin cannot read. And
        the reverse — ending with no creation after it — leaves a customer with
        no owner should what follows fail.
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
    ⚠️  Ending **does not delete the record**.

        Commission is calculated on whoever was responsible at the time of sale;
        deleting the ended assignment leaves every old order unattributed.
    """
    return CustomerAssignment.objects.filter(
        customer=customer, status=AssignmentStatus.ACTIVE
    ).update(status=AssignmentStatus.ENDED, ended_at=timezone.now())


# ═══════════════════════════════════════════════════════════
#  Performance
# ═══════════════════════════════════════════════════════════


@dataclass(frozen=True)
class Performance:
    """
    An employee's performance over a period.

    ⚠️  **No target and no commission — phase 11.**

        Putting zero in their place made the rep read "your achievement is 0%"
        and take it for poor performance rather than a system not yet
        configured. The absence is declared explicitly rather than filled with a
        false number.
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
    ⚠️  What is attributed to the employee is `owner_employee`, not `created_by`.

        The rep is responsible for all their customers' orders — including those
        the customers placed themselves on the website. Restricting it to what
        they typed by hand makes their success in converting a customer to
        self-service **lower** their number.
    """
    from orders.models import Order, OrderStatus

    if start > end:
        raise BusinessError(ErrorCode.VALIDATION_ERROR, detail="بداية الفترة بعد نهايتها")

    period = Order.objects.filter(
        owner_employee=employee.user,
        created_at__date__gte=start,
        created_at__date__lte=end,
    )

    # ⚠️  Cancelled orders are excluded from the calculation entirely: nothing was sold.
    #     A return, however, was sold and then came back — it is subtracted, not ignored.
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
    The previous months' performance.

    ⚠️  **One aggregated query, not one query per month.**

        A loop over twelve months means twelve queries on every dashboard open —
        and it is the first screen every rep opens each morning.
    """
    from django.db.models.functions import TruncMonth

    from orders.models import Order, OrderStatus

    # ⚠️  Subtracting by months, not by "31 days".
    #
    #     Subtracting a fixed day count drifts: six months × 31 days overshoots
    #     half a year by several days, so an incomplete seventh month creeps in
    #     and it looks as though the rep's performance collapsed in the oldest row.
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
#  Selling on the customer's behalf
# ═══════════════════════════════════════════════════════════


def assert_may_act_for(employee: EmployeeProfile, customer) -> None:
    """
    ⚠️  **The guard that stops a rep selling to a customer who is not theirs.**

        Without this check any rep creates an order for any customer by passing
        an id — so the sale is attributed to the wrong person and its commission
        goes to the wrong person, and whoever it belonged to discovers it at the
        end of the month rather than before.
    """
    if not employee.is_active:
        raise BusinessError(
            ErrorCode.PERMISSION_DENIED, detail="الحساب موقوف عن العمل", status_code=403
        )

    if not is_assigned(employee, customer):
        # ⚠️  404, not 403: the difference reveals the customer's existence and activity
        #     to anyone trying ids.
        raise BusinessError(ErrorCode.NOT_FOUND, status_code=404)
