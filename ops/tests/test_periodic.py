"""
اختبارات المهام الدورية.

⚠️  المهام تعمل بلا مراقب بشري في الثانية صباحًا.

    وهذا يعني أن سلوك الفشل أهم من سلوك النجاح: مهمة تُسقط البقية
    تعطّل الصيانة كلها إلى أن يلاحظ أحد — بعد أيام، حين يشتكي عميل
    من منتج «نافد» وهو متوفر.
"""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command

from ops.management.commands.run_periodic import JOBS


def test_every_job_has_a_group_and_label():
    """الاسم وحده لا يكفي في سجل يُقرأ بعد شهور."""
    for name, (group, label, function) in JOBS.items():
        assert group, name
        assert label, name
        assert callable(function), name


def test_reservations_are_released_before_alerts():
    """
    ⚠️  الترتيب جزء من الصحة لا تفصيل تنفيذي.

        الحجز المنتهي يخصم من المتاح؛ فحساب التنبيهات قبل الإفراج
        ينتج «مخزون حرج» لمخزون سيعود بعد ثانية — ثم يُحسم في
        اليوم التالي، فيبدو النظام مضطربًا.
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
    ⚠️  **السلوك الأهم.**

        دفعة تالفة تمنع الحجر يجب ألا تمنع إفراج الحجوزات.
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
    # ⚠️  رمز خروج غير صفري: الجدولة تكتشف الفشل بلا قراءة سجل
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
    """اسم مكتوب خطأً في cron يجب أن يقول ما المتاح لا أن يصمت."""
    err = StringIO()
    with pytest.raises(SystemExit) as exit_info:
        call_command("run_periodic", "--job", "nonexistent", stdout=StringIO(), stderr=err)

    assert exit_info.value.code == 2
    assert "release_reservations" in err.getvalue()
