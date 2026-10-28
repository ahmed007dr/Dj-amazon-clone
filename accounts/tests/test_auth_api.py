"""
Authentication endpoint tests.

They cover the full lifecycle: register ← activate ← log in ← forgot ← recover ← log in
and guard the security properties that were broken in the legacy code.
"""

from datetime import UTC, datetime, timedelta

import pytest
from django.core import mail as django_mail
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import AccountStatus, SecurityToken, TokenPurpose, User, UserSession

PASSWORD = "Str0ng-Test-Pass!23"


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture(autouse=True)
def _clear_throttles():
    """Rate limiting would fail consecutive tests were the cache not cleared."""
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def active_user(db):
    user = User.objects.create_user(email="active@test.local", password=PASSWORD)
    user.is_active = True
    user.email_verified_at = "2026-01-01T00:00:00Z"
    user.save()
    return user


# ═══════════════════════════════════════════════════════════
#  Registration and activation
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRegistration:
    def test_register_creates_inactive_user(self, client):
        """
        ⛔ Legacy code: `form.save()` after `commit=False` saved an active user
           and ignored `is_active=False` — making the activation system
           entirely decorative and trivially bypassed.
        """
        response = client.post(
            reverse("v1:accounts:register"),
            {"email": "new@test.local", "password": PASSWORD},
            format="json",
        )
        assert response.status_code == 201

        user = User.objects.get(email="new@test.local")
        assert not user.is_active
        assert not user.is_email_verified
        assert not user.can_authenticate

    def test_register_sends_verification_email(self, client, django_capture_on_commit_callbacks):
        """
        ⚠️  Delivery starts on `on_commit` — that is, after the transaction commits.

            An email going out before the commit means a message about an
            account whose transaction may be rolled back, so it does not exist.
            The test captures the callbacks and runs them, to measure what
            actually happens in production.
        """
        django_mail.outbox.clear()
        with django_capture_on_commit_callbacks(execute=True):
            client.post(
                reverse("v1:accounts:register"),
                {"email": "mail@test.local", "password": PASSWORD},
                format="json",
            )
        assert len(django_mail.outbox) == 1
        assert "فعّل" in django_mail.outbox[0].subject

    def test_register_respects_preferred_language(self, client, django_capture_on_commit_callbacks):
        """The email arrives in the recipient's language, not the request's."""
        django_mail.outbox.clear()
        with django_capture_on_commit_callbacks(execute=True):
            client.post(
                reverse("v1:accounts:register"),
                {"email": "en@test.local", "password": PASSWORD, "preferred_language": "en"},
                format="json",
                HTTP_ACCEPT_LANGUAGE="ar",
            )
        assert "Activate" in django_mail.outbox[0].subject

    def test_duplicate_email_rejected(self, client, active_user):
        response = client.post(
            reverse("v1:accounts:register"),
            {"email": "active@test.local", "password": PASSWORD},
            format="json",
        )
        assert response.status_code == 400
        assert response.data["code"] == "VALIDATION_ERROR"
        assert "email" in response.data["fields"]

    def test_weak_password_rejected(self, client):
        response = client.post(
            reverse("v1:accounts:register"),
            {"email": "weak@test.local", "password": "12345678"},
            format="json",
        )
        assert response.status_code == 400
        assert "password" in response.data["fields"]

    def test_verify_email_activates_and_returns_tokens(self, client):
        client.post(
            reverse("v1:accounts:register"),
            {"email": "verify@test.local", "password": PASSWORD},
            format="json",
        )
        user = User.objects.get(email="verify@test.local")

        # The plaintext token is not stored — we issue a fresh one for the test
        from accounts import services

        _, raw = services.issue_token(user, TokenPurpose.EMAIL_VERIFICATION)

        response = client.post(reverse("v1:accounts:verify-email"), {"token": raw}, format="json")
        assert response.status_code == 200
        assert "access" in response.data

        user.refresh_from_db()
        assert user.is_active
        assert user.is_email_verified

    def test_verification_token_is_single_use(self, client, active_user):
        from accounts import services

        _, raw = services.issue_token(active_user, TokenPurpose.EMAIL_VERIFICATION)
        url = reverse("v1:accounts:verify-email")

        assert client.post(url, {"token": raw}, format="json").status_code == 200
        assert client.post(url, {"token": raw}, format="json").status_code == 400


