"""
Staff portal tests.

⚠️  The exit gate for phase 10:

        the rep sees **their own customers alone** · does not sell to a customer
        who is not theirs · the order is attributed to its owner · the roles do
        not carry admin permissions.

    And the greatest dangers it guards are not on the screen but beneath it: a
    rep reading a colleague's customer's phone number and purchase volume by
    changing an id · a departed employee still selling on a valid token · the
    record of "who was responsible at the time of sale" being lost so the
    commission goes to the wrong person.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from core.errors import BusinessError
from core.testing import grant_all_domains
from customers.models import CustomerProfile
from employees import services
from employees.models import (
    AssignmentStatus,
    CustomerAssignment,
    EmployeeProfile,
    EmployeeRole,
    EmployeeRoleKind,
)
from orders.models import Order, OrderChannel, OrderStatus, PaymentStatus

PASSWORD = "Str0ng-Test-Pass!23"


# ═══════════════════════════════════════════════════════════
#  Setup
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def role(db):
    return EmployeeRole.objects.create(
        code="rep", kind=EmployeeRoleKind.SALES_REP, name_ar="مندوب", name_en="Rep"
    )


def make_employee(email, role, *, number=None, active=True):
    user = User.objects.create_user(
        email=email, password=PASSWORD, account_type=AccountType.EMPLOYEE
    )
    user.is_active = True
    user.first_name = "مندوب"
    user.save()

    return EmployeeProfile.objects.create(
        user=user,
        employee_number=number or email.split("@")[0].upper(),
        role=role,
        is_active=active,
    )


def make_customer(email, name="عميل"):
    user = User.objects.create_user(email=email, password=PASSWORD)
    user.is_active = True
    user.first_name = name
    user.save()
    return CustomerProfile.objects.create(user=user, display_name_ar=name)


@pytest.fixture
def rep(role):
    return make_employee("rep-a@test.local", role, number="EMP-001")


@pytest.fixture
def other_rep(role):
    return make_employee("rep-b@test.local", role, number="EMP-002")


@pytest.fixture
def mine(db, rep):
    customer = make_customer("mine@test.local", "عميلي")
    services.assign_customer(customer, rep)
    return customer


@pytest.fixture
def theirs(db, other_rep):
    customer = make_customer("theirs@test.local", "عميل الزميل")
    services.assign_customer(customer, other_rep)
    return customer


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def make_order(customer, employee=None, *, total="1000.00", status=OrderStatus.DELIVERED):
    amount = Decimal(total)
    return Order.objects.create(
        customer=customer,
        channel=OrderChannel.EMPLOYEE,
        status=status,
        payment_status=PaymentStatus.PAID,
        subtotal=amount,
        grand_total=amount,
        owner_employee=employee.user if employee else None,
    )


# ═══════════════════════════════════════════════════════════
#  Assignment — the exit gate
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAssignment:
    def test_a_customer_has_one_active_owner(self, rep, other_rep):
        """
        ⚠️  Two reps sharing a customer means a double commission on the same
            sale, and conflicting follow-up: either both call them or neither does.
        """
        customer = make_customer("shared@test.local")
        services.assign_customer(customer, rep)
        services.assign_customer(customer, other_rep)

        active = CustomerAssignment.objects.filter(
            customer=customer, status=AssignmentStatus.ACTIVE
        )
        assert active.count() == 1
        assert active.first().employee == other_rep

    def test_the_database_refuses_two_active_assignments(self, rep, other_rep):
        """A check in the service loses the race; the unique constraint settles it."""
        from django.db import IntegrityError, transaction

        customer = make_customer("race@test.local")
        services.assign_customer(customer, rep)

        with pytest.raises(IntegrityError), transaction.atomic():
            CustomerAssignment.objects.create(customer=customer, employee=other_rep)

    def test_transfer_keeps_the_old_record(self, rep, other_rep):
        """
        ⚠️  **Commission is calculated on whoever was responsible at the time of sale.**

            Deleting the ended assignment leaves every old order unattributed —
            with no way to reconstruct it.
        """
        customer = make_customer("moved@test.local")
        services.assign_customer(customer, rep)
        services.assign_customer(customer, other_rep)

        assert CustomerAssignment.objects.filter(customer=customer).count() == 2
        old = CustomerAssignment.objects.get(customer=customer, employee=rep)
        assert old.status == AssignmentStatus.ENDED
        assert old.ended_at is not None

    def test_reassigning_to_the_same_employee_is_a_no_op(self, rep, mine):
        services.assign_customer(mine, rep)

        assert CustomerAssignment.objects.filter(customer=mine).count() == 1

    def test_an_inactive_employee_cannot_receive_customers(self, role):
        """A departed employee is assigned no new customers."""
        gone = make_employee("gone@test.local", role, active=False)
        customer = make_customer("orphan@test.local")

        with pytest.raises(BusinessError):
            services.assign_customer(customer, gone)

    def test_ending_an_assignment_does_not_delete_it(self, rep, mine):
        services.end_assignment(mine)

        assert CustomerAssignment.objects.filter(customer=mine).count() == 1
        assert not services.is_assigned(rep, mine)


# ═══════════════════════════════════════════════════════════
#  Isolation between reps
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestIsolation:
    def test_a_rep_sees_only_assigned_customers(self, rep, mine, theirs):
        response = client_for(rep.user).get(reverse("v1:employees:customers"))

        assert response.status_code == 200
        numbers = [row["customer_number"] for row in response.data["results"]]
        assert mine.customer_number in numbers
        assert theirs.customer_number not in numbers

    def test_search_cannot_escape_the_assignment_filter(self, rep, mine, theirs):
        """
        ⚠️  A search that bypasses the filter lets a rep find any customer by
            name and read their phone number and purchase volume — the data reps
            compete over internally.
        """
        response = client_for(rep.user).get(
            reverse("v1:employees:customers"), {"search": "عميل الزميل"}
        )

        assert response.status_code == 200
        assert response.data["results"] == []

    def test_a_rep_cannot_read_another_reps_customer_orders(self, rep, theirs):
        """⚠️  404, not 403: the difference reveals the customer's existence to anyone trying ids."""
        response = client_for(rep.user).get(
            reverse("v1:employees:customer-orders", args=[theirs.pk])
        )

        assert response.status_code == 404

    def test_a_rep_cannot_sell_to_another_reps_customer(self, rep, theirs):
        """
        ⚠️  **The guard that stops a sale being attributed to the wrong person.**

            Without the check any rep creates an order for any customer by
            passing an id, so the commission goes to the wrong person and
            whoever it belonged to discovers it at the end of the month rather
            than before.
        """
        with pytest.raises(BusinessError):
            services.assert_may_act_for(rep, theirs)

    def test_a_suspended_employee_loses_access_immediately(self, rep, mine):
        """
        ⚠️  A valid token in a departed employee's hand is the most obvious hole possible.

            Disabling the account alone leaves a gap until the token expires;
            checking `is_active` on the profile closes it on the first request.
        """
        rep.is_active = False
        rep.save()

        response = client_for(rep.user).get(reverse("v1:employees:customers"))
        assert response.status_code == 403

        with pytest.raises(BusinessError):
            services.assert_may_act_for(rep, mine)

    def test_a_customer_cannot_open_the_employee_portal(self, db):
        customer = User.objects.create_user(email="shopper@test.local", password=PASSWORD)
        customer.is_active = True
        customer.save()

        assert client_for(customer).get(reverse("v1:employees:dashboard")).status_code == 403

    def test_an_employee_without_a_profile_is_refused(self, db):
        stray = User.objects.create_user(
            email="stray@test.local", password=PASSWORD, account_type=AccountType.EMPLOYEE
        )
        stray.is_active = True
        stray.save()

        assert client_for(stray).get(reverse("v1:employees:dashboard")).status_code == 403


