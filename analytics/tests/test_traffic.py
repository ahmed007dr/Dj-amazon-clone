"""
اختبارات قياس الحركة.

⚠️  الخاصية المحروسة الأولى: **القياس لا يُسقط طلبًا أبدًا**.

    وسيطٌ يرفع استثناءً على مسار صفحة منتج يحوّل عطلًا في الإحصاء
    إلى عطل في المتجر — وهو ثمن لا يستحقه أي رقم.

⚠️  والثانية: لا هوية شخصية تصل قاعدة البيانات.

    الجدول أعداد فقط، والبصمة تعيش في الكاش وتزول.
"""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountType, DeviceType, User
from analytics import services
from analytics.middleware import TrafficMiddleware, client_ip
from analytics.models import TrafficBucket

PASSWORD = "Str0ng-Test-Pass!23"


def _admin_profile():
    """
    ⚠️  `apps.get_model` لا `import` — **مقصود**.

        `analytics` تحت `administration` في مخطط الطبقات، ويفرضه
        `import-linter` في الـ CI. واختبارٌ يستورد لأعلى يكسر العقد
        الذي يحرسه كل الكود الآخر — و«لأنه اختبار فقط» هو أول ثقب
        في أي عقد معماري.
    """
    from django.apps import apps

    return apps.get_model("administration", "AdminProfile")

CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148"
GOOGLEBOT = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"


@pytest.fixture
def visit():
    def _visit(*, ip="10.0.0.1", user_agent=CHROME, authenticated=False):
        services.record_visit(ip=ip, user_agent=user_agent, authenticated=authenticated)

    return _visit


def _counter(kind: str, device: str) -> int:
    bucket = services.bucket_of(timezone.now())
    return cache.get(services._key(kind, bucket, device)) or 0


# ═══════════════════════════════════════════════════════════
#  العدّ
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCounting:
    def test_a_visitor_is_unique_within_the_hour(self, visit):
        """⚠️  «زائر فريد» لا «طلب» — الخلط يضخّم الرقم عشرة أضعاف."""
        for _ in range(5):
            visit()

        assert _counter("req", DeviceType.DESKTOP) == 5
        assert _counter("guest", DeviceType.DESKTOP) == 1

    def test_a_different_network_is_a_different_visitor(self, visit):
        visit(ip="10.0.0.1")
        visit(ip="10.0.0.2")

        assert _counter("guest", DeviceType.DESKTOP) == 2

    def test_devices_are_counted_apart(self, visit):
        visit(user_agent=CHROME)
        visit(ip="10.0.0.9", user_agent=IPHONE)

        assert _counter("guest", DeviceType.DESKTOP) == 1
        assert _counter("guest", DeviceType.MOBILE) == 1

    def test_a_signed_in_visitor_is_not_a_guest(self, visit):
        """⚠️  عدّه مرتين يجعل «المتصلون الآن» رقمًا مضخّمًا."""
        visit(authenticated=True)

        assert _counter("known", DeviceType.DESKTOP) == 1
        assert _counter("guest", DeviceType.DESKTOP) == 0
        assert services.guests_online() == 0

    def test_a_crawler_is_not_pressure(self, visit):
        """⚠️  ذروة زحف محرك بحث ليست ساعة يوجد فيها إنسان."""
        visit(user_agent=GOOGLEBOT)

        assert _counter("req", DeviceType.DESKTOP) == 0
        assert services.guests_online() == 0

    def test_the_fingerprint_hides_the_visitor(self):
        identity = services.fingerprint("41.32.8.4", CHROME)

        assert "41.32.8.4" not in identity
        assert identity != services.fingerprint("41.32.8.5", CHROME)
        assert identity == services.fingerprint("41.32.8.4", CHROME)