# ═══════════════════════════════════════════════════════════
#  Login
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestLogin:
    def test_login_returns_tokens_and_opens_session(self, client, active_user):
        response = client.post(
            reverse("v1:accounts:login"),
            {"identifier": "active@test.local", "password": PASSWORD},
            format="json",
        )
        assert response.status_code == 200
        assert "access" in response.data
        assert "refresh" in response.data
        assert UserSession.objects.filter(user=active_user, logout_at__isnull=True).exists()

    def test_login_by_phone(self, client, active_user):
        active_user.phone = "+201001234567"
        active_user.save()

        response = client.post(
            reverse("v1:accounts:login"),
            {"identifier": "+201001234567", "password": PASSWORD},
            format="json",
        )
        assert response.status_code == 200

    def test_unverified_user_cannot_login(self, client, db):
        User.objects.create_user(email="unverified@test.local", password=PASSWORD)
        response = client.post(
            reverse("v1:accounts:login"),
            {"identifier": "unverified@test.local", "password": PASSWORD},
            format="json",
        )
        assert response.status_code == 400

    def test_suspended_user_cannot_login(self, client, active_user):
        """⛔ The legacy backend did not check the status at all."""
        active_user.status = AccountStatus.SUSPENDED
        active_user.save()

        response = client.post(
            reverse("v1:accounts:login"),
            {"identifier": "active@test.local", "password": PASSWORD},
            format="json",
        )
        assert response.status_code == 400

    def test_failure_message_does_not_reveal_account_existence(self, client, active_user):
        """
        Distinguishing "email not registered" from "wrong password" turns the
        login screen into an account discovery tool.
        """
        url = reverse("v1:accounts:login")

        unknown = client.post(
            url, {"identifier": "nobody@test.local", "password": PASSWORD}, format="json"
        )
        wrong_pw = client.post(
            url,
            {"identifier": "active@test.local", "password": "WrongPass!123"},
            format="json",
        )

        assert unknown.status_code == wrong_pw.status_code == 400
        assert unknown.data["fields"] == wrong_pw.data["fields"]


# ═══════════════════════════════════════════════════════════
#  Password recovery
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPasswordReset:
    def test_response_is_identical_for_unknown_email(self, client, active_user):
        """⚠️  A different response = a tool for discovering registered accounts."""
        url = reverse("v1:accounts:password-reset")

        known = client.post(url, {"email": "active@test.local"}, format="json")
        unknown = client.post(url, {"email": "nobody@test.local"}, format="json")

        assert known.status_code == unknown.status_code == 200
        assert known.data == unknown.data

    def test_reset_flow_end_to_end(self, client, active_user):
        from accounts import services

        _, raw = services.issue_token(active_user, TokenPurpose.PASSWORD_RESET)
        new_password = "Brand-New-Pass!456"

        response = client.post(
            reverse("v1:accounts:password-reset-confirm"),
            {"token": raw, "new_password": new_password},
            format="json",
        )
        assert response.status_code == 200

        active_user.refresh_from_db()
        assert active_user.check_password(new_password)

        # Logging in with the new password works
        assert (
            client.post(
                reverse("v1:accounts:login"),
                {"identifier": "active@test.local", "password": new_password},
                format="json",
            ).status_code
            == 200
        )

    def test_reset_revokes_all_sessions(self, client, active_user):
        """Anyone who knew the old password must lose access immediately."""
        from accounts import services

        services.open_session(active_user, session_key="session-to-kill")

        _, raw = services.issue_token(active_user, TokenPurpose.PASSWORD_RESET)
        client.post(
            reverse("v1:accounts:password-reset-confirm"),
            {"token": raw, "new_password": "Brand-New-Pass!456"},
            format="json",
        )

        assert not UserSession.objects.filter(user=active_user, logout_at__isnull=True).exists()

    def test_token_is_single_use(self, client, active_user):
        from accounts import services

        _, raw = services.issue_token(active_user, TokenPurpose.PASSWORD_RESET)
        url = reverse("v1:accounts:password-reset-confirm")
        payload = {"token": raw, "new_password": "Brand-New-Pass!456"}

        assert client.post(url, payload, format="json").status_code == 200
        assert client.post(url, payload, format="json").status_code == 400

    def test_token_is_stored_hashed(self, active_user):
        """A database leak must not grant the ability to reset passwords."""
        from accounts import services

        record, raw = services.issue_token(active_user, TokenPurpose.PASSWORD_RESET)
        assert raw not in record.token_hash
        assert not SecurityToken.objects.filter(token_hash=raw).exists()

    def test_issuing_new_token_invalidates_previous(self, active_user):
        from accounts import services

        _, first = services.issue_token(active_user, TokenPurpose.PASSWORD_RESET)
        _, second = services.issue_token(active_user, TokenPurpose.PASSWORD_RESET)

        from core.errors import BusinessError

        with pytest.raises(BusinessError):
            services.consume_token(first, TokenPurpose.PASSWORD_RESET)

        assert services.consume_token(second, TokenPurpose.PASSWORD_RESET)


