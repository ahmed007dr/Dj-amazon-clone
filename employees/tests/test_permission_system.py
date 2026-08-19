"""
Domain permissions.

⚠️  The exit gate: **"admin" is no longer a permission**.

        Someone with an admin profile and no grants reaches nothing · a grant
        opens its own domain alone · the owner always passes · and granting
        itself is guarded.

    And the greatest dangers it guards: the system being locked away from its
    own owner with no way back · and a single grant opening a domain nobody intended.
"""

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from administration.models import AdminProfile
from core.permissions import CATALOGUE_CODES, DOMAIN_PERMISSIONS

PASSWORD = "Str0ng-Test-Pass!23"


def make_admin(email: str, *, owner: bool = False, perms: list[str] | None = None) -> User:
    user = User.objects.create_user(
        email=email, password=PASSWORD, account_type=AccountType.ADMIN
    )
    user.is_active = True
    user.save()
    AdminProfile.objects.create(user=user, is_owner=owner)

    for code in perms or []:
        app_label, codename = code.split(".")
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )

    return user


def client_for(user: User) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# ═══════════════════════════════════════════════════════════
#  The gate
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestDomainGate:
    def test_an_admin_without_grants_reaches_nothing(self, db):
        """
        ⚠️  This is the whole change: the admin profile alone used to open
            fourteen screens — the catalogue, the inventory, the accounts and
            the settings together.
        """
        client = client_for(make_admin("bare@test.local"))

        for name in (
            "v1:catalog:admin-products",
            "v1:inventory:stock",
            "v1:administration:accounts",
            "v1:academic:admin-universities",
        ):
            assert client.get(reverse(name)).status_code == 403, name

    def test_a_grant_opens_its_domain_only(self, db):
        """⚠️  One grant opens its own domain, not its neighbours: otherwise "admin"
            returns as a permission under another name."""
        client = client_for(
            make_admin("catalog@test.local", perms=["catalog.change_product"])
        )

        assert client.get(reverse("v1:catalog:admin-products")).status_code == 200
        assert client.get(reverse("v1:inventory:stock")).status_code == 403
        assert client.get(reverse("v1:administration:accounts")).status_code == 403

    def test_the_owner_passes_everything(self, db):
        """
        ⚠️  **Without this there is no way back.**

            The first wrong configuration would lock the system away from its
            own owner, reopening only from the command line.
        """
        client = client_for(make_admin("owner@test.local", owner=True))

        for name in (
            "v1:catalog:admin-products",
            "v1:inventory:stock",
            "v1:administration:accounts",
            "v1:access:policies",
        ):
            assert client.get(reverse(name)).status_code == 200, name

    def test_a_superuser_passes_everything(self, db):
        user = User.objects.create_superuser(email="root@test.local", password=PASSWORD)
        user.is_active = True
        user.save()

        assert client_for(user).get(reverse("v1:catalog:admin-products")).status_code == 200

    def test_a_customer_reaches_nothing(self, db):
        """⚠️  The permission alone is not enough without authentication, and vice versa."""
        user = User.objects.create_user(
            email="shopper@test.local", password=PASSWORD, account_type=AccountType.STUDENT
        )
        user.is_active = True
        user.save()

        assert client_for(user).get(reverse("v1:catalog:admin-products")).status_code == 403


# ═══════════════════════════════════════════════════════════
#  What the frontend knows
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestWhatTheClientLearns:
    def test_me_carries_the_permissions(self, db):
        """
        ⚠️  Without these fields the frontend cannot hide anything — and it used
            to know the account type alone.
        """
        user = make_admin("known@test.local", perms=["catalog.change_product"])

        data = client_for(user).get(reverse("v1:accounts:me")).data

        assert "catalog.change_product" in data["permissions"]
        assert data["has_admin_profile"] is True
        assert data["is_owner"] is False

    def test_the_owner_is_flagged_not_listed(self, db):
        """⚠️  The owner's permissions are "everything": sending thousands of strings
            on every startup serves no purpose, and the flag is enough."""
        data = client_for(make_admin("boss@test.local", owner=True)).get(
            reverse("v1:accounts:me")
        ).data

        assert data["is_owner"] is True

    def test_group_permissions_are_included(self, db):
        """
        ⚠️  `has_perm` reads the groups, and a role is assigned through them (ADR-53).
            Reading the user's own permissions alone would have hidden from the
            frontend everything granted through their role.
        """
        from django.contrib.auth.models import Group

        user = make_admin("grouped@test.local")
        group = Group.objects.create(name="test-role")
        group.permissions.add(
            Permission.objects.get(
                content_type__app_label="inventory", codename="change_stock"
            )
        )
        user.groups.add(group)

        data = client_for(user).get(reverse("v1:accounts:me")).data
        assert "inventory.change_stock" in data["permissions"]


