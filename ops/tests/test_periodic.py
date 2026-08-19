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


def test_outbound_mail_is_scheduled():
    """
    ⚠️  الطابور بلا جدولة يجعل الفشل المؤقت ضياعًا دائمًا.

        التسليم يبدأ على `on_commit` فور وقوع الحدث؛ وما يفشل حينها
        (خادم متوقف · مهلة) لا يعيده أحد إلا هذا المسح. وغيابه من
        الجدول لا يكسر اختبارًا واحدًا في `mailing` — الطابور يعمل
        والرسائل تنتظر إلى الأبد.

    ⚠️  ويُجدوَل **كل بضع دقائق** لا يوميًا كبقية المهام: أول إعادة
        محاولة بعد دقيقة، وتأخيرها يومًا يجعل بريد إعادة تعيين كلمة
        المرور يصل بعد أن ينساه صاحبه.
    """
    from mailing import services as mail_services

    group, label, job = JOBS["send_outbound_mail"]

    assert group == "mail"
    assert label
    assert job is mail_services.deliver_pending


def test_inbound_mail_is_scheduled_after_delivery():
    """
    ⚠️  الترتيب جزء من الصحة: الصندوق الوارد يمتلئ بردود على ما
        أرسلناه. وسحبه قبل تسليم ما ينتظر يجعل ردّ العميل يصل قبل
        الرسالة التي يردّ عليها — فيقرأ الموظف جوابًا بلا سؤال.
    """
    from mailing import inbound as mail_inbound

    names = list(JOBS)

    assert JOBS["fetch_inbound_mail"][2] is mail_inbound.fetch_all
    assert names.index("send_outbound_mail") < names.index("fetch_inbound_mail")
