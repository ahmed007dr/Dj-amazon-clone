import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from core import features
from core.models.settings import SystemSetting

URL = "/api/v1/public-config/"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
class TestPublicConfig:
    def test_the_switch_row_exists_and_is_off_after_migration(self):
        row = SystemSetting.objects.get(pk=features.STUDENT_VERIFICATION_ENFORCED)

        assert row.value is False
        assert features.student_verification_enforced() is False

    def test_missing_row_means_off(self):
        SystemSetting.objects.filter(pk=features.STUDENT_VERIFICATION_ENFORCED).delete()
        cache.clear()

        assert features.student_verification_enforced() is False

    def test_endpoint_is_public_and_reports_the_switch(self):
        response = APIClient().get(URL)

        assert response.status_code == 200
        assert response.json() == {"student_verification_enforced": False}

    def test_turning_it_on_is_reflected(self):
        SystemSetting.set(features.STUDENT_VERIFICATION_ENFORCED, True)

        assert APIClient().get(URL).json()["student_verification_enforced"] is True
