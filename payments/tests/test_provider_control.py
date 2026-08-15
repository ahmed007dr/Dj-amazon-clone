"""
اختبارات التحكم ببوابات الدفع.

⚠️  المتطلب: **أكثر من بوابة مع تشغيلها وإيقافها من لوحة الأدمن**
    بلا تعديل كود ولا إعادة نشر. (ADR-15)

    هذه الاختبارات تحرس الخصائص التي تجعل ذلك حقيقيًا لا زخرفيًا.
"""

from decimal import Decimal

import pytest
from django.core.management import call_command
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from administration.models import AdminProfile
from payments.models import (
    PaymentMethodKind,
    PaymentProvider,
    ProviderCredential,
    TransactionStatus,
)

PASSWORD = "Str0ng-Test-Pass!23"


@pytest.fixture
def providers(db):
    call_command("seed_payment_providers", verbosity=0)
    return {p.code: p for p in PaymentProvider.objects.all()}


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_user(
        email="admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    admin.is_active = True
    admin.save()
    AdminProfile.objects.create(user=admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


# ═══════════════════════════════════════════════════════════
#  تعدد البوابات
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestMultipleProviders:
    def test_seed_activates_only_what_can_actually_work(self, providers):
        """
        ⚠️  البوابات الخارجية تُبذر **موقوفة**.

            تفعيل Paymob أو Fawry بلا مفاتيح يجعل العميل يختارها
            ثم يفشل دفعه بعد أن أدخل بياناته. الجاهز فورًا هو ما
            لا يحتاج حسابًا خارجيًا.
        """
        working = {code for code, p in providers.items() if p.is_active}
        awaiting = {code for code, p in providers.items() if not p.is_active}

        # ⚠️  `pos-card` من الجاهزين: ماكينة الكاونتر تُشغَّل يدويًا
        #     ولا تحتاج مفاتيح مزوّد، فتفعيلها لا يَعِد بما لا يعمل.
        assert working == {"cod", "cash", "bank", "pos-card"}
        assert awaiting == {"paymob", "fawry"}

    def test_external_gateways_start_in_sandbox(self, providers):
        """وضع الإنتاج بلا اختبار يحصّل مالًا حقيقيًا في أول تجربة."""
        assert providers["paymob"].is_sandbox
        assert providers["fawry"].is_sandbox

    def test_reseeding_does_not_disable_a_gateway_the_admin_enabled(self, providers, db):
        """
        ⚠️  **الفخّ الذي أُصلح.**

            كانت البذرة تفرض `is_active` في كل تشغيل — أي أن إعادة
            بذر بعد أن يضيف الأدمن مفاتيح Paymob ويفعّلها تُوقفها
            ثانيةً بصمت، فيتوقّف الدفع بالبطاقة بلا سبب ظاهر.
        """
        from django.core.management import call_command

        paymob = providers["paymob"]
        paymob.is_active = True
        paymob.is_sandbox = False
        paymob.save()

        call_command("seed_payment_providers", verbosity=0)

        paymob.refresh_from_db()
        assert paymob.is_active, "البذرة أوقفت بوابة فعّلها الأدمن"
        assert not paymob.is_sandbox, "البذرة أعادتها إلى وضع التجريب"

    def test_customer_sees_only_channel_appropriate_methods(self, providers):
        """
        ⚠️  «نقدي» في متجر إلكتروني بلا معنى — القناة تحسم.
        """
        client = APIClient()

        online = client.get(reverse("v1:payments:methods"), {"channel": "ONLINE", "amount": "1000"})
        methods = {entry["method"] for entry in online.data}

        assert PaymentMethodKind.CASH_ON_DELIVERY in methods
        assert PaymentMethodKind.CASH not in methods

        pos = client.get(reverse("v1:payments:methods"), {"channel": "POS", "amount": "1000"})
        pos_methods = {entry["method"] for entry in pos.data}
        assert PaymentMethodKind.CASH in pos_methods

    def test_amount_limits_filter_providers(self, providers):
        """التحويل البنكي بحد أدنى ٥٠٠ — لا يظهر لطلب أصغر."""
        client = APIClient()

        small = client.get(reverse("v1:payments:methods"), {"channel": "ONLINE", "amount": "100"})
        large = client.get(reverse("v1:payments:methods"), {"channel": "ONLINE", "amount": "1000"})

        assert PaymentMethodKind.BANK_TRANSFER not in {e["method"] for e in small.data}
        assert PaymentMethodKind.BANK_TRANSFER in {e["method"] for e in large.data}

    def test_highest_priority_provider_wins(self, providers, db):
        """
        ⚠️  عند صلاحية أكثر من بوابة، الأعلى أولوية يُجرَّب أولًا.
        """
        from payments import services

        PaymentProvider.objects.create(
            code="cod2",
            adapter_key="cash_on_delivery",
            name_ar="دفع بديل",
            name_en="Alt COD",
            supported_methods=[PaymentMethodKind.CASH_ON_DELIVERY],
            supported_channels=["ONLINE"],
            priority=500,
            is_active=True,
        )

        candidates = services.available_providers(
            method=PaymentMethodKind.CASH_ON_DELIVERY,
            channel="ONLINE",
            amount=Decimal("100"),
        )
        assert candidates[0].code == "cod2"


# ═══════════════════════════════════════════════════════════
#  التشغيل والإيقاف — جوهر المتطلب
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestToggleControl:
    def test_disabling_removes_it_from_customer_options_immediately(self, admin_client, providers):
        """
        ⚠️  **جوهر ADR-15.**

            الأدمن يوقف بوابة فتختفي من خيارات العميل في الطلب
            التالي — بلا إعادة نشر ولا تعديل كود.
        """
        client = APIClient()
        params = {"channel": "ONLINE", "amount": "1000"}

        before = {e["method"] for e in client.get(reverse("v1:payments:methods"), params).data}
        assert PaymentMethodKind.BANK_TRANSFER in before

        response = admin_client.post(
            reverse("v1:payments:provider-toggle", args=[providers["bank"].pk]),
            {"is_active": False, "reason": "صيانة الحساب البنكي"},
            format="json",
        )
        assert response.status_code == 200

        after = {e["method"] for e in client.get(reverse("v1:payments:methods"), params).data}
        assert PaymentMethodKind.BANK_TRANSFER not in after

    def test_reenabling_restores_it(self, admin_client, providers):
        url = reverse("v1:payments:provider-toggle", args=[providers["bank"].pk])
        admin_client.post(url, {"is_active": False}, format="json")
        admin_client.post(url, {"is_active": True}, format="json")

        client = APIClient()
        methods = {
            e["method"]
            for e in client.get(
                reverse("v1:payments:methods"), {"channel": "ONLINE", "amount": "1000"}
            ).data
        }
        assert PaymentMethodKind.BANK_TRANSFER in methods

    def test_cannot_disable_the_last_active_provider(self, admin_client, providers):
        """
        ⚠️  متجر بلا بوابة واحدة لا يستقبل طلبات — والاكتشاف يكون
            بشكوى عميل لا بتنبيه.
        """
        # ⚠️  تُوقَف كل النشطة عدا واحدة، فيقع الرفض على الأخيرة.
        for code in ("bank", "cash", "pos-card"):
            admin_client.post(
                reverse("v1:payments:provider-toggle", args=[providers[code].pk]),
                {"is_active": False},
                format="json",
            )

        response = admin_client.post(
            reverse("v1:payments:provider-toggle", args=[providers["cod"].pk]),
            {"is_active": False},
            format="json",
        )

        assert response.status_code == 409
        providers["cod"].refresh_from_db()
        assert providers["cod"].is_active

    def test_toggle_is_audited_with_reason(self, admin_client, providers):
        from core.models.audit import AuditLog

        admin_client.post(
            reverse("v1:payments:provider-toggle", args=[providers["bank"].pk]),
            {"is_active": False, "reason": "تعليق مؤقت"},
            format="json",
        )

        entry = AuditLog.objects.filter(object_repr__contains="bank").first()
        assert entry is not None
        assert entry.changes["is_active"]["new"] is False
        assert entry.changes["reason"] == "تعليق مؤقت"

    def test_customer_cannot_toggle(self, providers):
        customer = User.objects.create_user(email="customer@test.local", password=PASSWORD)
        customer.is_active = True
        customer.save()

        client = APIClient()
        client.force_authenticate(user=customer)

        response = client.post(
            reverse("v1:payments:provider-toggle", args=[providers["cod"].pk]),
            {"is_active": False},
            format="json",
        )
        assert response.status_code == 403


# ═══════════════════════════════════════════════════════════
#  بيانات الاعتماد
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCredentialSecrecy:
    def test_secret_value_is_never_returned(self, admin_client, providers):
        """
        ⚠️  **ADR-15** — القيمة تُكتب ولا تُقرأ، حتى للأدمن.

            إرجاع المفتاح «للتأكد منه» يعني أن تسريب جلسة أدمن
            واحدة يسرّب حساب البوابة كله.
        """
        url = reverse("v1:payments:provider-credentials", args=[providers["bank"].pk])
        secret = "sk_live_abcdefghij0123456789"

        created = admin_client.post(
            url, {"key": "api_key", "value": secret, "is_sandbox": False}, format="json"
        )
        assert created.status_code == 201
        assert secret not in str(created.data)
        assert "value" not in created.data

        listed = admin_client.get(url)
        assert secret not in str(listed.data)
        assert listed.data[0]["masked_value"].endswith("6789")

    def test_provider_listing_shows_key_names_not_values(self, admin_client, providers):
        ProviderCredential.objects.create(
            provider=providers["bank"],
            key="api_key",
            value="super-secret-value",
            is_sandbox=False,
        )

        response = admin_client.get(reverse("v1:payments:providers"))
        payload = str(response.data)

        assert "super-secret-value" not in payload
        assert "api_key" in payload

    def test_audit_log_records_key_name_not_value(self, admin_client, providers):
        from core.models.audit import AuditLog

        admin_client.post(
            reverse("v1:payments:provider-credentials", args=[providers["bank"].pk]),
            {"key": "api_key", "value": "top-secret", "is_sandbox": False},
            format="json",
        )

        entry = AuditLog.objects.filter(object_repr__contains="بيانات اعتماد").first()
        assert entry is not None
        assert "top-secret" not in str(entry.changes)
        assert entry.changes["key"] == "api_key"


# ═══════════════════════════════════════════════════════════
#  إضافة بوابة جديدة من اللوحة
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAddingProviders:
    def test_admin_lists_available_adapters(self, admin_client):
        response = admin_client.get(reverse("v1:payments:adapters"))

        assert "cash_on_delivery" in response.data["adapters"]
        assert "bank_transfer" in response.data["adapters"]

    def test_unknown_adapter_is_rejected(self, admin_client):
        """
        ⚠️  بوابة بمحوّل غير موجود تفشل عند أول محاولة دفع — والرفض
            هنا يجعل الخطأ ظاهرًا وقت الضبط.
        """
        response = admin_client.post(
            reverse("v1:payments:providers"),
            {
                "code": "ghost",
                "adapter_key": "nonexistent_gateway",
                "name_ar": "وهمية",
                "name_en": "Ghost",
                "supported_methods": ["CARD"],
            },
            format="json",
        )

        assert response.status_code == 400
        assert "adapter_key" in response.data["fields"]

    def test_invalid_payment_method_is_rejected(self, admin_client):
        response = admin_client.post(
            reverse("v1:payments:providers"),
            {
                "code": "weird",
                "adapter_key": "cash",
                "name_ar": "غريبة",
                "name_en": "Weird",
                "supported_methods": ["BITCOIN"],
            },
            format="json",
        )
        assert response.status_code == 400

    def test_provider_with_transactions_cannot_be_deleted(self, admin_client, providers, db):
        """
        ⚠️  حذفها يترك معاملات تاريخية بلا مرجع فينكسر كل تقرير مالي.
        """
        from payments.models import PaymentTransaction

        PaymentTransaction.objects.create(
            provider=providers["cod"],
            method=PaymentMethodKind.CASH_ON_DELIVERY,
            amount=Decimal("100.00"),
            status=TransactionStatus.CAPTURED,
        )

        response = admin_client.delete(
            reverse("v1:payments:provider-detail", args=[providers["cod"].pk])
        )
        assert response.status_code == 409
        assert PaymentProvider.objects.filter(pk=providers["cod"].pk).exists()

    def test_reordering_changes_which_provider_wins(self, admin_client, providers, db):
        from payments import services

        alternative = PaymentProvider.objects.create(
            code="cod-alt",
            adapter_key="cash_on_delivery",
            name_ar="بديلة",
            name_en="Alternative",
            supported_methods=[PaymentMethodKind.CASH_ON_DELIVERY],
            supported_channels=["ONLINE"],
            priority=1,
            is_active=True,
        )

        assert (
            services.available_providers(
                method=PaymentMethodKind.CASH_ON_DELIVERY,
                channel="ONLINE",
                amount=Decimal("100"),
            )[0].code
            == "cod"
        )

        admin_client.post(
            reverse("v1:payments:providers-reorder"),
            {"order": [str(alternative.pk), str(providers["cod"].pk)]},
            format="json",
        )

        assert (
            services.available_providers(
                method=PaymentMethodKind.CASH_ON_DELIVERY,
                channel="ONLINE",
                amount=Decimal("100"),
            )[0].code
            == "cod-alt"
        )
