"""
Creating staff from the panel — an account, a profile and an invite link.

⚠️  What these tests guard is the chain, not a single call:

        admin submits the form → login + profile exist → the mail carries a link →
        the link sets a password through the *existing* reset page → that person logs
        in and holds exactly the permissions of the role they were given.

    A break at any link leaves someone who was "added" and still cannot work, or —
    worse — someone who can work with more than their role says.
"""

import re

import pytest
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountType, SecurityToken, TokenPurpose, User
from administration.models import AdminProfile
from core.models.audit import AuditAction, AuditLog
from employees import services
from employees.models import EmployeeProfile, EmployeeRole, EmployeeRoleKind
from employees.permissions import MANAGE_TEAM
from mailing.models import OutboundMessage

PASSWORD = "Str0ng-Test-Pass!23"
NEW_PASSWORD = "Another-Str0ng-Pass!77"

pytestmark = pytest.mark.django_db


def grant(user, *codes):
    for code in codes:
        app_label, codename = code.split(".")
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )


def make_admin(email, *, owner=False, perms=()):
    user = User.objects.create_user(
        email=email, password=PASSWORD, account_type=AccountType.ADMIN
    )
    user.is_active = True
    user.first_name = "Owner" if owner else "Manager"
    user.save()
    AdminProfile.objects.create(user=user, is_owner=owner)
    grant(user, *perms)
    return user


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def owner():
    return make_admin("owner@test.local", owner=True)


@pytest.fixture
def role():
    role = EmployeeRole.objects.create(
        code="catalog-editor",
        kind=EmployeeRoleKind.OPERATIONS,
        name_ar="محرر كتالوج",
        name_en="Catalog editor",
    )
    role.permissions.set(
        [Permission.objects.get(codename="change_product", content_type__app_label="catalog")]
    )
    services.sync_role_permissions(role)
    return role


URL = "v1:employees:admin-staff"


def payload(role, **overrides):
    body = {
        "email": "New.Person@Test.local",
        "first_name": "سارة",
        "last_name": "أحمد",
        "phone": "+201001234567",
        "access": "STAFF_PORTAL",
        "role": str(role.pk),
    }
    body.update(overrides)
    return body


def invite_for(email) -> OutboundMessage:
    return OutboundMessage.objects.filter(to_email=email, template_key="staff_invite").get()


def token_from(message: OutboundMessage) -> str:
    return re.search(r"token=([\w\-]+)", message.body).group(1)


# ═══════════════════════════════════════════════════════════
#  Who may create
# ═══════════════════════════════════════════════════════════


class TestPermission:
    def test_owner_may_create(self, owner, role):
        response = client_for(owner).post(reverse(URL), payload(role), format="json")
        assert response.status_code == 201, response.content

    def test_owner_without_the_superuser_flag_is_not_locked_out(self, owner, role):
        """
        ⚠️  The regression this change fixes: `CanManageEmployees` once asked for the
            superuser flag or the permission and forgot `AdminProfile.is_owner`, so a
            real owner got 403 on the one screen that creates staff.
        """
        assert not owner.is_superuser
        assert client_for(owner).get(reverse(URL)).status_code == 200

    def test_superuser_may_create(self, role):
        root = User.objects.create_superuser(email="root@test.local", password=PASSWORD)
        assert client_for(root).post(reverse(URL), payload(role), format="json").status_code == 201

    def test_holder_of_the_team_permission_may_create(self, role):
        manager = make_admin("hr@test.local", perms=[MANAGE_TEAM])
        assert (
            client_for(manager).post(reverse(URL), payload(role), format="json").status_code
            == 201
        )

    def test_admin_without_the_permission_is_refused(self, role):
        other = make_admin("other@test.local")
        response = client_for(other).post(reverse(URL), payload(role), format="json")
        assert response.status_code == 403
        assert not User.objects.filter(email="new.person@test.local").exists()

    def test_anonymous_is_refused(self, role):
        response = APIClient().post(reverse(URL), payload(role), format="json")
        assert response.status_code in (401, 403)

    def test_an_employee_cannot_create_staff(self, role):
        user = User.objects.create_user(
            email="rep@test.local", password=PASSWORD, account_type=AccountType.EMPLOYEE
        )
        user.is_active = True
        user.save()
        EmployeeProfile.objects.create(user=user, employee_number="EMP-X", role=role)

        assert client_for(user).post(reverse(URL), payload(role), format="json").status_code == 403