# ═══════════════════════════════════════════════════════════
#  Granting
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestGranting:
    def test_the_catalogue_is_curated_not_raw(self, db):
        """
        ⚠️  Django's table holds two hundred automatic permissions, `delete_user`
            among them. Displaying it as-is makes granting that by oversight one click away.
        """
        client = client_for(
            make_admin("granter@test.local", perms=["employees.change_customerassignment"])
        )

        groups = client.get(reverse("v1:employees:admin-permissions")).data
        codes = {row["code"] for group in groups for row in group["permissions"]}

        assert codes == CATALOGUE_CODES
        assert "accounts.delete_user" not in codes
        assert all(row["label_ar"] for group in groups for row in group["permissions"])

    def test_granting_a_role_syncs_the_group(self, db):
        """
        ⚠️  **Without the synchronisation, permissions are decoration** (ADR-53).

            `has_perm` reads the groups, not the role table; saving without
            synchronising makes the screen show a configured role while every
            check fails.
        """
        from employees.models import EmployeeRole, EmployeeRoleKind

        granter = make_admin("boss2@test.local", perms=["employees.change_customerassignment"])
        role = EmployeeRole.objects.create(
            code="tester", kind=EmployeeRoleKind.SALES_REP, name_ar="مجرّب", name_en="Tester"
        )

        response = client_for(granter).patch(
            reverse("v1:employees:admin-role-detail", args=[role.pk]),
            {"permissions": ["catalog.change_product"]},
            format="json",
        )

        assert response.status_code == 200
        role.refresh_from_db()
        assert role.group is not None
        assert role.group.permissions.filter(codename="change_product").exists()

    def test_a_permission_outside_the_catalogue_is_refused(self, db):
        """⚠️  A hand-crafted call would have granted what the screen never displays."""
        from employees.models import EmployeeRole, EmployeeRoleKind

        granter = make_admin("boss3@test.local", perms=["employees.change_customerassignment"])
        role = EmployeeRole.objects.create(
            code="tester2", kind=EmployeeRoleKind.SALES_REP, name_ar="مجرّب", name_en="T"
        )

        response = client_for(granter).patch(
            reverse("v1:employees:admin-role-detail", args=[role.pk]),
            {"permissions": ["accounts.delete_user"]},
            format="json",
        )

        assert response.status_code == 400
        assert not role.permissions.exists()

    def test_granting_needs_the_team_permission(self, db):
        """⚠️  Whoever holds granting can grant themselves everything — so the gate
            on it is the gate on the whole system."""
        client = client_for(make_admin("nobody@test.local", perms=["catalog.change_product"]))

        assert client.get(reverse("v1:employees:admin-permissions")).status_code == 403


# ═══════════════════════════════════════════════════════════
#  The deployment safety net
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestDeploymentSafetyNet:
    def test_the_command_restores_what_admins_had(self, db):
        """
        ⚠️  Without this command **every existing admin** loses access the moment it deploys.
        """
        from io import StringIO

        from django.core.management import call_command

        admin = make_admin("existing@test.local")
        client = client_for(admin)

        assert client.get(reverse("v1:catalog:admin-products")).status_code == 403

        call_command("grant_admin_permissions", stdout=StringIO())

        admin = User.objects.get(pk=admin.pk)  # the cache holds the permissions
        assert client_for(admin).get(reverse("v1:catalog:admin-products")).status_code == 200

    def test_the_command_does_not_widen_beyond_what_was_implicit(self, db):
        """
        ⚠️  Finance, suppliers and loyalty were already guarded by explicit
            permissions — granting them here would have turned a tightening into a widening.
        """
        from io import StringIO

        from django.core.management import call_command

        admin = make_admin("existing2@test.local")
        call_command("grant_admin_permissions", stdout=StringIO())

        admin = User.objects.get(pk=admin.pk)
        granted = admin.get_all_permissions()

        assert set(DOMAIN_PERMISSIONS.values()) <= granted
        assert "finance.view_revenueentry" not in granted
        assert "suppliers.add_purchaseorder" not in granted
        assert "employees.change_customerassignment" not in granted

    def test_the_owner_is_left_out_of_the_group(self, db):
        """⚠️  The owner passes by definition; including them conflates who holds
            by office with who holds by grant."""
        from io import StringIO

        from django.core.management import call_command

        owner = make_admin("boss4@test.local", owner=True)
        call_command("grant_admin_permissions", stdout=StringIO())

        assert not owner.groups.filter(name="system-admins").exists()