# ═══════════════════════════════════════════════════════════
#  الحضور الآن
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestGuestPresence:
    def test_guests_are_counted_now(self, visit):
        visit(ip="10.0.0.1")
        visit(ip="10.0.0.2")

        assert services.guests_online() == 2

    def test_a_stale_guest_leaves(self, visit):
        visit()
        registry = cache.get(services.visitors.key)
        stale = timezone.now() - services.VISITOR_WINDOW - timedelta(minutes=1)
        cache.set(services.visitors.key, dict.fromkeys(registry, stale.isoformat()), 600)

        assert services.guests_online() == 0


# ═══════════════════════════════════════════════════════════
#  الوسيط
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestMiddleware:
    def test_a_store_request_is_measured(self, client):
        client.get(reverse("v1:catalog:products"), HTTP_USER_AGENT=CHROME)
        assert _counter("req", DeviceType.DESKTOP) == 1

    def test_the_admin_panel_is_not_store_pressure(self, db):
        """⚠️  لوحة تُحدِّث نفسها كل ٣٠ ثانية تصنع ذروة وهمية."""
        admin = User.objects.create_user(
            email="traffic-admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
        )
        admin.is_active = True
        admin.save()
        _admin_profile().objects.create(user=admin)

        api = APIClient()
        api.force_authenticate(user=admin)
        api.get(reverse("v1:administration:online-now"), HTTP_USER_AGENT=CHROME)

        assert _counter("req", DeviceType.DESKTOP) == 0

    def test_a_refused_request_is_not_usage(self, client):
        """⚠️  محاولة اقتحام لا يجوز أن تبدو ذروة تصفّح."""
        client.get("/api/v1/catalog/products/no-such-product/", HTTP_USER_AGENT=CHROME)
        assert _counter("req", DeviceType.DESKTOP) == 0

    def test_a_measurement_failure_never_breaks_the_response(self, monkeypatch, client):
        def explode(**kwargs):
            raise RuntimeError("الكاش سقط")

        monkeypatch.setattr(services, "record_visit", explode)
        response = client.get(reverse("v1:catalog:products"), HTTP_USER_AGENT=CHROME)

        assert response.status_code == 200

    def test_the_proxy_header_wins_over_the_socket(self):
        """
        ⚠️  خلف Nginx يكون `REMOTE_ADDR` هو الوكيل نفسه.

            بدون قراءة الترويسة يصير كل الزوار بصمةً واحدة و«الزوار
            الفريدون» رقمًا ثابتًا عند ١ إلى الأبد.
        """
        request = RequestFactory().get(
            "/api/v1/catalog/products/",
            HTTP_X_FORWARDED_FOR="41.32.8.4, 10.0.0.1",
            REMOTE_ADDR="10.0.0.1",
        )
        assert client_ip(request) == "41.32.8.4"

    def test_non_api_paths_are_ignored(self, db):
        request = RequestFactory().get("/robots.txt", HTTP_USER_AGENT=CHROME)
        response = TrafficMiddleware(lambda r: None).process_response(
            request, _ok_response()
        )

        assert response.status_code == 200
        assert _counter("req", DeviceType.DESKTOP) == 0


def _ok_response():
    from django.http import HttpResponse

    return HttpResponse("ok")


# ═══════════════════════════════════════════════════════════
#  التفريغ
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestFlush:
    def test_counters_become_a_bucket(self, visit):
        visit()
        visit(ip="10.0.0.2")

        assert services.flush_traffic() == 1

        row = TrafficBucket.objects.get()
        assert row.requests == 2
        assert row.guest_visitors == 2
        assert row.bucket_start == services.bucket_of(timezone.now())

    def test_flushing_twice_does_not_double(self, visit):
        visit()
        services.flush_traffic()
        services.flush_traffic()

        assert TrafficBucket.objects.count() == 1
        assert TrafficBucket.objects.get().requests == 1

    def test_a_reset_cache_does_not_erase_a_recorded_hour(self, visit):
        """⚠️  الكتابة بالأكبر لا بالإحلال — وإلا محا الصفرُ ساعةً."""
        visit()
        visit(ip="10.0.0.2")
        services.flush_traffic()

        cache.clear()
        services.flush_traffic()

        assert TrafficBucket.objects.get().requests == 2

    def test_nothing_is_written_for_a_silent_hour(self, db):
        assert services.flush_traffic() == 0
        assert not TrafficBucket.objects.exists()

    def test_old_traffic_is_purged(self, db):
        TrafficBucket.objects.create(
            bucket_start=timezone.now() - timedelta(days=120), requests=9
        )
        recent = TrafficBucket.objects.create(
            bucket_start=timezone.now() - timedelta(days=3), requests=4
        )

        assert services.purge_traffic(days=90) == 1
        assert list(TrafficBucket.objects.all()) == [recent]