# ═══════════════════════════════════════════════════════════
#  What gets created
# ═══════════════════════════════════════════════════════════


class TestCreateStaffPortal:
    def test_creates_login_profile_and_invite(self, owner, role):
        response = client_for(owner).post(reverse(URL), payload(role), format="json")

        assert response.status_code == 201
        body = response.json()
        assert body["invite_sent"] is True
        assert body["email"] == "new.person@test.local"
        assert body["account_type"] == "EMPLOYEE"
        assert body["invite_pending"] is True
        assert body["employee_number"].startswith("EMP-")

        user = User.objects.get(email="new.person@test.local")
        assert user.is_active
        assert user.email_verified_at is not None
        assert user.account_type == AccountType.EMPLOYEE
        assert not user.has_usable_password()
        assert user.phone == "+201001234567"

        profile = user.employee_profile
        assert profile.role == role
        assert profile.is_active
        # A portal user is not an admin.
        assert not hasattr(user, "admin_profile")

    def test_the_role_group_permissions_apply(self, owner, role):
        client_for(owner).post(reverse(URL), payload(role), format="json")

        user = User.objects.get(email="new.person@test.local")
        assert user.groups.filter(name="employee:catalog-editor").exists()
        assert user.has_perm("catalog.change_product")
        assert not user.has_perm("finance.add_expense")

    def test_the_invite_mail_is_enqueued_with_a_link(self, owner, role):
        client_for(owner).post(reverse(URL), payload(role), format="json")

        message = invite_for("new.person@test.local")
        assert "/auth/reset-password?token=" in message.body
        assert "محرر كتالوج" in message.body
        assert "Manager" not in message.subject  # subject is the fixed branded line
        assert message.language == "ar"

    def test_english_recipient_gets_english_mail(self, owner, role):
        client_for(owner).post(
            reverse(URL), payload(role, preferred_language="en"), format="json"
        )

        message = invite_for("new.person@test.local")
        assert message.language == "en"
        assert "Catalog editor" in message.body
        assert "7 days" in message.body

    def test_the_raw_token_is_not_stored_or_returned(self, owner, role):
        response = client_for(owner).post(reverse(URL), payload(role), format="json")
        raw = token_from(invite_for("new.person@test.local"))

        assert raw not in response.content.decode()
        record = SecurityToken.objects.get(user__email="new.person@test.local")
        assert raw not in record.token_hash
        assert record.purpose == TokenPurpose.PASSWORD_RESET

    def test_invite_token_lives_for_days_not_minutes(self, owner, role):
        client_for(owner).post(reverse(URL), payload(role), format="json")

        record = SecurityToken.objects.get(user__email="new.person@test.local")
        remaining = record.expires_at - record.created_at
        assert remaining.days >= 6

    def test_audit_entry_is_written_without_secrets(self, owner, role):
        response = client_for(owner).post(
            reverse(URL),
            payload(role, temporary_password="Temp-Passw0rd!xyz"),
            format="json",
        )
        employee_id = response.json()["id"]

        entry = AuditLog.objects.get(action=AuditAction.CREATE, object_id=employee_id)
        assert entry.actor_id == owner.pk
        assert "new.person@test.local" in entry.object_repr
        assert entry.changes["temporary_password"] is True
        assert entry.changes["invite_sent"] is False
        assert "Temp-Passw0rd" not in str(entry.changes)

    def test_manager_and_extension_are_stored(self, owner, role):
        boss = EmployeeProfile.objects.create(
            user=make_admin("boss@test.local"), employee_number="EMP-BOSS", role=role
        )

        response = client_for(owner).post(
            reverse(URL),
            payload(role, manager=str(boss.pk), phone_extension="204"),
            format="json",
        )

        assert response.status_code == 201
        profile = EmployeeProfile.objects.get(user__email="new.person@test.local")
        assert profile.manager == boss
        assert profile.phone_extension == "204"

    def test_the_new_person_appears_in_the_staff_list(self, owner, role):
        client_for(owner).post(reverse(URL), payload(role), format="json")

        rows = client_for(owner).get(reverse(URL)).json()["results"]
        assert [r["email"] for r in rows] == ["new.person@test.local"]
        assert rows[0]["invite_pending"] is True