# ═══════════════════════════════════════════════════════════
#  Immediate suspension  (ADR-16)
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSuspensionIsImmediate:
    def test_suspension_blocks_existing_token_at_once(self, client, active_user):
        """
        ⚠️  The heart of ADR-16.

        Without the third layer (the cache set) an already-issued token stays
        valid until it expires — meaning a suspended user keeps working for 10 minutes.
        """
        login = client.post(
            reverse("v1:accounts:login"),
            {"identifier": "active@test.local", "password": PASSWORD},
            format="json",
        )
        access = login.data["access"]
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        assert client.get(reverse("v1:accounts:me")).status_code == 200

        from accounts import services

        services.suspend_account(active_user, reason="مخالفة")

        # The same token — must be rejected immediately
        response = client.get(reverse("v1:accounts:me"))
        assert response.status_code == 401
        assert response.data["code"] == "ACCOUNT_SUSPENDED"

    def test_suspension_closes_sessions_and_logs_change(self, active_user):
        from accounts import services
        from accounts.models import AccountStatusChange

        services.open_session(active_user, session_key="live-session")
        services.suspend_account(active_user, reason="اختبار")

        assert not UserSession.objects.filter(user=active_user, logout_at__isnull=True).exists()

        change = AccountStatusChange.objects.get(user=active_user)
        assert change.to_status == AccountStatus.SUSPENDED
        assert change.reason == "اختبار"

    def test_reactivation_restores_access(self, client, active_user):
        from accounts import services

        services.suspend_account(active_user, reason="اختبار")
        services.activate_account(active_user, reason="انتهى السبب")

        assert not services.is_suspended_cached(active_user.pk)
        assert (
            client.post(
                reverse("v1:accounts:login"),
                {"identifier": "active@test.local", "password": PASSWORD},
                format="json",
            ).status_code
            == 200
        )


