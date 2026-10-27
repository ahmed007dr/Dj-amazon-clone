"""
The audit-log list can answer "what happened to THIS object?".

⚠️  A bare `object_id` would be ambiguous — ids are only unique within a model — so
    the object filter is always `model` + `object_id`.
"""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from administration.models import AdminProfile
from core.models.audit import AuditAction, AuditLog
from core.testing import grant_all_domains

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin():
    user = User.objects.create_user(
        email="audit-admin@test.local", password=PASSWORD, first_name="Mona", last_name="Admin"
    )
    user.is_active = True
    user.save()
    AdminProfile.objects.create(user=user)
    grant_all_domains(user)
    return user


@pytest.fixture
def client(admin):
    api = APIClient()
    api.force_authenticate(user=admin)
    return api


def entry(actor, model_label, object_id, action=AuditAction.UPDATE, repr_="x"):
    app_label, model = model_label.split(".")
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        content_type=ContentType.objects.get(app_label=app_label, model=model),
        object_id=object_id,
        object_repr=repr_,
    )


def listing(client, **params):
    return client.get(reverse("v1:administration:audit-log"), params).json()


def test_filters_by_model_and_object_id(client, admin):
    entry(admin, "catalog.product", "P-1", repr_="mine")
    entry(admin, "catalog.product", "P-2", repr_="other product")
    # Same id on a different model must not match.
    entry(admin, "accounts.user", "P-1", repr_="other model")

    rows = listing(client, model="catalog.product", object_id="P-1")["results"]

    assert [row["object_repr"] for row in rows] == ["mine"]


def test_model_alone_lists_every_object_of_that_model(client, admin):
    entry(admin, "catalog.product", "P-1")
    entry(admin, "catalog.product", "P-2")
    entry(admin, "accounts.user", "U-1")

    assert listing(client, model="catalog.product")["count"] == 2


def test_object_id_without_a_model_is_ignored_not_ambiguous(client, admin):
    entry(admin, "catalog.product", "P-1")
    entry(admin, "accounts.user", "P-1")

    assert listing(client, object_id="P-1")["count"] == 2


def test_rows_carry_readable_actor_and_model(client, admin):
    entry(admin, "catalog.product", "P-1", action=AuditAction.PRICE_CHANGE)

    row = listing(client, model="catalog.product")["results"][0]

    assert row["actor_email"] == "audit-admin@test.local"
    assert row["actor_name"] == "Mona Admin"
    assert row["model"] == "catalog.product"
    assert row["object_id"] == "P-1"
    assert row["action"] == "PRICE_CHANGE"
    assert row["action_label"]


def test_rows_without_an_object_still_serialise(client, admin):
    AuditLog.objects.create(actor=None, action=AuditAction.LOGIN, object_repr="system")

    row = listing(client)["results"][0]

    assert row["model"] is None
    assert row["actor_email"] is None


def test_malformed_actor_filter_is_empty_not_500(client):
    response = client.get(reverse("v1:administration:audit-log"), {"actor": "not-a-uuid"})

    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_list_does_not_query_per_row(client, admin, django_assert_max_num_queries):
    for index in range(10):
        entry(admin, "catalog.product", f"P-{index}")

    with django_assert_max_num_queries(7):
        response = client.get(reverse("v1:administration:audit-log"))

    assert response.status_code == 200