class TestCreateAdminPanel:
    def test_admin_panel_access_gets_admin_account_and_profiles(self, owner, role):
        response = client_for(owner).post(
            reverse(URL), payload(role, access="ADMIN_PANEL"), format="json"
        )

        assert response.status_code == 201
        user = User.objects.get(email="new.person@test.local")
        assert user.account_type == AccountType.ADMIN
        assert user.admin_profile.is_owner is False
        assert user.employee_profile.role == role

    def test_admin_panel_user_holds_exactly_the_roles_permissions(self, owner, role):
        """
        ⚠️  Not the whole `system-admins` bundle: a catalogue editor who could also
            open finance and accounts is not what the form said.
        """
        client_for(owner).post(reverse(URL), payload(role, access="ADMIN_PANEL"), format="json")

        user = User.objects.get(email="new.person@test.local")
        assert user.has_perm("catalog.change_product")
        assert not user.has_perm("accounts.change_user")
        assert not user.has_perm("finance.add_expense")
        assert not user.groups.filter(name="system-admins").exists()

        # …and what the frontend reads to draw the sidebar agrees.
        assert "catalog.change_product" in user.get_all_permissions()

    def test_admin_panel_user_opens_the_catalog_but_not_staff_screens(self, owner, role):
        client_for(owner).post(reverse(URL), payload(role, access="ADMIN_PANEL"), format="json")
        user = User.objects.get(email="new.person@test.local")

        client = client_for(user)
        assert client.get(reverse("v1:catalog:admin-products")).status_code == 200
        assert client.get(reverse(URL)).status_code == 403


# ═══════════════════════════════════════════════════════════
#  Validation
# ═══════════════════════════════════════════════════════════


class TestValidation:
    def test_duplicate_email_is_a_field_error(self, owner, role):
        client_for(owner).post(reverse(URL), payload(role), format="json")

        response = client_for(owner).post(
            reverse(URL), payload(role, email="NEW.person@test.local", phone="+201009999999"),
            format="json",
        )

        assert response.status_code == 400
        assert "email" in response.json()["fields"]
        assert User.objects.filter(email__iexact="new.person@test.local").count() == 1

    def test_duplicate_phone_is_a_field_error(self, owner, role):
        client_for(owner).post(reverse(URL), payload(role), format="json")

        response = client_for(owner).post(
            reverse(URL), payload(role, email="second@test.local"), format="json"
        )

        assert response.status_code == 400
        assert "phone" in response.json()["fields"]

    def test_failed_creation_leaves_nothing_behind(self, owner, role):
        """One transaction: a duplicate must not leave a half-made user or a mail."""
        client_for(owner).post(reverse(URL), payload(role), format="json")

        def counts():
            return (
                User.objects.count(),
                EmployeeProfile.objects.count(),
                OutboundMessage.objects.count(),
            )

        before = counts()

        client_for(owner).post(reverse(URL), payload(role, phone="+201005555555"), format="json")

        assert counts() == before

    def test_required_fields(self, owner):
        response = client_for(owner).post(reverse(URL), {}, format="json")
        assert response.status_code == 400
        assert {"email", "first_name", "access", "role"} <= set(response.json()["fields"])

    def test_unknown_access_is_refused(self, owner, role):
        response = client_for(owner).post(
            reverse(URL), payload(role, access="SUPERUSER"), format="json"
        )
        assert response.status_code == 400
        assert "access" in response.json()["fields"]

    def test_inactive_role_is_refused(self, owner, role):
        role.is_active = False
        role.save()

        response = client_for(owner).post(reverse(URL), payload(role), format="json")
        assert response.status_code == 400
        assert "role" in response.json()["fields"]

    def test_bad_phone_is_refused(self, owner, role):
        response = client_for(owner).post(reverse(URL), payload(role, phone="abc"), format="json")
        assert response.status_code == 400
        assert "phone" in response.json()["fields"]

    def test_weak_temporary_password_is_refused(self, owner, role):
        response = client_for(owner).post(
            reverse(URL), payload(role, temporary_password="12345678"), format="json"
        )
        assert response.status_code == 400
        assert "temporary_password" in response.json()["fields"]


# ═══════════════════════════════════════════════════════════
#  Temporary password fallback
# ═══════════════════════════════════════════════════════════


class TestTemporaryPassword:
    def test_temporary_password_logs_in_and_sends_no_mail(self, owner, role):
        response = client_for(owner).post(
            reverse(URL), payload(role, temporary_password="Temp-Passw0rd!xyz"), format="json"
        )

        assert response.status_code == 201
        assert response.json()["invite_sent"] is False
        assert not OutboundMessage.objects.filter(template_key="staff_invite").exists()

        login = APIClient().post(
            reverse("v1:accounts:login"),
            {"identifier": "new.person@test.local", "password": "Temp-Passw0rd!xyz"},
            format="json",
        )
        assert login.status_code == 200, login.content

    def test_without_it_the_account_cannot_log_in_yet(self, owner, role):
        client_for(owner).post(reverse(URL), payload(role), format="json")

        login = APIClient().post(
            reverse("v1:accounts:login"),
            {"identifier": "new.person@test.local", "password": "anything"},
            format="json",
        )
        assert login.status_code in (400, 401)


