"""
Responsibility tests — which account each mail goes out from.

⚠️  **The fault these tests guard is entirely silent.**

    The message is sent and it arrives, but it goes out from the wrong account:
    a security message from a blacklisted marketing account lands in "junk", so
    the customer sees "the reset email never arrived" and the system sees a
    successful send. No exception and no line in a log — and the difference
    shows up weeks later in a delivery rate.
"""

import pytest

from mailing import services
from mailing.models import EmailAccount, MailRoute, MailTransport
from mailing.purposes import MailPurpose


def account(code: str, **overrides) -> EmailAccount:
    fields = {
        "code": code,
        "label_ar": code,
        "label_en": code,
        "transport": MailTransport.CONSOLE,
        "from_email": f"{code}@example.com",
    }
    fields.update(overrides)
    return EmailAccount.objects.create(**fields)


@pytest.mark.django_db
class TestResolutionOrder:
    def test_template_route_beats_purpose_route(self):
        general = account("orders-general")
        specific = account("cancellations")
        MailRoute.objects.create(purpose=MailPurpose.ORDERS, account=general)
        MailRoute.objects.create(
            purpose=MailPurpose.ORDERS, template_key="order_cancelled", account=specific
        )

        assert services.resolve_account(template_key="order_cancelled") == specific
        assert services.resolve_account(template_key="order_placed") == general

    def test_purpose_route_beats_default(self):
        account("fallback", is_default=True)
        orders = account("orders")
        MailRoute.objects.create(purpose=MailPurpose.ORDERS, account=orders)

        assert services.resolve_account(template_key="order_placed") == orders

    def test_default_catches_what_no_route_covers(self):
        """
        ⚠️  The mandatory terminus: without falling back to the default, a
            template added tomorrow is not sent — not with an error but silently.
        """
        fallback = account("fallback", is_default=True)

        assert services.resolve_account(template_key="payment_received") == fallback

    def test_inactive_route_is_ignored(self):
        fallback = account("fallback", is_default=True)
        MailRoute.objects.create(
            purpose=MailPurpose.ORDERS, account=account("paused"), is_active=False
        )

        assert services.resolve_account(template_key="order_placed") == fallback

    def test_route_to_a_disabled_account_falls_through(self):
        """
        ⚠️  An assignment to a disabled account does not drop the mail.

            Disabling an account for maintenance would have stopped everything
            assigned to it with no notice, while the default is present and
            capable. An assignment is an intention, not an obligation.
        """
        fallback = account("fallback", is_default=True)
        MailRoute.objects.create(
            purpose=MailPurpose.ORDERS, account=account("off", is_active=False)
        )

        assert services.resolve_account(template_key="order_placed") == fallback

    def test_purpose_comes_from_the_template_not_the_caller(self):
        """
        ⚠️  A call passing a purpose contradicting its template's used to send
            "password reset" from the marketing account. The template declares
            its purpose, and it is the source.
        """
        marketing_target = account("promo-target")
        MailRoute.objects.create(purpose=MailPurpose.MARKETING, account=marketing_target)
        security = account("security", is_default=True)

        resolved = services.resolve_account(
            purpose=MailPurpose.MARKETING, template_key="password_reset"
        )

        assert resolved == security


@pytest.mark.django_db
class TestSecurityFence:
    def test_route_of_security_mail_to_marketing_is_rejected(self):
        """
        ⚠️  The firewall the domain exists for (ADR-76): the marketing account
            gets blacklisted by its very nature, and assigning "password reset"
            to it locks users out of their accounts as punishment for a
            marketing campaign.
        """
        from django.core.exceptions import ValidationError

        route = MailRoute(purpose=MailPurpose.ACCOUNT, account=account("promo", is_marketing=True))

        with pytest.raises(ValidationError) as exc:
            route.full_clean()

        assert "account" in exc.value.error_dict

    def test_fence_holds_even_for_a_row_written_before_the_rule(self):
        """
        ⚠️  The firewall is applied twice deliberately: `clean()` guards what is
            written, and the resolver guards what is read.

            An account that becomes a marketing one **after** being assigned
            passes the first and does not pass the second — which is exactly
            what write-time validation cannot catch.
        """
        promo = account("promo")
        MailRoute.objects.create(purpose=MailPurpose.ACCOUNT, account=promo)
        safe = account("safe", is_default=True)

        # A later change — bypassing validation
        EmailAccount.objects.filter(pk=promo.pk).update(is_marketing=True)

        assert services.resolve_account(template_key="password_reset") == safe

    def test_marketing_still_serves_marketing(self):
        """The firewall protects security without disabling marketing."""
        promo = account("promo", is_marketing=True)
        MailRoute.objects.create(purpose=MailPurpose.MARKETING, account=promo)

        assert services.resolve_account(purpose=MailPurpose.MARKETING) == promo

    def test_marketing_account_is_never_the_last_resort_for_security(self):
        """
        ⚠️  If the only available account were a marketing one, the answer is
            **no account**, not "this is the best there is": falling back to
            `.env` or the console leaves a visible trace in the log, whereas
            sending from a burnt account leaves a silent one.
        """
        account("only-promo", is_marketing=True)

        assert services.resolve_account(template_key="verify_email") is None


@pytest.mark.django_db
class TestRoutingMap:
    def test_source_distinguishes_assigned_from_fallen_through(self):
        """
        ⚠️  A screen showing "Orders ← the primary account" leaves the operator
            believing they assigned it when it is a fallback to the default — so
            if they change the default, messages they thought were pinned move with it.
        """
        account("fallback", is_default=True)
        orders = account("orders")
        MailRoute.objects.create(purpose=MailPurpose.ORDERS, account=orders)
        MailRoute.objects.create(
            purpose=MailPurpose.ORDERS, template_key="order_placed", account=account("placed")
        )

        rows = {row["template_key"]: row for row in services.routing_map()}

        assert rows["order_placed"]["source"] == services.SOURCE_TEMPLATE
        assert rows["order_confirmed"]["source"] == services.SOURCE_PURPOSE
        assert rows["password_reset"]["source"] == services.SOURCE_DEFAULT

    def test_every_template_appears(self):
        """A template absent from the map is a setting the operator does not know they have."""
        from mailing.templates import TEMPLATES

        assert {row["template_key"] for row in services.routing_map()} == set(TEMPLATES)

    def test_no_account_at_all_reports_the_environment_layer(self):
        rows = services.routing_map()

        assert {row["source"] for row in rows} == {services.SOURCE_ENV}