# ═══════════════════════════════════════════════════════════
#  Performance
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPerformance:
    def test_sales_are_attributed_by_owner_not_creator(self, rep, mine):
        """
        ⚠️  The rep is responsible for **all** their customers' orders —
            including those the customers placed themselves on the website.

            Restricting it to what they typed by hand makes their success in
            converting a customer to self-service **lower** their number.
        """
        online = make_order(mine, rep, total="2000.00")
        online.channel = OrderChannel.ONLINE
        online.created_by = None
        online.save()

        result = services.performance(
            rep, timezone.localdate().replace(day=1), timezone.localdate()
        )

        assert result.orders_count == 1
        assert result.gross_sales == Decimal("2000.00")

    def test_cancelled_orders_are_excluded_entirely(self, rep, mine):
        """Nothing was sold in a cancelled order — it is neither added nor subtracted."""
        make_order(mine, rep, total="500.00")
        make_order(mine, rep, total="900.00", status=OrderStatus.CANCELLED)

        result = services.performance(
            rep, timezone.localdate().replace(day=1), timezone.localdate()
        )

        assert result.orders_count == 1
        assert result.gross_sales == Decimal("500.00")

    def test_refunds_are_subtracted_not_ignored(self, rep, mine):
        """A return was sold and then came back — it is subtracted from the net."""
        make_order(mine, rep, total="1000.00")
        make_order(mine, rep, total="400.00", status=OrderStatus.REFUNDED)

        result = services.performance(
            rep, timezone.localdate().replace(day=1), timezone.localdate()
        )

        assert result.gross_sales == Decimal("1000.00")
        assert result.returns_total == Decimal("400.00")
        assert result.net_sales == Decimal("600.00")

    def test_another_reps_sales_never_leak_in(self, rep, other_rep, mine, theirs):
        make_order(mine, rep, total="300.00")
        make_order(theirs, other_rep, total="9000.00")

        result = services.performance(
            rep, timezone.localdate().replace(day=1), timezone.localdate()
        )

        assert result.net_sales == Decimal("300.00")

    def test_average_order_is_zero_not_a_crash(self, rep):
        result = services.performance(
            rep, timezone.localdate().replace(day=1), timezone.localdate()
        )

        assert result.orders_count == 0
        assert result.average_order == Decimal("0.00")

    def test_inverted_period_is_refused(self, rep):
        today = timezone.localdate()
        with pytest.raises(BusinessError):
            services.performance(rep, today, today - timedelta(days=5))

    def test_monthly_history_covers_the_requested_months(self, rep, mine):
        """
        ⚠️  Subtracting by months, not by "31 days".

            Subtracting a fixed day count drifts, so an incomplete seventh month
            creeps in and it looks as though the rep's performance collapsed in
            the oldest row.
        """
        make_order(mine, rep, total="700.00")

        history = services.monthly_history(rep, months=6)

        assert len(history) >= 1
        assert history[0]["net"] == "700.00"


