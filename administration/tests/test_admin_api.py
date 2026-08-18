"""
اختبارات بوابة الأدمن.

تغطي ما طُلب صراحةً: إيقاف/تفعيل أي حساب · من متصل الآن ·
آخر استخدام · آخر عملية · مدة الاستخدام.
"""

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountStatus, User, UserSession
from administration.models import AdminProfile

PASSWORD = "Str0ng-Test-Pass!23"


def make_user(email: str, **kwargs) -> User:
    user = User.objects.create_user(email=email, password=PASSWORD, **kwargs)
    user.is_active = True
    user.save()
    return user


@pytest.fixture
def admin(db):
    user = make_user("admin@test.local")
    AdminProfile.objects.create(user=user, department="النظم")
    return user


@pytest.fixture
def customer(db):
    return make_user("customer@test.local")


@pytest.fixture
def admin_client(admin):
    client = APIClient()
    client.force_authenticate(user=admin)
    return client


# ═══════════════════════════════════════════════════════════
#  الصلاحيات
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAdminAccessControl:
    def test_customer_cannot_reach_admin_endpoints(self, customer):
        """أخطر اختبار في هذا الملف — تصعيد الصلاحيات."""
        client = APIClient()
        client.force_authenticate(user=customer)

        for url in (
            reverse("v1:administration:accounts"),
            reverse("v1:administration:online-now"),
            reverse("v1:administration:audit-log"),
        ):
            assert client.get(url).status_code == 403, url

    def test_customer_cannot_suspend_anyone(self, customer):
        victim = make_user("victim@test.local")
        client = APIClient()
        client.force_authenticate(user=customer)

        response = client.post(
            reverse("v1:administration:account-suspend", args=[victim.pk]),
            {"reason": "محاولة تصعيد"},
            format="json",
        )

        assert response.status_code == 403
        victim.refresh_from_db()
        assert victim.status == AccountStatus.ACTIVE

    def test_is_staff_alone_grants_nothing(self, customer):
        """
        ⚠️  `is_staff` وصول لوحة Django — **ليست نموذج الصلاحيات**.
            الاعتماد عليها يمنح كل شيء ضمنيًا.
        """
        customer.is_staff = True
        customer.save()

        client = APIClient()
        client.force_authenticate(user=customer)
        assert client.get(reverse("v1:administration:accounts")).status_code == 403

    def test_anonymous_is_rejected(self, db):
        assert APIClient().get(reverse("v1:administration:accounts")).status_code == 401


# ═══════════════════════════════════════════════════════════
#  إدارة الحسابات
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAccountManagement:
    def test_list_shows_all_accounts_with_count(self, admin_client, customer):
        response = admin_client.get(reverse("v1:administration:accounts"))

        assert response.status_code == 200
        # ترقيم بالإزاحة للأدمن — مصرَّح له برؤية العدد الكلي
        assert response.data["count"] >= 2

    def test_search_and_filter(self, admin_client, customer):
        url = reverse("v1:administration:accounts")

        assert admin_client.get(url, {"search": "customer"}).data["count"] == 1
        assert admin_client.get(url, {"status": "SUSPENDED"}).data["count"] == 0

    def test_suspend_requires_reason(self, admin_client, customer):
        """إيقاف بلا سبب موثّق لا يُدافَع عنه لاحقًا."""
        response = admin_client.post(
            reverse("v1:administration:account-suspend", args=[customer.pk]),
            {},
            format="json",
        )

        assert response.status_code == 400
        assert "reason" in response.data["fields"]

    def test_suspend_records_reason_and_actor(self, admin_client, admin, customer):
        from accounts.models import AccountStatusChange

        response = admin_client.post(
            reverse("v1:administration:account-suspend", args=[customer.pk]),
            {"reason": "مخالفة الشروط"},
            format="json",
        )
        assert response.status_code == 200

        customer.refresh_from_db()
        assert customer.status == AccountStatus.SUSPENDED

        change = AccountStatusChange.objects.get(user=customer)
        assert change.reason == "مخالفة الشروط"
        assert change.changed_by == admin

    def test_suspension_notifies_the_user(
        self, admin_client, customer, django_capture_on_commit_callbacks
    ):
        from django.core import mail as django_mail

        django_mail.outbox.clear()
        with django_capture_on_commit_callbacks(execute=True):
            admin_client.post(
                reverse("v1:administration:account-suspend", args=[customer.pk]),
                {"reason": "مخالفة"},
                format="json",
            )

        assert len(django_mail.outbox) == 1
        assert "مخالفة" in django_mail.outbox[0].body

    def test_admin_cannot_suspend_self(self, admin_client, admin):
        """قفل الذات خطأ لا رجعة فيه بلا تدخل قاعدة البيانات."""
        response = admin_client.post(
            reverse("v1:administration:account-suspend", args=[admin.pk]),
            {"reason": "خطأ"},
            format="json",
        )

        assert response.status_code == 403
        admin.refresh_from_db()
        assert admin.status == AccountStatus.ACTIVE

    def test_activate_restores_and_logs(self, admin_client, customer):
        from accounts import services

        services.suspend_account(customer, reason="اختبار")

        response = admin_client.post(
            reverse("v1:administration:account-activate", args=[customer.pk]),
            {"reason": "انتهى السبب"},
            format="json",
        )

        assert response.status_code == 200
        customer.refresh_from_db()
        assert customer.status == AccountStatus.ACTIVE
        assert not services.is_suspended_cached(customer.pk)

    def test_status_history_is_complete(self, admin_client, customer):
        from accounts import services

        services.suspend_account(customer, reason="أولى")
        services.activate_account(customer, reason="ثانية")
        services.suspend_account(customer, reason="ثالثة")

        response = admin_client.get(
            reverse("v1:administration:account-status-history", args=[customer.pk])
        )

        assert response.status_code == 200
        assert len(response.data) == 3

    def test_unknown_account_returns_404(self, admin_client):
        import uuid

        response = admin_client.post(
            reverse("v1:administration:account-suspend", args=[uuid.uuid4()]),
            {"reason": "اختبار"},
            format="json",
        )
        assert response.status_code == 404


