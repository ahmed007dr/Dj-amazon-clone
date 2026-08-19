"""
Periodic task tests.

⚠️  The jobs run with no human watching at one in the morning.

    Which means failure behaviour matters more than success behaviour: a job
    that takes the rest down disables all maintenance until somebody notices —
    days later, when a customer complains about a product that is "out of stock"
    while it is available.
"""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from ops.management.commands.run_periodic import JOBS


def test_every_job_has_a_group_and_label():
    """The name alone is not enough in a log read months later."""
    for name, (group, label, function) in JOBS.items():
        assert group, name
        assert label, name
        assert callable(function), name


def test_reservations_are_released_before_alerts():
    """
    ⚠️  The order is part of correctness, not an implementation detail.

        An expired reservation is deducted from available; so computing the
        alerts before the release produces "critical stock" for stock that comes
        back a second later — and it is then resolved the next day, so the
        system looks erratic.
    """
    order = list(JOBS)
    assert order.index("release_reservations") < order.index("expiry_alerts")


@pytest.mark.django_db
def test_dry_run_executes_nothing():
    called = []

    def spy():
        called.append(1)
        return 0

    with patch.dict(JOBS, {"abandon_carts": ("cart", "اختبار", spy)}):
        call_command("run_periodic", "--dry-run", stdout=StringIO())

    assert called == []


@pytest.mark.django_db
def test_all_jobs_run_and_report_counts():
    out = StringIO()
    call_command("run_periodic", stdout=out)

    output = out.getvalue()
    for _group, label, _fn in JOBS.values():
        assert label in output


@pytest.mark.django_db
def test_a_failing_job_does_not_stop_the_rest():
    """
    ⚠️  **The most important behaviour.**

        A corrupt batch that blocks quarantining must not block the release of reservations.
    """
    survived = []

    def boom():
        raise RuntimeError("فشل مقصود")

    def survivor():
        survived.append(1)
        return 3

    with patch.dict(
        JOBS,
        {
            "quarantine_batches": ("inventory", "حجر", boom),
            "abandon_carts": ("cart", "سلال", survivor),
        },
    ):
        out, err = StringIO(), StringIO()
        with pytest.raises(SystemExit) as exit_info:
            call_command("run_periodic", stdout=out, stderr=err)

    assert survived == [1], "المهمة التالية لم تُنفَّذ بعد فشل السابقة"
    # ⚠️  A non-zero exit code: the scheduler detects the failure without reading a log
    assert exit_info.value.code == 1


@pytest.mark.django_db
def test_group_selection_runs_only_that_group():
    out = StringIO()
    call_command("run_periodic", "--job", "cart", stdout=out)

    output = out.getvalue()
    assert "السلال" in output or "سلال" in output
    assert "حجر الدفعات المنتهية" not in output


@pytest.mark.django_db
def test_unknown_job_exits_with_a_usable_message():
    """A name mistyped in cron must say what is available rather than staying silent."""
    err = StringIO()
    with pytest.raises(SystemExit) as exit_info:
        call_command("run_periodic", "--job", "nonexistent", stdout=StringIO(), stderr=err)

    assert exit_info.value.code == 2
    assert "release_reservations" in err.getvalue()


def test_outbound_mail_is_scheduled():
    """
    ⚠️  A queue with no schedule turns a temporary failure into a permanent loss.

        Delivery starts on `on_commit` the moment the event occurs; and what
        fails then (a server down · a timeout) is retried by nothing but this
        sweep. And its absence from the schedule breaks not one test in
        `mailing` — the queue works and the messages wait forever.

    ⚠️  And it is scheduled **every few minutes** rather than daily like the
        rest: the first retry comes after a minute, and delaying it a day makes
        the password reset email arrive after its owner has forgotten it.
    """
    from mailing import services as mail_services

    group, label, job = JOBS["send_outbound_mail"]

    assert group == "mail"
    assert label
    assert job is mail_services.deliver_pending


def test_inbound_mail_is_scheduled_after_delivery():
    """
    ⚠️  The order is part of correctness: the inbox fills with replies to what
        we sent. And pulling it before delivering what is waiting makes the
        customer's reply arrive ahead of the message it answers — so the
        employee reads an answer with no question.
    """
    from mailing import inbound as mail_inbound

    names = list(JOBS)

    assert JOBS["fetch_inbound_mail"][2] is mail_inbound.fetch_all
    assert names.index("send_outbound_mail") < names.index("fetch_inbound_mail")
