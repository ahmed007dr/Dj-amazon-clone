"""
اختبارات واجهات البريد.

⚠️  **الخاصية المحروسة هنا واحدة قبل كل شيء: السرّ لا يخرج.**

    إعداد البريد يُدار من شاشة، والشاشة تقرأ من الـ API. وأي حقل
    يعيد كلمة المرور — ولو «مقنّعة جزئيًا» — يضعها في سجل المتصفح
    وفي كاش الوكيل وفي أي أداة تصحيح مفتوحة. القناع الحقيقي أن تكون
    القيمة غير موجودة في الحمولة أصلًا.
"""

import pytest
from django.apps import apps
from django.urls import reverse
from rest_framework.test import APIClient

from mailing.models import CredentialKey, EmailAccount, EmailCredential, MailTransport

PASSWORD = "Str0ng-Test-Pass!23"
SMTP_SECRET = "sup3r-secret-smtp-key"


def _model(label: str, name: str):
    """⚠️  `apps.get_model` لا `import` — `mailing` ممنوع من استيراد نطاق عمل."""
    return apps.get_model(label, name)


@pytest.fixture
def admin_client(db):
    user_model = _model("accounts", "User")
    admin = user_model.objects.create_user(
        email="mail-admin@test.local", password=PASSWORD, account_type="ADMIN"
    )
    admin.is_active = True
    admin.save()
    _model("administration", "AdminProfile").objects.create(user=admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


@pytest.fixture
def account(db):
    account = EmailAccount.objects.create(
        code="primary",
        label_ar="الأساسي",
        label_en="Primary",
        host="smtp.example.com",
        from_email="noreply@example.com",
    )
    EmailCredential.objects.create(account=account, key=CredentialKey.PASSWORD, value=SMTP_SECRET)
    return account


@pytest.mark.django_db
class TestSecretsNeverLeave:
    def test_list_carries_no_secret(self, admin_client, account):
        response = admin_client.get(reverse("v1:mailing:accounts"))

        assert response.status_code == 200
        assert SMTP_SECRET not in response.content.decode()
        assert response.data[0]["has_password"] is True
        assert "password" not in response.data[0]

    def test_detail_carries_no_secret(self, admin_client, account):
        url = reverse("v1:mailing:account-detail", args=[account.pk])

        response = admin_client.get(url)

        assert response.status_code == 200
        assert SMTP_SECRET not in response.content.decode()

    def test_write_then_read_back_never_returns_it(self, admin_client, account):
        """الكتابة تنجح، والقراءة بعدها لا تعيد ما كُتب."""
        url = reverse("v1:mailing:account-detail", args=[account.pk])

        response = admin_client.patch(url, {"password": "brand-new-password"}, format="json")

        assert response.status_code == 200
        assert "brand-new-password" not in response.content.decode()
        assert account.credentials.get(key=CredentialKey.PASSWORD).value == "brand-new-password"

    def test_audit_log_records_field_names_not_values(self, admin_client, account):
        """
        ⚠️  سجل التدقيق أطول عمرًا من الصف الذي أخفينا السرّ فيه —
            وكتابة الحمولة فيه تُبقي كلمة المرور صريحة إلى الأبد.
        """
        url = reverse("v1:mailing:account-detail", args=[account.pk])
        admin_client.patch(url, {"password": "another-secret"}, format="json")

        log = (
            _model("core", "AuditLog").objects.filter(object_repr__contains="primary").latest("id")
        )

        assert "another-secret" not in str(log.changes)
        assert log.changes == {"fields": ["password"]}


@pytest.mark.django_db
class TestSecretPreservation:
    def test_blank_password_keeps_the_current_one(self, admin_client, account):
        """
        ⚠️  الشاشة تُقدَّم بحقل فارغ دائمًا لأن القيمة لا تُقرأ. فحفظ
            تعديل على المنفذ وحده كان سيمسح كلمة المرور بلا أن يقصد
            أحد — ويوقف البريد كله بتعديل يبدو بريئًا.
        """
        url = reverse("v1:mailing:account-detail", args=[account.pk])

        response = admin_client.patch(url, {"port": 2525, "password": ""}, format="json")

        assert response.status_code == 200
        assert account.credentials.get(key=CredentialKey.PASSWORD).value == SMTP_SECRET


@pytest.mark.django_db
class TestAccess:
    def test_anonymous_is_rejected(self, account):
        response = APIClient().get(reverse("v1:mailing:accounts"))

        assert response.status_code in (401, 403)

    def test_customer_is_rejected(self, db, account):
        """
        ⚠️  إعداد البريد داخلي بالكامل: أسماء الخوادم والمستخدمين
            تكشف بنية تحتية وتدلّ مهاجمًا على أين يجرّب كلمات المرور.
        """
        user_model = _model("accounts", "User")
        customer = user_model.objects.create_user(
            email="customer@test.local", password=PASSWORD, account_type="CUSTOMER"
        )
        customer.is_active = True
        customer.save()

        client = APIClient()
        client.force_authenticate(user=customer)

        assert client.get(reverse("v1:mailing:accounts")).status_code == 403


@pytest.mark.django_db
class TestVerification:
    def test_verify_reports_failure_without_raising(self, admin_client, db):
        """
        ⚠️  خادم لا يستجيب يجب أن يعطي «فشل ورسالته» لا 500.

            الشاشة التي تعرض خطأ خادم عام تترك المشغّل بلا سبب، وهو
            بالضبط ما جاء ليعرفه: أهي كلمة المرور أم المنفذ أم جدار
            الحماية؟
        """
        account = EmailAccount.objects.create(
            code="broken",
            label_ar="معطّل",
            label_en="Broken",
            host="127.0.0.1",
            port=1,
            timeout=1,
            from_email="x@example.com",
        )
        url = reverse("v1:mailing:account-verify", args=[account.pk])

        response = admin_client.post(url)

        assert response.status_code == 200
        assert response.data["ok"] is False
        assert response.data["error"]

        account.refresh_from_db()
        assert account.consecutive_failures == 1

    def test_test_send_uses_the_account_it_was_asked_about(self, admin_client, db, monkeypatch):
        """
        ⚠️  الرسالة التجريبية تتجاوز الحلّال عمدًا: السؤال «هل يعمل
            **هذا** الحساب؟» لا «من المسؤول عن هذا الغرض؟». تمريرها
            بالحلّال كان يفحص حسابًا غير الذي يجلس المشغّل أمامه.
        """
        from django.core import mail as django_mail

        from mailing import services

        monkeypatch.setattr(
            services, "CONSOLE_BACKEND", "django.core.mail.backends.locmem.EmailBackend"
        )
        EmailAccount.objects.create(
            code="default-one",
            label_ar="الافتراضي",
            label_en="Default",
            transport=MailTransport.CONSOLE,
            from_email="default@example.com",
            is_default=True,
        )
        tested = EmailAccount.objects.create(
            code="secondary",
            label_ar="الثانوي",
            label_en="Secondary",
            transport=MailTransport.CONSOLE,
            from_email="secondary@example.com",
        )
        django_mail.outbox.clear()

        url = reverse("v1:mailing:account-test-send", args=[tested.pk])
        response = admin_client.post(url, {"to": "ops@example.com"}, format="json")

        assert response.status_code == 200
        assert response.data["ok"] is True
        assert django_mail.outbox[0].from_email == "secondary@example.com"


@pytest.mark.django_db
class TestRoutingAPI:
    def test_map_shows_the_account_and_its_source(self, admin_client, account):
        from mailing.models import MailRoute
        from mailing.purposes import MailPurpose

        account.is_default = True
        account.save()
        orders = EmailAccount.objects.create(
            code="orders",
            label_ar="الطلبات",
            label_en="Orders",
            host="smtp.example.com",
            from_email="orders@example.com",
        )
        MailRoute.objects.create(purpose=MailPurpose.ORDERS, account=orders)

        response = admin_client.get(reverse("v1:mailing:routing-map"))

        assert response.status_code == 200
        rows = {row["template_key"]: row for row in response.data}
        assert rows["order_placed"]["account_code"] == "orders"
        assert rows["order_placed"]["source"] == "purpose"
        assert rows["password_reset"]["source"] == "default"

    def test_security_route_to_marketing_is_refused_by_the_api(self, admin_client, db):
        """السياج يُفرَض في الـ API كما في لوحة الإدارة — لا نسختين للقاعدة."""
        from mailing.purposes import MailPurpose

        promo = EmailAccount.objects.create(
            code="promo",
            label_ar="التسويق",
            label_en="Marketing",
            host="smtp.example.com",
            from_email="promo@example.com",
            is_marketing=True,
        )

        response = admin_client.post(
            reverse("v1:mailing:routes"),
            {"purpose": MailPurpose.ACCOUNT, "account": str(promo.pk)},
            format="json",
        )

        assert response.status_code == 400

    def test_purpose_is_corrected_from_the_template(self, admin_client, account):
        """
        ⚠️  صفٌّ بغرض يخالف غرض قالبه لا يخطئ ولا يعمل: لا يطابق شيئًا
            أبدًا. والتصحيح يمنع إعدادًا يراه المشغّل مضبوطًا وهو ميت.
        """
        from mailing.purposes import MailPurpose

        response = admin_client.post(
            reverse("v1:mailing:routes"),
            {
                "purpose": MailPurpose.MARKETING,
                "template_key": "order_shipped",
                "account": str(account.pk),
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["purpose"] == MailPurpose.SHIPPING


@pytest.mark.django_db
class TestOutboxAPI:
    def test_list_answers_did_the_message_go_out(self, admin_client, account):
        from mailing import services

        account.is_default = True
        account.save()
        services.enqueue(
            "password_changed", to="customer@example.com", language="ar", context={"name": "أحمد"}
        )

        response = admin_client.get(reverse("v1:mailing:outbox"))

        assert response.status_code == 200
        row = response.data["results"][0]
        assert row["to_email"] == "customer@example.com"
        assert row["status"] == "PENDING"

    def test_body_is_not_exposed_in_the_list(self, admin_client, account):
        """
        ⚠️  نص الرسالة يحمل روابط تفعيل وإعادة تعيين صالحة للاستعمال.

            عرضه في جدول يقرؤه كل من يفتح شاشة البريد يحوّل شاشة
            تشخيص إلى مفتاح لكل حساب في النظام.
        """
        from mailing import services

        account.is_default = True
        account.save()
        services.enqueue(
            "password_reset",
            to="customer@example.com",
            language="ar",
            context={"name": "أحمد", "link": "https://example.com/reset?token=SECRET-TOKEN"},
        )

        response = admin_client.get(reverse("v1:mailing:outbox"))

        assert "SECRET-TOKEN" not in response.content.decode()

    def test_retry_is_available_after_a_declared_failure(self, admin_client, account):
        from mailing import services
        from mailing.models import DeliveryState, OutboundMessage

        account.is_default = True
        account.host = "127.0.0.1"
        account.port = 1
        account.timeout = 1
        account.save()
        message = services.enqueue(
            "password_changed", to="customer@example.com", language="ar", context={"name": "أحمد"}
        )
        OutboundMessage.objects.filter(pk=message.pk).update(status=DeliveryState.FAILED)

        response = admin_client.post(reverse("v1:mailing:outbox-retry", args=[message.pk]))

        assert response.status_code == 502
        assert response.data["ok"] is False
        assert response.data["error"]


@pytest.mark.django_db
class TestTemplateAPI:
    def test_list_shows_all_templates_not_just_edited_ones(self, admin_client):
        """
        ⚠️  الشاشة تسأل عن القوالب لا عن الجدول: عرض التجاوزات وحدها
            كان يُظهر قائمة فارغة على نظام يرسل ثلاثة عشر قالبًا.
        """
        from mailing.templates import TEMPLATES

        response = admin_client.get(reverse("v1:mailing:templates"))

        assert response.status_code == 200
        assert {row["key"] for row in response.data} == set(TEMPLATES)
        assert all(row["is_overridden"] is False for row in response.data)

    def test_row_carries_the_available_variables(self, admin_client):
        """المحرّر الذي لا يرى ما يملك يكتب `{price}` بدل `{total}`."""
        response = admin_client.get(reverse("v1:mailing:template-detail", args=["order_placed"]))

        assert set(response.data["variables"]) == {"name", "number", "total", "link"}

    def test_save_then_reset_returns_the_original(self, admin_client):
        url = reverse("v1:mailing:template-detail", args=["password_changed"])
        original = admin_client.get(url).data["subject_ar"]

        saved = admin_client.put(
            url,
            {
                "subject_ar": "تنبيه أمني",
                "subject_en": "Security alert",
                "body_ar": "مرحبًا {name}",
                "body_en": "Hello {name}",
            },
            format="json",
        )
        assert saved.status_code == 200
        assert saved.data["subject_ar"] == "تنبيه أمني"
        assert saved.data["is_overridden"] is True

        # ⚠️  «الرجوع إلى الافتراضي» ضغطة لا إعادة كتابة من الذاكرة
        reset = admin_client.delete(url)

        assert reset.status_code == 200
        assert reset.data["subject_ar"] == original
        assert reset.data["is_overridden"] is False

    def test_unknown_variable_is_refused_by_the_api(self, admin_client):
        response = admin_client.put(
            reverse("v1:mailing:template-detail", args=["password_changed"]),
            {
                "subject_ar": "تنبيه",
                "subject_en": "Alert",
                "body_ar": "مرحبًا {name}، رصيدك {balance}",
                "body_en": "Hello {name}",
            },
            format="json",
        )

        assert response.status_code == 400
        # المعالج الموحّد يضع أخطاء الحقول تحت `fields` (اصطلاح الـ API)
        assert "body_ar" in response.data["fields"]

    def test_preview_renders_the_draft_without_saving(self, admin_client):
        """
        ⚠️  المعاينة تعمل على ما في الشاشة الآن: معاينة لا تسبق الحفظ
            لا تمنع شيئًا. ولا تلمس قاعدة البيانات — التجربة ليست التزامًا.
        """
        from mailing.models import TemplateOverride

        response = admin_client.post(
            reverse("v1:mailing:template-preview", args=["password_changed"]),
            {"subject_ar": "مرحبًا {name} — تنبيه", "body_ar": "نصّ {name}"},
            format="json",
        )

        assert response.status_code == 200
        assert "أحمد محمود" in response.data["ar"]["subject"]
        assert TemplateOverride.objects.count() == 0

    def test_preview_names_the_unknown_variables(self, admin_client):
        """
        ⚠️  المتغيّر المجهول يُعرَض صراحةً بدل أن يمرّ في النص فيراه
            المحرّر «كلمة غريبة» ويتجاهلها.
        """
        response = admin_client.post(
            reverse("v1:mailing:template-preview", args=["password_changed"]),
            {"body_ar": "مرحبًا {name}، رصيدك {balance}"},
            format="json",
        )

        assert response.data["ar"]["unknown_variables"] == ["balance"]

    def test_customer_cannot_read_templates(self, db):
        user_model = _model("accounts", "User")
        customer = user_model.objects.create_user(
            email="reader@test.local", password=PASSWORD, account_type="CUSTOMER"
        )
        customer.is_active = True
        customer.save()

        client = APIClient()
        client.force_authenticate(user=customer)

        assert client.get(reverse("v1:mailing:templates")).status_code == 403


@pytest.mark.django_db
class TestTemplateResetCycle:
    def test_edit_reset_edit_again_works(self, admin_client):
        """
        ⚠️  الدورة الكاملة: تحرير ← رجوع ← تحرير من جديد.

            بتفرّد صارم كان الصفّ المحذوف ناعمًا يحتلّ المفتاح إلى
            الأبد، فيفشل التحرير الثاني بـ IntegrityError على مفتاح لا
            يراه المشغّل — وهو عطل لا يظهر إلا لمن رجع عن تحرير مرة.
        """
        url = reverse("v1:mailing:template-detail", args=["password_changed"])
        payload = {
            "subject_ar": "تنبيه أمني",
            "subject_en": "Security alert",
            "body_ar": "مرحبًا {name}",
            "body_en": "Hello {name}",
        }

        assert admin_client.put(url, payload, format="json").status_code == 200
        assert admin_client.delete(url).status_code == 200

        again = admin_client.put(url, {**payload, "subject_ar": "تنبيه ثانٍ"}, format="json")

        assert again.status_code == 200
        assert again.data["subject_ar"] == "تنبيه ثانٍ"
        assert again.data["is_overridden"] is True