# ═══════════════════════════════════════════════════════════
#  The dashboard and selling on behalf
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestDashboardAndSelling:
    def test_the_dashboard_carries_performance_only(self, rep, mine):
        """
        ⚠️  **No target or commission fields — and the absence is deliberate.**

            `targets` and `commissions` sit above this domain in the layers.
            A `target` field here would always return `null` and read as "no
            target" rather than "ask `/targets/me/`" — a lie worse than absence.
        """
        response = client_for(rep.user).get(reverse("v1:employees:dashboard"))

        assert response.status_code == 200
        assert "net_sales" in response.data
        assert "target" not in response.data
        assert "estimated_commission" not in response.data

    def test_creating_an_order_attributes_it_to_the_rep(self, rep, mine, db):
        """
        ⚠️  `owner_employee` is the basis of the commission later — leaving it
            empty drops the order from the rep's performance and from their
            commission calculation.
        """
        from catalog.models import Category, Product
        from inventory import services as inventory_services
        from inventory.models import LocationKind, StockLocation

        location = StockLocation.objects.create(
            code="emp-loc",
            name_ar="مخزن",
            name_en="Store",
            kind=LocationKind.WAREHOUSE,
            is_default=True,
            is_sellable=True,
        )
        category = Category.objects.create(slug="emp", name_ar="فئة", name_en="Cat")
        product = Product.objects.create(
            sku="EMP-1",
            name_ar="صنف",
            name_en="Item",
            category=category,
            base_price=Decimal("100.00"),
        )
        inventory_services.receive(product, 50, Decimal("60.00"), location=location)

        response = client_for(rep.user).post(
            reverse("v1:employees:create-order"),
            {
                "customer": str(mine.pk),
                "lines": [{"product": str(product.pk), "quantity": 2}],
                "payment_method": "COD",
                "address": {
                    "recipient_name": "عميلي",
                    "phone": "01111111111",
                    "governorate": "القاهرة",
                    "city": "مدينة نصر",
                    "street": "شارع",
                },
            },
            format="json",
        )

        assert response.status_code == 201, response.data
        order = Order.objects.get(pk=response.data["id"])
        assert order.owner_employee == rep.user
        assert order.created_by == rep.user
        assert order.channel == OrderChannel.EMPLOYEE

    def test_selling_to_an_unassigned_customer_is_refused(self, rep, theirs):
        response = client_for(rep.user).post(
            reverse("v1:employees:create-order"),
            {
                "customer": str(theirs.pk),
                "lines": [{"product": str(theirs.pk), "quantity": 1}],
                "payment_method": "COD",
                "address": {
                    "recipient_name": "x",
                    "phone": "01111111111",
                    "governorate": "القاهرة",
                    "city": "مدينة",
                    "street": "شارع",
                },
            },
            format="json",
        )

        assert response.status_code == 404


