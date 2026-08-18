"""
اختبارات طابور الصادر.

⚠️  **العطلان اللذان وُجد الطابور لأجلهما، وكلاهما كان صامتًا:**

    ١. الإرسال داخل المعاملة قبل إيداعها — معاملة تُلغى بعد الإرسال
       تعني عميلًا يتلقّى «استلمنا طلبك» لطلب غير موجود.

    ٢. `fail_silently=True` بلا إعادة محاولة — خادم متوقف ثانيتين
       يعني طلب إعادة تعيين كلمة مرور يُفقد نهائيًا، ويرى المستخدم
       شاشة تقول «أرسلنا لك رسالة».
"""

from datetime import timedelta

import pytest
from django.core import mail as django_mail
from django.db import transaction
from django.utils import timezone

from mailing import services
from mailing.models import (
    BACKOFF_MINUTES,
    MAX_ATTEMPTS,
    DeliveryState,
    EmailAccount,
    MailTransport,
    OutboundMessage,
)

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


@pytest.fixture
def console_account(db, monkeypatch):
    monkeypatch.setattr(services, "CONSOLE_BACKEND", LOCMEM)
    return EmailAccount.objects.create(
        code="system",
        label_ar="النظام",
        label_en="System",
        transport=MailTransport.CONSOLE,
        from_email="noreply@example.com",
        is_default=True,
    )


@pytest.fixture
def dead_account(db):
    """خادم لا يستجيب — منفذ مغلق ومهلة ثانية واحدة."""
    return EmailAccount.objects.create(
        code="dead",
        label_ar="معطّل",
        label_en="Dead",
        host="127.0.0.1",
        port=1,
        timeout=1,
        from_email="noreply@example.com",
        is_default=True,
    )


def queue(template_key="password_changed", **overrides):
    payload = {
        "to": "customer@example.com",
        "language": "ar",
        "context": {"name": "أحمد"},
    }
    payload.update(overrides)
    return services.enqueue(template_key, **payload)


@pytest.mark.django_db
class TestSnapshot:
    def test_body_is_rendered_at_enqueue_not_at_delivery(self, console_account):
        """
        ⚠️  النص لقطة لا مرجع: التصيير المؤجَّل يقرأ قالبًا قد يكون
            الأدمن حرّره في الأثناء، وسياقًا قد تغيّر — «إجمالي طلبك
            ٤٥٠» تصير رقمًا آخر بعد مرتجع.
        """
        message = queue(
            "order_placed",
            context={"name": "أحمد", "number": "ORD-1", "total": "450.00", "link": "x"},
        )

        assert "ORD-1" in message.subject
        assert "450.00" in message.body
        assert message.status == DeliveryState.PENDING


@pytest.mark.django_db
class TestCommitBoundary:
    """
    ⚠️  بلا `transaction=True`.

        الاختبار التبادلي يقطع الجداول عند تفكيكه، وهو مع اتصالات
        الخيوط المعلّقة في اختبارات التزامن الأخرى يجعل الحزمة تفشل
        فشلًا متنقّلًا لا علاقة له بما تختبره. ونقطة الإيداع تُقاس
        بلا ذلك: المُستدعَيات المسجَّلة داخل كتلة مُلغاة **تُسقَط**،
        وهو بالضبط ما يعني «لم يُرسَل شيء».
    """

    def test_rollback_leaves_no_message_and_schedules_no_delivery(
        self, console_account, django_capture_on_commit_callbacks
    ):
        """
        ⚠️  العطل الأول حرفيًا: الصفّ يُكتب داخل المعاملة فيُلغى معها،
            والتسليم مجدوَل على `on_commit` فلا يقع أصلًا.

            قبل ذلك كان البريد يخرج **قبل** الإيداع: معاملة تُلغى
            بعده تعني عميلًا يتلقّى «استلمنا طلبك ORD-…» لطلب غير
            موجود في قاعدة البيانات.
        """
        django_mail.outbox.clear()

        with django_capture_on_commit_callbacks() as callbacks:
            with pytest.raises(RuntimeError), transaction.atomic():
                queue()
                raise RuntimeError("العملية فشلت بعد تقييد البريد")

        assert OutboundMessage.objects.count() == 0
        assert callbacks == []
        assert django_mail.outbox == []

    def test_delivery_is_scheduled_only_after_commit(
        self, console_account, django_capture_on_commit_callbacks
    ):
        django_mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            with transaction.atomic():
                message = queue()
            assert django_mail.outbox == []  # قُيِّد ولم يُسلَّم بعد

        message.refresh_from_db()
        assert message.status == DeliveryState.SENT
        assert message.sent_at is not None
        assert len(django_mail.outbox) == 1


