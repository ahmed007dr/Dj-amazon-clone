"""
إدارة الكوبونات من اللوحة.

⚠️  نطاق `promotions` كان **بلا ملف `urls.py` إطلاقًا**: المتجر يقبل
    كوبونًا ولا يستطيع أحد إنشاء واحد إلا من لوحة Django.

⚠️  والمحروس: لا قائمة عامة · الكود موحَّد بحروف كبيرة · المستخدَم
    يُوقَف ولا يُحذف.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.apps import apps
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import AccountType, User
from promotions.models import Coupon

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(db):
    admin = User.objects.create_user(
        email="promo-admin@test.local", password=PASSWORD, account_type=AccountType.ADMIN
    )
    admin.is_active = True
    admin.save()
    apps.get_model("administration", "AdminProfile").objects.create(user=admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


def draft(**overrides) -> dict:
    body = {
        "code": "SUMMER10",
        "name_ar": "حملة الصيف",
        "name_en": "Summer campaign",
        "kind": "PERCENTAGE",
        "value": "10.00",
    }
    body.update(overrides)
    return body


# ═══════════════════════════════════════════════════════════
#  الإنشاء والتحقق
# ═══════════════════════════════════════════════════════════


class TestCreate:
    def test_a_coupon_is_created(self, admin_client):
        response = admin_client.post(reverse("v1:promotions:coupons"), draft(), format="json")

        assert response.status_code == 201
        assert Coupon.objects.filter(code="SUMMER10").exists()

    def test_the_code_is_normalised_to_upper_case(self, admin_client):
        """
        ⚠️  بلا توحيد يصير `summer10` و`SUMMER10` كوبونين — والعميل
            الذي يكتبه بحروف صغيرة يُرفض بلا سبب مفهوم.
        """
        response = admin_client.post(
            reverse("v1:promotions:coupons"), draft(code=" summer20 "), format="json"
        )

        assert response.status_code == 201
        assert response.data["code"] == "SUMMER20"

    def test_a_duplicate_code_is_caught_after_normalising(self, admin_client):
        """
        ⚠️  التحقق على الصيغة **الموحّدة**: بدونه يمرّ `summer10`
            بجوار `SUMMER10` ثم يصطدمان عند الحفظ بخطأ قاعدة بيانات
            لا رسالة حقل.
        """
        admin_client.post(reverse("v1:promotions:coupons"), draft(), format="json")

        response = admin_client.post(
            reverse("v1:promotions:coupons"), draft(code="summer10"), format="json"
        )

        assert response.status_code == 400
        assert "code" in response.data["fields"]

    def test_a_percentage_above_hundred_is_refused(self, admin_client):
        """النسبة فوق ١٠٠٪ تجعل الطلب سالبًا — المتجر يدفع للعميل."""
        response = admin_client.post(
            reverse("v1:promotions:coupons"), draft(value="120.00"), format="json"
        )
        assert response.status_code == 400

    def test_a_zero_discount_is_refused(self, admin_client):
        """
        ⚠️  ليس خطأً تقنيًا لكنه كوبون بلا أثر: العميل يُدخله ويرى
            «طُبّق» ولا يتغيّر شيء — فيشكو من عطل غير موجود.
        """
        response = admin_client.post(
            reverse("v1:promotions:coupons"), draft(value="0.00"), format="json"
        )
        assert response.status_code == 400

    def test_an_end_before_start_is_refused(self, admin_client):
        now = timezone.now()

        response = admin_client.post(
            reverse("v1:promotions:coupons"),
            draft(starts_at=now.isoformat(), ends_at=(now - timedelta(days=1)).isoformat()),
            format="json",
        )

        assert response.status_code == 400
        assert "ends_at" in response.data["fields"]

    def test_usage_count_cannot_be_written(self, admin_client):
        """
        ⚠️  كتابته تعني أن تعديلًا في اللوحة يعيد فتح كوبون استُنفد
            بلا أثر في أي سجل صرف.
        """
        response = admin_client.post(
            reverse("v1:promotions:coupons"), draft(usage_count=999), format="json"
        )

        assert response.status_code == 201
        assert Coupon.objects.get(code="SUMMER10").usage_count == 0


# ═══════════════════════════════════════════════════════════
#  الحذف والحالة
# ═══════════════════════════════════════════════════════════


class TestLifecycle:
    def test_a_used_coupon_is_not_deleted(self, admin_client):
        """
        ⚠️  سجلات الصرف تشير إليه، وحذفه يجعل «بكم بيع هذا الطلب
            ولماذا؟» سؤالًا بلا جواب.
        """
        coupon = Coupon.objects.create(
            code="USED",
            name_ar="مستخدم",
            name_en="Used",
            kind="FIXED",
            value=Decimal("5.00"),
            usage_count=3,
        )

        response = admin_client.delete(reverse("v1:promotions:coupon-detail", args=[coupon.pk]))

        assert response.status_code == 409
        assert "3" in response.data["detail"]
        assert Coupon.objects.filter(pk=coupon.pk).exists()

    def test_an_unused_coupon_is_deleted(self, admin_client):
        coupon = Coupon.objects.create(
            code="FRESH", name_ar="جديد", name_en="Fresh", kind="FIXED", value=Decimal("5.00")
        )

        response = admin_client.delete(reverse("v1:promotions:coupon-detail", args=[coupon.pk]))
        assert response.status_code == 204

    def test_status_filter_runs_in_the_query(self, admin_client):
        """
        ⚠️  التصفية في بايثون بعد الترقيم تعطي صفحات ناقصة بلا أن
            يلاحظ أحد.
        """
        now = timezone.now()

        Coupon.objects.create(
            code="LIVE",
            name_ar="جارٍ",
            name_en="Live",
            kind="FIXED",
            value=Decimal("5.00"),
            starts_at=now - timedelta(days=1),
        )
        Coupon.objects.create(
            code="SOON",
            name_ar="قادم",
            name_en="Soon",
            kind="FIXED",
            value=Decimal("5.00"),
            starts_at=now + timedelta(days=7),
        )

        running = admin_client.get(reverse("v1:promotions:coupons"), {"status": "running"})
        scheduled = admin_client.get(reverse("v1:promotions:coupons"), {"status": "scheduled"})

        assert [row["code"] for row in running.data["results"]] == ["LIVE"]
        assert [row["code"] for row in scheduled.data["results"]] == ["SOON"]

    def test_the_running_flags_are_exposed(self, admin_client):
        """الأدمن يحتاج «لماذا لا يعمل؟» لا «مفعّل: نعم» وحدها."""
        Coupon.objects.create(
            code="DONE",
            name_ar="منتهٍ",
            name_en="Done",
            kind="FIXED",
            value=Decimal("5.00"),
            usage_limit=1,
            usage_count=1,
        )

        response = admin_client.get(reverse("v1:promotions:coupons"))
        row = response.data["results"][0]

        assert row["is_exhausted"] is True
        assert row["is_running"] is False


# ═══════════════════════════════════════════════════════════
#  الخصوصية
# ═══════════════════════════════════════════════════════════


def test_the_coupon_list_is_never_public():
    """
    ⚠️  كشفها يجعل كل زائر يجرّب أعلى خصم متاح بدل الكود الذي وصله
        في حملته — فتنهار كل حملة موجّهة.
    """
    assert APIClient().get(reverse("v1:promotions:coupons")).status_code in (401, 403)


def test_a_customer_cannot_read_redemptions():
    customer = User.objects.create_user(email="c@test.local", password=PASSWORD)
    customer.is_active = True
    customer.save()

    client = APIClient()
    client.force_authenticate(user=customer)

    assert client.get(reverse("v1:promotions:redemptions")).status_code == 403