# ═══════════════════════════════════════════════════════════
#  المراقبة
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestMonitoring:
    def test_online_now_reflects_activity_window(self, admin_client, customer):
        from datetime import timedelta

        from accounts import services

        session = services.open_session(customer, session_key="live")

        response = admin_client.get(reverse("v1:administration:online-now"))
        # المعرّف يُسلسَل نصًا في الاستجابة
        assert str(customer.pk) in {str(u["id"]) for u in response.data["users"]}

        # خارج النافذة ⟵ لم يعد متصلًا
        session.last_activity = timezone.now() - timedelta(minutes=30)
        session.save()

        response = admin_client.get(reverse("v1:administration:online-now"))
        assert response.data["count"] == 0

    def test_closed_session_is_not_online(self, admin_client, customer):
        from accounts import services

        session = services.open_session(customer, session_key="ended")
        services.close_session(session)

        response = admin_client.get(reverse("v1:administration:online-now"))
        assert response.data["count"] == 0

    def test_detail_reports_usage_and_session_count(self, admin_client, customer):
        from accounts import services

        for key in ("s1", "s2"):
            services.close_session(services.open_session(customer, session_key=key))

        response = admin_client.get(reverse("v1:administration:account-detail", args=[customer.pk]))

        assert response.status_code == 200
        assert response.data["session_count"] == 2
        assert response.data["total_usage_seconds"] >= 0

    def test_last_action_comes_from_audit_log(self, admin_client, customer):
        """
        ⚠️  «آخر ظهور» و«آخر عملية» سؤالان مختلفان.

        من يفتح التطبيق ولا يفعل شيئًا له ظهور بلا عملية.
        """
        from core.models.audit import AuditAction, AuditLog

        AuditLog.objects.create(
            actor=customer, action=AuditAction.UPDATE, object_repr="تعديل الملف"
        )

        response = admin_client.get(reverse("v1:administration:account-detail", args=[customer.pk]))

        assert response.data["last_action"]["action"] == AuditAction.UPDATE
        assert response.data["last_action"]["object"] == "تعديل الملف"

    def test_last_action_is_null_when_no_activity(self, admin_client, customer):
        response = admin_client.get(reverse("v1:administration:account-detail", args=[customer.pk]))
        assert response.data["last_action"] is None

    def test_session_list_hides_session_key(self, admin_client, customer):
        """من يعرف مفتاح الجلسة ينتحلها."""
        from accounts import services

        services.open_session(customer, session_key="secret-key-value")

        response = admin_client.get(
            reverse("v1:administration:account-sessions", args=[customer.pk])
        )

        assert response.status_code == 200
        assert "session_key" not in response.data["results"][0]

    def test_activity_log_is_scoped_to_the_user(self, admin_client, customer):
        from core.models.audit import AuditAction, AuditLog

        other = make_user("other@test.local")
        AuditLog.objects.create(actor=customer, action=AuditAction.LOGIN, object_repr="له")
        AuditLog.objects.create(actor=other, action=AuditAction.LOGIN, object_repr="لغيره")

        response = admin_client.get(
            reverse("v1:administration:account-activity", args=[customer.pk])
        )

        assert response.data["count"] == 1
        assert response.data["results"][0]["object_repr"] == "له"


@pytest.mark.django_db
class TestQueryEfficiency:
    def test_account_list_does_not_scale_queries_with_rows(
        self, admin_client, django_assert_max_num_queries
    ):
        """
        ⚠️  الحارس ضد N+1.

        جدول الأدمن يُثري كل صف بأربعة حقول محسوبة. بلا تجميع،
        مئة مستخدم = أربعمئة استعلام.
        """
        for i in range(25):
            user = make_user(f"bulk{i}@test.local")
            UserSession.objects.create(user=user, session_key=f"k{i}")

        with django_assert_max_num_queries(15):
            response = admin_client.get(reverse("v1:administration:accounts"))
            assert response.status_code == 200