# ═══════════════════════════════════════════════════════════
#  Sessions
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestSessions:
    def test_user_sees_only_own_sessions(self, client, active_user):
        other = User.objects.create_user(email="other@test.local", password=PASSWORD)
        other.is_active = True
        other.save()

        from accounts import services

        services.open_session(active_user, session_key="mine")
        services.open_session(other, session_key="theirs")

        client.force_authenticate(user=active_user)
        response = client.get(reverse("v1:accounts:sessions"))

        assert response.status_code == 200
        assert len(response.data["results"]) == 1

    def test_cannot_revoke_another_users_session(self, client, active_user):
        """
        ⚠️  The ownership check — the most common hole in the legacy code (IDOR).
            And `404`, not `403`, so the difference does not become an enumeration tool.
        """
        other = User.objects.create_user(email="victim@test.local", password=PASSWORD)
        from accounts import services

        victim_session = services.open_session(other, session_key="victim")

        client.force_authenticate(user=active_user)
        response = client.post(reverse("v1:accounts:session-revoke", args=[victim_session.pk]))

        assert response.status_code == 404
        victim_session.refresh_from_db()
        assert victim_session.logout_at is None

    # ── Pagination ───────────────────────────────────────────

    @staticmethod
    def _open_many(user, count, *, prefix="s"):
        """
        `count` open sessions with distinct, increasing sign-in times (oldest first).

        `login_at` is `auto_now_add`, so it is rewritten after creation — otherwise a
        fast loop could give several rows the same instant and the ordering
        assertions would be exercising the tie-break by accident.
        """
        from accounts import services

        base = datetime(2026, 1, 1, tzinfo=UTC)
        sessions = []
        for i in range(count):
            session = services.open_session(user, session_key=f"{prefix}-{i}")
            UserSession.objects.filter(pk=session.pk).update(login_at=base + timedelta(minutes=i))
            sessions.append(session)
        return sessions

    @staticmethod
    def _page(client, page=None, **params):
        if page is not None:
            params["page"] = page
        return client.get(reverse("v1:accounts:sessions"), params)

    def test_response_is_paginated_without_count(self, client, active_user):
        """⚠️  `pages` is exposed, `count` is not (ADR-32)."""
        self._open_many(active_user, 3)

        client.force_authenticate(user=active_user)
        response = self._page(client)

        assert response.status_code == 200
        assert set(response.data) == {"results", "page", "pages", "next", "previous"}
        assert response.data["page"] == 1
        assert response.data["pages"] == 1
        assert response.data["next"] is None
        assert response.data["previous"] is None
        assert {"session_key", "user_agent"}.isdisjoint(response.data["results"][0])

    def test_pages_hold_ten_and_cover_every_session_exactly_once(self, client, active_user):
        sessions = self._open_many(active_user, 25)
        client.force_authenticate(user=active_user)

        pages = [self._page(client, n) for n in (1, 2, 3)]

        assert [len(r.data["results"]) for r in pages] == [10, 10, 5]
        assert {r.data["pages"] for r in pages} == {3}
        assert pages[0].data["next"] and not pages[0].data["previous"]
        assert pages[1].data["next"] and pages[1].data["previous"]
        assert not pages[2].data["next"] and pages[2].data["previous"]

        ids = [row["id"] for r in pages for row in r.data["results"]]
        # Newest sign-in first, straight across the page boundaries, nothing repeated.
        assert ids == [session.pk for session in reversed(sessions)]

    def test_page_defaults_to_first(self, client, active_user):
        sessions = self._open_many(active_user, 12)
        client.force_authenticate(user=active_user)

        response = self._page(client)

        assert response.data["page"] == 1
        assert response.data["results"][0]["id"] == sessions[-1].pk

    def test_order_does_not_move_when_a_device_is_used_between_pages(self, client, active_user):
        """
        ⚠️  `last_activity` is flushed in bulk, so it changes between two clicks.
            Ordering by it would shift rows across the page boundary — one shown
            twice, another never. `login_at` does not move.
        """
        from django.utils import timezone

        sessions = self._open_many(active_user, 15)
        newest_first = [session.pk for session in reversed(sessions)]
        client.force_authenticate(user=active_user)

        assert [r["id"] for r in self._page(client, 2).data["results"]] == newest_first[10:]

        # The oldest device is used right now, and the presence flush writes it.
        UserSession.objects.filter(pk=sessions[0].pk).update(last_activity=timezone.now())

        assert [r["id"] for r in self._page(client, 1).data["results"]] == newest_first[:10]
        assert [r["id"] for r in self._page(client, 2).data["results"]] == newest_first[10:]

    def test_equal_sign_in_times_still_order_deterministically(self, client, active_user):
        sessions = self._open_many(active_user, 12)
        UserSession.objects.filter(user=active_user).update(login_at=sessions[0].login_at)

        client.force_authenticate(user=active_user)
        ids = [row["id"] for n in (1, 2) for row in self._page(client, n).data["results"]]

        assert ids == sorted((session.pk for session in sessions), reverse=True)

    def test_other_users_sessions_never_appear_on_any_page(self, client, active_user):
        other = User.objects.create_user(email="other2@test.local", password=PASSWORD)
        other.is_active = True
        other.save()
        mine = self._open_many(active_user, 11, prefix="mine")
        theirs = self._open_many(other, 30, prefix="theirs")

        client.force_authenticate(user=active_user)
        first, second = self._page(client, 1), self._page(client, 2)

        ids = {row["id"] for r in (first, second) for row in r.data["results"]}
        assert ids == {session.pk for session in mine}
        assert ids.isdisjoint({session.pk for session in theirs})
        # The other user's 30 rows must not inflate the page count either.
        assert first.data["pages"] == 2
        assert self._page(client, 3).status_code == 404

    def test_ended_sessions_are_not_listed(self, client, active_user):
        from django.utils import timezone

        sessions = self._open_many(active_user, 12)
        UserSession.objects.filter(pk__in=[sessions[0].pk, sessions[1].pk]).update(
            logout_at=timezone.now()
        )

        client.force_authenticate(user=active_user)
        first = self._page(client, 1)

        assert len(first.data["results"]) == 10
        assert first.data["pages"] == 1
        assert self._page(client, 2).status_code == 404

    def test_page_past_the_end_is_404(self, client, active_user):
        self._open_many(active_user, 10)
        client.force_authenticate(user=active_user)

        assert self._page(client, 1).status_code == 200
        assert self._page(client, 2).status_code == 404
        assert self._page(client, 0).status_code == 404

    def test_no_sessions_is_one_empty_page_not_404(self, client, active_user):
        client.force_authenticate(user=active_user)

        response = self._page(client)

        assert response.status_code == 200
        assert response.data["results"] == []
        assert response.data["pages"] == 1

    def test_limit_is_honoured_and_capped(self, client, active_user):
        self._open_many(active_user, 12)
        client.force_authenticate(user=active_user)

        small = self._page(client, limit=4)
        assert len(small.data["results"]) == 4
        assert small.data["pages"] == 3
        assert len(self._page(client, limit=500).data["results"]) == 12

    def test_requires_authentication(self, client):
        assert self._page(client).status_code == 401

    def test_current_device_is_flagged_wherever_its_page_is(self, client, active_user):
        """
        The current device is not pinned to the first page — the flag is on the
        row, so it is marked on page 2 as well.
        """
        from accounts import services

        token = AccessToken.for_user(active_user)
        current = services.open_session(active_user, session_key=token["jti"])
        UserSession.objects.filter(pk=current.pk).update(login_at=datetime(2025, 1, 1, tzinfo=UTC))
        self._open_many(active_user, 12)

        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        first, second = self._page(client, 1), self._page(client, 2)

        assert not any(row["is_current"] for row in first.data["results"])
        assert [row["id"] for row in second.data["results"] if row["is_current"]] == [current.pk]

    def test_revoking_removes_the_session_from_the_pages(self, client, active_user):
        sessions = self._open_many(active_user, 11)
        client.force_authenticate(user=active_user)
        assert self._page(client).data["pages"] == 2

        response = client.post(reverse("v1:accounts:session-revoke", args=[sessions[0].pk]))
        assert response.status_code == 204

        first = self._page(client, 1)
        assert sessions[0].pk not in [row["id"] for row in first.data["results"]]
        # Ending the only row of the last page removes the page itself: the client
        # has to step back (or restart at page 1), because page 2 is now a 404.
        assert first.data["pages"] == 1
        assert self._page(client, 2).status_code == 404