# ═══════════════════════════════════════════════════════════
#  القراءة والصلاحيات
# ═══════════════════════════════════════════════════════════


@pytest.fixture
def admin_user(db):
    user = User.objects.create_user(
        email="live-admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    user.is_active = True
    user.save()
    _admin_profile().objects.create(user=user)
    return user


@pytest.fixture
def reports_user(db):
    """
    ⚠️  **مستخدم آخر** لا نفس الأدمن بصلاحية مضافة.

        منح الصلاحية لكائن الاختبار نفسه كان يجعل «أدمن بلا صلاحية»
        و«أدمن بصلاحية» شخصًا واحدًا — فيمرّ اختبار الحجب دائمًا
        بلا أن يفحص شيئًا.
    """
    from django.contrib.auth.models import Permission

    user = User.objects.create_user(
        email="reports-admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    user.is_active = True
    user.save()
    _admin_profile().objects.create(user=user)
    user.user_permissions.add(Permission.objects.get(codename="view_revenueentry"))
    return User.objects.get(pk=user.pk)


@pytest.mark.django_db
class TestReadEndpoints:
    def test_live_separates_guests_from_users(self, admin_user, visit):
        visit(ip="10.0.0.1")
        visit(ip="10.0.0.2")

        api = APIClient()
        api.force_authenticate(user=admin_user)
        data = api.get(reverse("v1:analytics:live")).data

        assert data["guests_online"] == 2
        assert data["users_online"] == 0
        assert data["total_online"] == 2

    def test_a_customer_cannot_read_the_live_pulse(self, db):
        customer = User.objects.create_user(email="shopper@test.local", password=PASSWORD)
        customer.is_active = True
        customer.save()

        api = APIClient()
        api.force_authenticate(user=customer)

        assert api.get(reverse("v1:analytics:live")).status_code == 403

    def test_traffic_needs_more_than_panel_access(self, admin_user, reports_user):
        """⚠️  منحنى الحركة يكشف حجم النشاط — صلاحية التقارير لا اللوحة."""
        panel_only = APIClient()
        panel_only.force_authenticate(user=admin_user)
        assert panel_only.get(reverse("v1:analytics:traffic")).status_code == 403

        allowed = APIClient()
        allowed.force_authenticate(user=reports_user)
        assert allowed.get(reverse("v1:analytics:traffic")).status_code == 200

    def test_the_summary_splits_devices(self, reports_user, visit):
        visit(user_agent=CHROME)
        visit(ip="10.0.0.9", user_agent=IPHONE)
        services.flush_traffic()

        api = APIClient()
        api.force_authenticate(user=reports_user)
        data = api.get(reverse("v1:analytics:traffic")).data

        assert data["guest_visitors"] == 2
        devices = {row["device_type"] for row in data["by_device"]}
        assert devices == {DeviceType.DESKTOP, DeviceType.MOBILE}

    def test_the_heatmap_grid_is_complete(self, reports_user):
        api = APIClient()
        api.force_authenticate(user=reports_user)
        data = api.get(reverse("v1:analytics:peak-hours")).data

        assert len(data["cells"]) == 24 * 7
        assert data["peak_cell"] is None

    def test_an_inverted_range_is_refused(self, reports_user):
        api = APIClient()
        api.force_authenticate(user=reports_user)
        response = api.get(
            reverse("v1:analytics:traffic"), {"start": "2026-05-01", "end": "2026-04-01"}
        )

        assert response.status_code == 400