# ═══════════════════════════════════════════════════════════
#  Roles and permissions
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRoles:
    def test_the_seed_gives_no_role_admin_powers(self):
        """
        ⚠️  **An employee is never granted admin permissions, not even "temporarily".**

            The check covers what is usually forgotten: editing prices,
            suspending accounts, and seeing profits for anyone outside finance.
        """
        from django.core.management import call_command

        call_command("seed_employee_roles", verbosity=0)

        forbidden = {"change_user", "delete_user", "change_pricelist", "change_taxclass"}

        for role in EmployeeRole.objects.all():
            codenames = set(role.permissions.values_list("codename", flat=True))
            assert not (codenames & forbidden), f"الدور {role.code} يحمل صلاحيات أدمن"

    def test_only_finance_role_sees_money(self):
        from django.core.management import call_command

        call_command("seed_employee_roles", verbosity=0)

        for role in EmployeeRole.objects.all():
            has_finance = role.permissions.filter(content_type__app_label="finance").exists()
            assert has_finance == (role.code == "finance-staff"), role.code

    def test_saving_a_profile_does_not_recurse(self, role, db, monkeypatch):
        """
        ⚠️  **A defect that genuinely occurred and was hidden by swallowed exceptions.**

            The `post_save` signal called `set_role`, which saves the profile,
            re-firing the signal endlessly. And the signal's `except Exception`
            swallowed the `RecursionError` — so the save looked successful while
            every operation burned a thousand stack frames and logged an
            exception nobody read.

            The separation: the signal calls `apply_role_permissions`, which
            saves nothing.
        """
        from employees import services as svc

        calls: list[int] = []
        real = svc.apply_role_permissions

        def counting(employee):
            calls.append(1)
            assert len(calls) < 20, f"تكرار غير منتهٍ: {len(calls)}"
            return real(employee)

        monkeypatch.setattr(svc, "apply_role_permissions", counting)

        employee = make_employee("norecurse@test.local", role)
        employee.phone_extension = "101"
        employee.save()

        assert len(calls) == 2, f"استدعاء واحد لكل حفظ — لا {len(calls)}"

    def test_role_permissions_actually_resolve_through_has_perm(self, role, db):
        """
        ⚠️  **The test that separates a real permission from decoration.**

            `has_perm` reads the user's own permissions and their groups only,
            and knows nothing about `EmployeeRole.permissions`. Without
            synchronising to the Django group, the role is configured in the
            panel and every permission check says "no".
        """
        employee = make_employee("perm@test.local", role)
        role.permissions.add(Permission.objects.get(codename="view_order"))

        services.set_role(employee, role)

        fresh = User.objects.get(pk=employee.user.pk)
        assert fresh.has_perm("orders.view_order")

    def test_changing_role_drops_the_previous_permissions(self, role, db):
        """
        ⚠️  Accumulating groups makes the employee collect the permissions of
            every role they have passed through.

            A rep moved to customer service remains able to create orders —
            and it shows on no screen.
        """
        selling = EmployeeRole.objects.create(
            code="seller", kind=EmployeeRoleKind.SALES_REP, name_ar="بائع", name_en="Seller"
        )
        selling.permissions.add(Permission.objects.get(codename="add_order"))

        watching = EmployeeRole.objects.create(
            code="watcher",
            kind=EmployeeRoleKind.CUSTOMER_SERVICE,
            name_ar="خدمة",
            name_en="Service",
        )
        watching.permissions.add(Permission.objects.get(codename="view_order"))

        employee = make_employee("moved-role@test.local", role)
        services.set_role(employee, selling)
        assert User.objects.get(pk=employee.user.pk).has_perm("orders.add_order")

        services.set_role(employee, watching)

        fresh = User.objects.get(pk=employee.user.pk)
        assert fresh.has_perm("orders.view_order")
        assert not fresh.has_perm("orders.add_order")

    def test_a_suspended_employee_loses_permissions_system_wide(self, role, db):
        """
        ⚠️  `is_active` alone protects this domain's endpoints only.

            The rest of the system asks `has_perm` — and it will say "yes" to a
            departed employee for as long as they remain in the group.
        """
        employee = make_employee("suspended-perm@test.local", role)
        role.permissions.add(Permission.objects.get(codename="view_order"))
        services.set_role(employee, role)

        employee.is_active = False
        employee.save()
        services.revoke_permissions(employee)

        fresh = User.objects.get(pk=employee.user.pk)
        assert not fresh.has_perm("orders.view_order")
        assert employee.has_permission("orders.view_order") is False


