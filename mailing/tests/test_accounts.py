"""
اختبارات حسابات البريد.

⚠️  **السؤال الذي تجيب عنه: من أي حساب خرجت هذه الرسالة؟**

    خطأ الإسناد لا يظهر في أي سجل خطأ: الرسالة تُرسَل وتصل، لكنها
    تخرج من حساب التسويق فتقع في «غير المرغوب» — أو تخرج رسالة
    تسويقية من حساب الأمان فتُدرِجه في القوائم السوداء. الأثر يظهر
    بعد أسابيع في معدّل وصول منخفض لا في استثناء.
"""

from email.header import decode_header, make_header
from email.utils import parseaddr

import pytest
from django.core import mail as django_mail
from django.core.exceptions import ValidationError
from django.db import connection

from core import encryption
from mailing import services
from mailing.models import (
    CredentialKey,
    EmailAccount,
    EmailCredential,
    MailDirection,
    MailSecurity,
    MailTransport,
)

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


def make_account(**overrides) -> EmailAccount:
    fields = {
        "code": "primary",
        "label_ar": "الحساب الأساسي",
        "label_en": "Primary",
        "transport": MailTransport.SMTP,
        "host": "smtp.example.com",
        "port": 587,
        "security": MailSecurity.TLS,
        "username": "postmaster@example.com",
        "from_email": "noreply@example.com",
        "from_name_ar": "المتجر الطبي",
        "is_active": True,
    }
    fields.update(overrides)
    return EmailAccount.objects.create(**fields)


@pytest.mark.django_db
class TestResolution:
    def test_no_account_falls_back_to_environment(self):
        """
        ⚠️  الطبقة الثالثة ليست ترفًا: تركيب جديد بقاعدة بيانات فارغة
            لا حساب فيه، وتفعيل أول أدمن يحتاج بريد تفعيل. `None`
            تعني «استعمل إعداد `.env`».
        """
        assert services.resolve_account() is None
        assert services.connection_for(None) is None

    def test_default_beats_priority(self):
        make_account(code="high", priority=100)
        default = make_account(code="default", is_default=True, priority=0)

        assert services.resolve_account() == default

    def test_highest_priority_when_no_default(self):
        make_account(code="low", priority=1)
        high = make_account(code="high", priority=50)

        assert services.resolve_account() == high

    def test_inactive_account_is_never_chosen(self):
        make_account(code="off", is_active=False, is_default=True)

        assert services.resolve_account() is None

    def test_inbound_only_account_does_not_send(self):
        """حساب استقبال ليس حساب إرسال — والخلط يُخرج البريد من صندوق الدعم."""
        make_account(
            code="support",
            direction=MailDirection.INBOUND,
            imap_host="imap.example.com",
            is_default=True,
        )

        assert services.resolve_account() is None


@pytest.mark.django_db
class TestConnection:
    def test_smtp_settings_come_from_the_row_not_from_settings(self):
        """
        ⚠️  `settings.EMAIL_*` لا تُعدَّل وقت التشغيل: الحساب يُختار
            لكل رسالة، وتعديل إعداد عالمي كان يجعل رسالتين متزامنتين
            تتبادلان الحسابين تحت الحِمل.
        """
        account = make_account(security=MailSecurity.SSL, port=465, timeout=7)
        EmailCredential.objects.create(
            account=account, key=CredentialKey.PASSWORD, value="s3cret-pass"
        )

        conn = services.connection_for(account)

        assert conn.host == "smtp.example.com"
        assert conn.port == 465
        assert conn.username == "postmaster@example.com"
        assert conn.password == "s3cret-pass"
        assert conn.use_ssl is True
        assert conn.use_tls is False
        assert conn.timeout == 7

    def test_console_transport_never_reaches_a_server(self):
        """
        `CONSOLE` مفتاح إيقاف يُبقي الإعداد: الحساب يبقى مضبوطًا
        ويظهر الأثر في السجل بدل أن يختفي بحذف الصف.
        """
        account = make_account(transport=MailTransport.CONSOLE)

        assert "console" in services.connection_for(account).__class__.__module__


@pytest.mark.django_db
class TestCredentials:
    def test_value_is_encrypted_at_rest(self):
        """
        ⚠️  حجب القيمة عن الـ API وحده يحمي مسارًا ويترك الآخر
            مفتوحًا: نسخة احتياطية أو تسريب SQL يعطي كلمة مرور صندوق
            البريد — وهو مفتاح إعادة تعيين كل كلمة مرور أخرى للشركة.
        """
        account = make_account()
        credential = EmailCredential.objects.create(
            account=account, key=CredentialKey.PASSWORD, value="plain-text-password"
        )

        table = EmailCredential._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT value FROM {table} WHERE id = %s", [credential.pk])  # noqa: S608
            stored = cursor.fetchone()[0]

        assert stored.startswith(encryption.PREFIX)
        assert "plain-text-password" not in stored
        # ويُقرأ صريحًا عبر الموديل — التشفير شفاف للكود
        assert EmailCredential.objects.get(pk=credential.pk).value == "plain-text-password"

    def test_masked_value_is_the_only_display(self):
        account = make_account()
        credential = EmailCredential.objects.create(
            account=account, key=CredentialKey.PASSWORD, value="abcdefghij"
        )

        assert credential.masked_value.endswith("ghij")
        assert "abcdef" not in credential.masked_value

    def test_missing_credential_reads_as_empty_not_error(self):
        """
        ⚠️  حساب بلا كلمة مرور يفشل عند الاتصال برسالة مفهومة — لا
            عند القراءة باستثناء يُسقط شاشة الحسابات كلها.
        """
        assert make_account().password == ""


