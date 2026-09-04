"""
Tax settings — `GET`/`PUT /administration/tax/settings/`.

⚠️  **The bug this file exists to pin down**: `default_class` used to be a
    second, independently-writable copy of "the default tax class" stored
    under a `SystemSetting` key, validated against `TaxClass` on every save —
    while `pricing.services` (via `TaxClass.get_default()`) has always read
    the *model's* `is_default` flag instead. The two could drift, and once the
    stored copy pointed at a class that was deactivated or renamed, every save
    of this form failed on a field the settings screen does not even render
    an input for. `default_class` is now read-only here, derived from
    `TaxClass.get_default()` — there is exactly one place a default lives.
"""

from decimal import Decimal

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from administration.models import AdminProfile
from core.models.settings import SystemSetting
from core.models.tax import TaxClass
from core.testing import grant_all_domains

PASSWORD = "Str0ng-Test-Pass!23"


def url():
    return reverse("v1:administration:tax-settings")


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_user(
        email="tax-admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    admin.is_active = True
    admin.save()
    AdminProfile.objects.create(user=admin)
    grant_all_domains(admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture
def default_class(db):
    return TaxClass.objects.create(
        code="standard",
        name_ar="قياسية",
        name_en="Standard",
        rate=Decimal("14.00"),
        is_default=True,
    )


@pytest.mark.django_db
class TestTaxSettings:
    def test_default_class_reflects_the_model_default(self, admin_client, default_class):
        response = admin_client.get(url())

        assert response.status_code == 200
        assert response.data["default_class"] == "standard"

    def test_save_succeeds_when_the_stored_setting_is_stale(self, admin_client, default_class):
        """
        ⚠️  Reproduces the reported `400 VALIDATION_ERROR` on `default_class`
            exactly: a leftover `SystemSetting` pointing at a code that no
            `TaxClass` has, present only because a previous, buggy write path
            (or a hand-edited value) put it there. A save that never reads
            this key cannot be broken by it.
        """
        SystemSetting.set(
            "tax.default_class",
            "a-code-that-does-not-exist",
            value_type="STRING",
            group="TAX",
            label_ar="x",
            label_en="x",
        )

        response = admin_client.put(
            url(),
            {
                "enabled": True,
                "prices_include_tax": False,
                "default_class": "a-code-that-does-not-exist",
                "rounding": "line",
            },
            format="json",
        )

        assert response.status_code == 200, response.data
        assert response.data["default_class"] == "standard"

    def test_default_class_cannot_be_changed_from_this_endpoint(self, admin_client, default_class):
        """
        ⚠️  The only way to change the default is "Make Default" on a tax
            class — sending a different `default_class` here is silently
            ignored, not honoured and not rejected.
        """
        other = TaxClass.objects.create(
            code="zero", name_ar="صفرية", name_en="Zero", rate=Decimal("0.00")
        )

        response = admin_client.put(
            url(),
            {
                "enabled": True,
                "prices_include_tax": False,
                "default_class": other.code,
                "rounding": "line",
            },
            format="json",
        )

        assert response.status_code == 200, response.data
        assert response.data["default_class"] == "standard"

    def test_no_default_class_at_all_does_not_break_the_form(self, admin_client):
        """No `TaxClass` is `is_default` yet — day one, before the seed runs."""
        response = admin_client.put(
            url(),
            {"enabled": True, "prices_include_tax": False, "rounding": "line"},
            format="json",
        )

        assert response.status_code == 200, response.data
        assert response.data["default_class"] == ""