# ═══════════════════════════════════════════════════════════
#  The invite link, end to end
# ═══════════════════════════════════════════════════════════


class TestInviteFlow:
    def test_invite_link_sets_a_password_and_the_person_logs_in(self, owner, role):
        client_for(owner).post(reverse(URL), payload(role), format="json")
        raw = token_from(invite_for("new.person@test.local"))

        confirm = APIClient().post(
            reverse("v1:accounts:password-reset-confirm"),
            {"token": raw, "new_password": NEW_PASSWORD},
            format="json",
        )
        assert confirm.status_code == 200, confirm.content

        login = APIClient().post(
            reverse("v1:accounts:login"),
            {"identifier": "new.person@test.local", "password": NEW_PASSWORD},
            format="json",
        )
        assert login.status_code == 200, login.content
        me = login.json()["user"]
        assert me["account_type"] == "EMPLOYEE"
        assert "catalog.change_product" in me["permissions"]

    def test_the_link_is_single_use(self, owner, role):
        client_for(owner).post(reverse(URL), payload(role), format="json")
        raw = token_from(invite_for("new.person@test.local"))
        body = {"token": raw, "new_password": NEW_PASSWORD}

        confirm_url = reverse("v1:accounts:password-reset-confirm")
        assert APIClient().post(confirm_url, body, format="json").status_code == 200
        assert APIClient().post(confirm_url, body, format="json").status_code == 400


# ═══════════════════════════════════════════════════════════
#  Resend
# ═══════════════════════════════════════════════════════════


class TestResend:
    def resend_url(self, employee_id):
        return reverse("v1:employees:admin-staff-resend-invite", args=[employee_id])

    def test_resend_issues_a_new_working_link_and_revokes_the_old_one(self, owner, role):
        created = client_for(owner).post(reverse(URL), payload(role), format="json").json()
        first = token_from(invite_for("new.person@test.local"))

        response = client_for(owner).post(self.resend_url(created["id"]))
        assert response.status_code == 200

        messages = OutboundMessage.objects.filter(
            to_email="new.person@test.local", template_key="staff_invite"
        ).order_by("created_at")
        assert messages.count() == 2
        second = token_from(messages.last())
        assert second != first

        # The first link no longer works, the second does.
        stale = APIClient().post(
            reverse("v1:accounts:password-reset-confirm"),
            {"token": first, "new_password": NEW_PASSWORD},
            format="json",
        )
        assert stale.status_code == 400
        fresh = APIClient().post(
            reverse("v1:accounts:password-reset-confirm"),
            {"token": second, "new_password": NEW_PASSWORD},
            format="json",
        )
        assert fresh.status_code == 200

    def test_resend_is_audited(self, owner, role):
        created = client_for(owner).post(reverse(URL), payload(role), format="json").json()

        client_for(owner).post(self.resend_url(created["id"]))

        assert AuditLog.objects.filter(
            action=AuditAction.UPDATE, object_id=created["id"], changes={"invite_resent": True}
        ).exists()

    def test_resend_is_refused_once_the_person_has_signed_in(self, owner, role):
        created = client_for(owner).post(
            reverse(URL), payload(role, temporary_password="Temp-Passw0rd!xyz"), format="json"
        ).json()
        APIClient().post(
            reverse("v1:accounts:login"),
            {"identifier": "new.person@test.local", "password": "Temp-Passw0rd!xyz"},
            format="json",
        )

        response = client_for(owner).post(self.resend_url(created["id"]))

        assert response.status_code == 409
        assert not OutboundMessage.objects.filter(template_key="staff_invite").exists()

    def test_resend_requires_the_permission(self, owner, role):
        created = client_for(owner).post(reverse(URL), payload(role), format="json").json()
        outsider = make_admin("outsider@test.local")

        assert client_for(outsider).post(self.resend_url(created["id"])).status_code == 403

    def test_resend_unknown_employee_is_404(self, owner):
        import uuid

        assert client_for(owner).post(self.resend_url(uuid.uuid4())).status_code == 404
