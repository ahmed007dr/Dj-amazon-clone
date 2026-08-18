"""
اختبارات التواجد اللحظي  (ADR-17).

⚠️  الخاصية المحروسة هنا ليست «الرقم صحيح» بل **أن الرقم يتحرّك
    أصلًا**. كان `touch_activity` يُستدعى عند الدخول وحده ولا مهمة
    تُفرّغه، فكان «من متصل الآن» يعني عمليًا «من دخل في آخر خمس
    دقائق» — رقمًا يقارب الصفر مهما كان الضغط على النظام.
"""

from datetime import timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts import services
from accounts.models import User, UserSession

PASSWORD = "Str0ng-Test-Pass!23"


@pytest.fixture
def user(db):
    user = User.objects.create_user(email="live@test.local", password=PASSWORD)
    user.is_active = True
    user.email_verified_at = timezone.now()
    user.save()
    return user


def _registry() -> dict:
    return cache.get(services.PRESENCE_KEY) or {}


def _age_heartbeat(user, delta: timedelta) -> None:
    """يُقدِّم نبضة مخزّنة إلى الوراء بلا انتظار حقيقي."""
    registry = _registry()
    stamp = timezone.now() - delta
    registry[str(user.pk)] = stamp.isoformat()
    cache.set(services.PRESENCE_KEY, registry, 600)


# ═══════════════════════════════════════════════════════════
#  النبضة
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestHeartbeat:
    def test_heartbeat_marks_user_live_without_touching_database(
        self, user, django_assert_num_queries
    ):
        """⚠️  نبضة تكلّف استعلامًا واحدًا تقتل القاعدة تحت الضغط."""
        with django_assert_num_queries(0):
            services.touch_activity(user.pk)

        assert user.pk in services.live_user_ids()

    def test_repeated_heartbeats_do_not_rewrite_the_registry(self, user):
        services.touch_activity(user.pk)
        first = _registry()[str(user.pk)]

        services.touch_activity(user.pk)
        assert _registry()[str(user.pk)] == first

    def test_a_stale_heartbeat_leaves_the_live_set(self, user):
        services.touch_activity(user.pk)
        _age_heartbeat(user, services.PRESENCE_WINDOW + timedelta(minutes=1))

        assert user.pk not in services.live_user_ids()

    def test_an_aged_heartbeat_is_refreshed(self, user):
        services.touch_activity(user.pk)
        _age_heartbeat(user, services.PRESENCE_HEARTBEAT + timedelta(seconds=5))
        stale = _registry()[str(user.pk)]

        services.touch_activity(user.pk)
        assert _registry()[str(user.pk)] != stale


# ═══════════════════════════════════════════════════════════
#  الاتحاد بين الكاش والقاعدة
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestOnlineSet:
    def test_a_fresh_session_is_online_before_any_heartbeat(self, user):
        services.open_session(user, session_key="just-logged-in")
        assert user.pk in services.online_user_ids()

    def test_a_heartbeat_survives_an_empty_session_table(self, user):
        """⚠️  سقوط الكاش لا يجوز أن يمحو من هو متصل، والعكس."""
        services.touch_activity(user.pk)
        assert not UserSession.objects.exists()
        assert user.pk in services.online_user_ids()

    def test_the_two_sources_are_not_double_counted(self, user):
        services.open_session(user, session_key="both")
        services.touch_activity(user.pk)

        assert services.online_user_ids().count(user.pk) == 1


# ═══════════════════════════════════════════════════════════
#  الخروج
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPresenceRelease:
    def test_logout_drops_the_heartbeat(self, user):
        session = services.open_session(user, session_key="ending")
        services.touch_activity(user.pk)

        services.close_session(session)
        assert user.pk not in services.live_user_ids()

    def test_a_second_open_device_keeps_the_user_online(self, user):
        first = services.open_session(user, session_key="phone")
        services.open_session(user, session_key="laptop")
        services.touch_activity(user.pk)

        services.close_session(first)
        assert user.pk in services.live_user_ids()


# ═══════════════════════════════════════════════════════════
#  التفريغ الدوري
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestFlush:
    def test_flush_writes_the_heartbeat_into_the_session(self, user):
        session = services.open_session(user, session_key="open")
        UserSession.objects.filter(pk=session.pk).update(
            last_activity=timezone.now() - timedelta(hours=2)
        )

        assert services.flush_presence() == 0  # لا نبضة بعد

        services.touch_activity(user.pk)
        assert services.flush_presence() == 1

        session.refresh_from_db()
        assert timezone.now() - session.last_activity < timedelta(minutes=1)

    def test_flush_does_not_revive_a_closed_session(self, user):
        session = services.open_session(user, session_key="closed")
        services.touch_activity(user.pk)
        services.close_session(session)

        assert services.flush_presence() == 0

    def test_flush_is_free_when_nobody_is_online(self, user, django_assert_num_queries):
        with django_assert_num_queries(0):
            assert services.flush_presence() == 0


# ═══════════════════════════════════════════════════════════
#  الطلب الحقيقي
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestRequestHeartbeat:
    def test_an_authenticated_request_refreshes_presence(self, user):
        """
        ⛔ الكسر القديم: النبضة كانت عند الدخول وحده، فمستخدم يعمل
           في النظام ساعةً كاملة كان يختفي من «المتصلون الآن» بعد
           خمس دقائق.
        """
        client = APIClient()
        tokens = services.issue_jwt(user)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        cache.delete(services.PRESENCE_KEY)
        client.get(reverse("v1:accounts:me"))

        assert user.pk in services.live_user_ids()