@pytest.mark.django_db
class TestRetry:
    def test_failure_keeps_the_message_and_backs_off(self, dead_account):
        """
        ⚠️  العطل الثاني: الفشل المؤقت كان يعني رسالة ضائعة إلى الأبد.
            الصفّ يبقى، ويُعاد بتراجع تدريجي لا فورًا — الخادم الذي
            رفض لحدّ معدّل يرفض الإلحاح أيضًا.
        """
        message = queue()
        before = timezone.now()

        assert services.deliver(message.pk) is False

        message.refresh_from_db()
        assert message.status == DeliveryState.PENDING
        assert message.attempts == 1
        assert message.last_error
        assert message.next_attempt_at >= before + timedelta(minutes=BACKOFF_MINUTES[0])

    def test_backoff_grows_with_each_attempt(self, dead_account):
        message = queue()

        delays = []
        for _ in range(3):
            OutboundMessage.objects.filter(pk=message.pk).update(next_attempt_at=timezone.now())
            started = timezone.now()
            services.deliver(message.pk)
            message.refresh_from_db()
            delays.append(round((message.next_attempt_at - started).total_seconds() / 60))

        assert delays == sorted(delays)
        assert delays[0] < delays[-1]

    def test_exhausted_attempts_become_a_declared_failure(self, dead_account):
        """
        ⚠️  الصفّ الذي يُعاد بلا حدّ يخفي عطلًا دائمًا (عنوان خاطئ ·
            صندوق ممتلئ) وسط ضجيج المحاولات، فلا يعرف أحد أن الرسالة
            لن تصل أبدًا. `FAILED` تجعلها سطرًا يُقرأ ويُعالَج.
        """
        message = queue()

        for _ in range(MAX_ATTEMPTS):
            OutboundMessage.objects.filter(pk=message.pk).update(next_attempt_at=timezone.now())
            services.deliver(message.pk)

        message.refresh_from_db()
        assert message.status == DeliveryState.FAILED
        assert message.attempts == MAX_ATTEMPTS

    def test_failed_message_is_not_picked_up_again(self, dead_account):
        message = queue()
        OutboundMessage.objects.filter(pk=message.pk).update(
            status=DeliveryState.FAILED, next_attempt_at=timezone.now()
        )

        assert services.deliver_pending() == 0

    def test_manual_retry_keeps_the_attempt_history(self, dead_account):
        """
        ⚠️  الإعادة اليدوية تصفّر التراجع لا العدّاد: تصفيره يجعل
            رسالة فشلت عشرين مرة تبدو كأنها في محاولتها الأولى.
        """
        message = queue()
        OutboundMessage.objects.filter(pk=message.pk).update(
            status=DeliveryState.FAILED, attempts=3, next_attempt_at=timezone.now()
        )
        message.refresh_from_db()

        services.retry(message)

        message.refresh_from_db()
        assert message.attempts >= 4

    def test_manual_retry_delivers_once_the_fault_is_fixed(self, console_account):
        """
        ⚠️  الحالة الفعلية بعد العطل: المشغّل يصلح الإعداد ثم يعيد
            المحاولة من الشاشة. الصفّ الذي أُعلن فشله يجب أن يقبل
            الإعادة — وإلا صار الإعلان حكمًا نهائيًا على رسالة صالحة.
        """
        django_mail.outbox.clear()
        message = queue()
        OutboundMessage.objects.filter(pk=message.pk).update(
            status=DeliveryState.FAILED, attempts=MAX_ATTEMPTS
        )
        message.refresh_from_db()

        assert services.retry(message) is True

        message.refresh_from_db()
        assert message.status == DeliveryState.SENT
        assert len(django_mail.outbox) == 1


@pytest.mark.django_db
class TestClaiming:
    def test_a_message_is_never_delivered_twice(self, console_account):
        """
        ⚠️  عاملان يقرآن نفس الصفّ فيرسلانه مرتين: العميل يتلقّى
            رسالتين متطابقتين. الحجز شرطٌ ذرّي — من يعيد `1` يملكه.
        """
        django_mail.outbox.clear()
        message = queue()

        assert services.deliver(message.pk) is True
        assert services.deliver(message.pk) is False  # لا مالك ثانٍ

        assert len(django_mail.outbox) == 1

    def test_a_claim_expires_so_a_crash_does_not_swallow_the_message(self, console_account):
        """
        ⚠️  العملية التي تسقط بين الحجز والإرسال كانت تترك الصفّ
            محجوزًا إلى الأبد — رسالة تضيع بلا فشل ظاهر، وهو أسوأ من
            فشل معلن. الحجز يمتدّ ثم يسقط فتلتقطها المهمة الدورية.
        """
        django_mail.outbox.clear()
        message = queue()
        OutboundMessage.objects.filter(pk=message.pk).update(
            status=DeliveryState.SENDING,
            next_attempt_at=timezone.now() - timedelta(minutes=1),
        )

        assert services.deliver_pending() == 1
        assert len(django_mail.outbox) == 1

    def test_a_live_claim_is_left_alone(self, console_account):
        """حجز حيّ لعامل آخر لا يُنتزع — وإلا عاد الازدواج من الباب الآخر."""
        message = queue()
        OutboundMessage.objects.filter(pk=message.pk).update(
            status=DeliveryState.SENDING,
            next_attempt_at=timezone.now() + timedelta(minutes=10),
        )

        assert services.deliver_pending() == 0

    def test_pending_before_its_time_is_not_picked_up(self, console_account):
        message = queue()
        OutboundMessage.objects.filter(pk=message.pk).update(
            next_attempt_at=timezone.now() + timedelta(minutes=5)
        )

        assert services.deliver_pending() == 0


@pytest.mark.django_db
class TestPeriodicSweep:
    def test_the_sweep_delivers_what_is_due(self, console_account):
        """
        ⚠️  شبكة أمان لا مسار رئيسي: التسليم يبدأ على `on_commit`،
            وهذا المسح يلتقط ما فشل وما عَلِق.

        ⚠️  وجدولته في `ops` تُختبَر **هناك** لا هنا: استيراد أمر
            التشغيل من اختبار `mailing` كان يجرّ معه كل نطاقات العمل
            (`accounts` · `cart` · `inventory` · `loyalty`) ويكسر
            عقد استقلال النطاق — أمسكه `import-linter` فعلًا.
        """
        django_mail.outbox.clear()
        queue()
        OutboundMessage.objects.update(next_attempt_at=timezone.now())

        assert services.deliver_pending() == 1
        assert len(django_mail.outbox) == 1