@pytest.mark.django_db
class TestValidation:
    def test_default_account_may_not_be_marketing(self):
        """
        ⚠️  الافتراضي نهاية كل مسار لم يُسنَد صراحةً — ورسائل الأمان
            تقع فيه. حساب تسويقي افتراضي يلتفّ على السياج كله من
            الباب الخلفي.
        """
        account = EmailAccount(
            code="promo",
            label_ar="التسويق",
            label_en="Marketing",
            host="smtp.example.com",
            from_email="promo@example.com",
            is_marketing=True,
            is_default=True,
        )

        with pytest.raises(ValidationError) as exc:
            account.full_clean()

        assert "is_marketing" in exc.value.error_dict

    def test_smtp_sender_requires_a_host(self):
        account = EmailAccount(
            code="broken", label_ar="ناقص", label_en="Broken", from_email="a@example.com"
        )

        with pytest.raises(ValidationError) as exc:
            account.full_clean()

        assert "host" in exc.value.error_dict

    def test_inbound_account_requires_an_imap_host(self):
        account = EmailAccount(
            code="support",
            label_ar="الدعم",
            label_en="Support",
            direction=MailDirection.INBOUND,
            from_email="support@example.com",
        )

        with pytest.raises(ValidationError) as exc:
            account.full_clean()

        assert "imap_host" in exc.value.error_dict

    def test_only_one_default_account(self):
        """«ما الحساب الافتراضي؟» سؤال بجواب واحد — يفرضه قيد لا شاشة."""
        from django.db.utils import IntegrityError

        make_account(code="first", is_default=True)

        with pytest.raises(IntegrityError):
            make_account(code="second", is_default=True)


@pytest.mark.django_db
class TestSending:
    def _console_as_locmem(self, monkeypatch):
        """
        ⚠️  بديل الطرفية بذاكرة قابلة للفحص — المسار المُختبَر يبقى
            كاملًا: التقييد ← الحجز ← الحلّ ← بناء الاتصال ← التسليم.
        """
        monkeypatch.setattr(services, "CONSOLE_BACKEND", LOCMEM)

    def test_message_carries_the_account_identity(
        self, monkeypatch, django_capture_on_commit_callbacks
    ):
        self._console_as_locmem(monkeypatch)
        make_account(
            transport=MailTransport.CONSOLE,
            is_default=True,
            from_email="orders@example.com",
            from_name_ar="متجر الطلبات",
            reply_to="support@example.com",
        )
        django_mail.outbox.clear()

        with django_capture_on_commit_callbacks(execute=True):
            assert services.send_mail(
                "password_reset",
                to="customer@example.com",
                language="ar",
                context={"name": "أحمد", "link": "https://example.com/reset"},
            )

        message = django_mail.outbox[0]

        # ⚠️  الاسم غير اللاتيني يُرمَّز في الترويسة (RFC 2047) —
        #     و`formataddr` هو ما يفعل ذلك ويقتبس الفواصل أيضًا.
        #     التركيب اليدوي `f"{name} <{email}>"` كان يمرّر اسمًا
        #     فيه فاصلة كأنه **مستلمان**.
        name, address = parseaddr(message.from_email)
        assert address == "orders@example.com"
        assert str(make_header(decode_header(name))) == "متجر الطلبات"

        # ⚠️  المرسل `noreply@` غالبًا، وردّ العميل عليه يذهب إلى العدم
        #     وهو يظنّ أنه راسل خدمة العملاء.
        assert message.reply_to == ["support@example.com"]

    def test_success_resets_the_failure_counter(
        self, monkeypatch, django_capture_on_commit_callbacks
    ):
        self._console_as_locmem(monkeypatch)
        account = make_account(
            transport=MailTransport.CONSOLE, is_default=True, consecutive_failures=4
        )

        with django_capture_on_commit_callbacks(execute=True):
            services.send_mail(
                "password_changed", to="c@example.com", language="ar", context={"name": "أحمد"}
            )

        account.refresh_from_db()
        assert account.consecutive_failures == 0
        assert account.last_success_at is not None

    def test_unknown_template_raises_instead_of_queueing_nothing(self):
        """
        ⚠️  الخطأ هنا **يُرفع** خلافًا لفشل التسليم.

            القالب المجهول خطأ برمجي يقع لحظة النداء ويُصلَح بتعديل
            كود؛ ابتلاعه يجعل ميزةً كاملة صامتة في الإنتاج. أما فشل
            SMTP فحدث تشغيلي يُعاد ولا يُفشل عملية تجارية.
        """
        with pytest.raises(KeyError):
            services.send_mail("no_such_template", to="c@example.com", language="ar", context={})