# ═══════════════════════════════════════════════════════════
#  Language negotiation
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestLanguageNegotiation:
    """
    ⚠️  Uses a real token, not `force_authenticate`.

        The user's preference is applied in the authentication layer, and
        `force_authenticate` bypasses it — testing a path no real request takes.
    """

    @staticmethod
    def _authenticate(client, user):
        from accounts import services

        tokens = services.issue_jwt(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

    def test_header_wins_over_user_preference(self, client, active_user):
        active_user.preferred_language = "ar"
        active_user.save()
        self._authenticate(client, active_user)

        response = client.get(reverse("v1:accounts:me"), HTTP_ACCEPT_LANGUAGE="en")
        assert response.headers["Content-Language"] == "en"

    def test_falls_back_to_user_preference(self, client, active_user):
        active_user.preferred_language = "en"
        active_user.save()
        self._authenticate(client, active_user)

        response = client.get(reverse("v1:accounts:me"))
        assert response.headers["Content-Language"] == "en"

    def test_unsupported_language_falls_back_to_preference(self, client, active_user):
        active_user.preferred_language = "en"
        active_user.save()
        self._authenticate(client, active_user)

        response = client.get(reverse("v1:accounts:me"), HTTP_ACCEPT_LANGUAGE="fr,de")
        assert response.headers["Content-Language"] == "en"

    def test_anonymous_request_uses_default(self, client):
        response = client.post(
            reverse("v1:accounts:password-reset"),
            {"email": "nobody@test.local"},
            format="json",
            HTTP_ACCEPT_LANGUAGE="fr",
        )
        assert response.headers["Content-Language"] == "ar"


# ═══════════════════════════════════════════════════════════
#  Email change — confirmation from both addresses
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestEmailChange:
    def _authenticate(self, client, user):
        client.force_authenticate(user=user)
        return client

    def test_requires_current_password(self, client, active_user):
        """
        ⚠️  An unattended unlocked device is enough to change the email and then
            take over the account through "forgot password".
        """
        self._authenticate(client, active_user)

        response = client.post(
            reverse("v1:accounts:email-change"),
            {"new_email": "new@test.local", "current_password": "WrongPass!123"},
            format="json",
        )

        assert response.status_code == 400
        assert "current_password" in response.data["fields"]

    def test_sends_two_emails_old_and_new(
        self, client, active_user, django_capture_on_commit_callbacks
    ):
        """
        The old address receives a warning · the new one receives a confirmation code.
        Sending to the new one alone allows a silent account takeover.
        """
        django_mail.outbox.clear()
        self._authenticate(client, active_user)

        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(
                reverse("v1:accounts:email-change"),
                {"new_email": "brand-new@test.local", "current_password": PASSWORD},
                format="json",
            )
        assert response.status_code == 200
        assert len(django_mail.outbox) == 2

        recipients = {msg.to[0] for msg in django_mail.outbox}
        assert recipients == {"active@test.local", "brand-new@test.local"}

    def test_email_is_not_changed_before_confirmation(self, client, active_user):
        self._authenticate(client, active_user)
        client.post(
            reverse("v1:accounts:email-change"),
            {"new_email": "pending@test.local", "current_password": PASSWORD},
            format="json",
        )

        active_user.refresh_from_db()
        assert active_user.email == "active@test.local"

    def test_confirmation_applies_change_and_revokes_sessions(self, client, active_user):
        from accounts import services

        services.open_session(active_user, session_key="before-change")
        _, raw = services.issue_token(
            active_user, TokenPurpose.EMAIL_CHANGE, new_email="confirmed@test.local"
        )

        response = client.post(
            reverse("v1:accounts:email-change-confirm"), {"token": raw}, format="json"
        )
        assert response.status_code == 200

        active_user.refresh_from_db()
        assert active_user.email == "confirmed@test.local"
        assert active_user.is_email_verified
        # Email is the identifier — changing it invalidates every session
        assert not UserSession.objects.filter(user=active_user, logout_at__isnull=True).exists()

    def test_cannot_take_an_email_already_registered(self, client, active_user):
        User.objects.create_user(email="taken@test.local", password=PASSWORD)
        self._authenticate(client, active_user)

        response = client.post(
            reverse("v1:accounts:email-change"),
            {"new_email": "taken@test.local", "current_password": PASSWORD},
            format="json",
        )
        assert response.status_code == 400
        assert "new_email" in response.data["fields"]

    def test_race_between_request_and_confirmation_is_caught(self, client, active_user):
        """
        Someone else may register with the email between the request and the
        confirmation — checking at request time alone is not enough.
        """
        from accounts import services

        _, raw = services.issue_token(
            active_user, TokenPurpose.EMAIL_CHANGE, new_email="contested@test.local"
        )
        User.objects.create_user(email="contested@test.local", password=PASSWORD)

        response = client.post(
            reverse("v1:accounts:email-change-confirm"), {"token": raw}, format="json"
        )

        assert response.status_code == 409
        active_user.refresh_from_db()
        assert active_user.email == "active@test.local"