# ═══════════════════════════════════════════════════════════
#  Admin screens
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAdminScreens:
    @pytest.fixture
    def manager(self, db):
        from administration.models import AdminProfile

        user = User.objects.create_user(
            email="emp-manager@test.local", password=PASSWORD, account_type=AccountType.ADMIN
        )
        user.is_active = True
        user.is_superuser = True
        user.save()
        AdminProfile.objects.create(user=user)
        grant_all_domains(user)
        return user

    def test_unassigned_customers_are_listed(self, manager, rep, mine):
        """
        ⚠️  A customer with no owner is followed up by nobody and appears on no
            rep's dashboard — and nothing draws attention to them but this list.
        """
        stray = make_customer("nobody@test.local", "بلا مسؤول")

        response = client_for(manager).get(reverse("v1:employees:admin-unassigned"))

        assert response.status_code == 200
        numbers = [row["customer_number"] for row in response.data["results"]]
        assert stray.customer_number in numbers
        assert mine.customer_number not in numbers

    def test_assigning_is_audited(self, manager, rep):
        from core.models.audit import AuditLog

        customer = make_customer("audited@test.local")

        response = client_for(manager).post(
            reverse("v1:employees:admin-assign"),
            {"customer": str(customer.pk), "employee": str(rep.pk), "note": "منطقة الجيزة"},
            format="json",
        )

        assert response.status_code == 201
        assert AuditLog.objects.filter(object_repr__contains=rep.employee_number).exists()

    def test_a_rep_cannot_assign_customers(self, rep):
        customer = make_customer("target@test.local")

        response = client_for(rep.user).post(
            reverse("v1:employees:admin-assign"),
            {"customer": str(customer.pk), "employee": str(rep.pk)},
            format="json",
        )

        assert response.status_code == 403
