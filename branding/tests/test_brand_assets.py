"""
رفع أصول الهوية من اللوحة.

⚠️  **الأصول كانت بلا أي فحص** بينما صور المنتجات مفحوصة بتوقيعها —
    تفاوت لا يبرّره شيء. واللوجو أخطر: يُقدَّم من أصل الموقع نفسه
    ويظهر في **كل** صفحة لكل زائر.

⚠️  و`apps.get_model` لا `import`: `branding` ممنوع من استيراد أي
    نطاق عمل، والاختبار جزء من الحزمة لا استثناء منها.
"""

import pytest
from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.test import APIClient

from branding.models import BrandProfile, ThemeMode, ThemePalette
from conftest import real_png_bytes

PASSWORD = "Str0ng-Test-Pass!23"

pytestmark = pytest.mark.django_db


def _model(label: str, name: str):
    return apps.get_model(label, name)


@pytest.fixture
def profile(db):
    profile = BrandProfile.objects.create(
        code="assets", name_ar="متجر", name_en="Store", is_active=True
    )
    for mode in ThemeMode:
        ThemePalette.objects.create(profile=profile, mode=mode)
    return profile


@pytest.fixture
def admin_client(db):
    admin = _model("accounts", "User").objects.create_user(
        email="assets-admin@test.local", password=PASSWORD, account_type="ADMIN"
    )
    admin.is_active = True
    admin.save()
    _model("administration", "AdminProfile").objects.create(user=admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


def detail_url(profile):
    return reverse("v1:branding:profile-detail", args=[profile.pk])


# ═══════════════════════════════════════════════════════════
#  الرفع
# ═══════════════════════════════════════════════════════════


class TestUpload:
    def test_a_real_image_is_accepted(self, admin_client, profile):
        response = admin_client.patch(
            detail_url(profile),
            {"logo_light": SimpleUploadedFile("logo.png", real_png_bytes(), "image/png")},
            format="multipart",
        )

        assert response.status_code == 200
        profile.refresh_from_db()
        assert profile.logo_light.name

    def test_a_forged_content_type_is_refused(self, admin_client, profile):
        """
        ⚠️  **الفحص على توقيع الملف لا على ترويسته.**

            `content_type` يأتي من العميل ويُزوَّر بسطر واحد. وملف
            نصّي يحمل ترويسة صورة كان يمرّ ويُقدَّم من أصل الموقع —
            وهو بالضبط ما تصدّه القائمة البيضاء على التوقيع.
        """
        response = admin_client.patch(
            detail_url(profile),
            {"logo_light": SimpleUploadedFile("evil.png", b"<svg onload=alert(1)>", "image/png")},
            format="multipart",
        )

        assert response.status_code == 400
        assert "logo_light" in response.data["fields"]

        profile.refresh_from_db()
        assert not profile.logo_light.name

    def test_an_oversized_file_is_refused(self, admin_client, profile):
        """اللوجو يُحمَّل في كل صفحة لكل زائر — الملف الثقيل يبطئ الموقع كله."""
        heavy = real_png_bytes() + b"0" * (3 * 1024 * 1024)

        response = admin_client.patch(
            detail_url(profile),
            {"icon": SimpleUploadedFile("big.png", heavy, "image/png")},
            format="multipart",
        )

        assert response.status_code == 400

    def test_an_empty_file_is_refused(self, admin_client, profile):
        """الحجم صفر يمرّ كل فحص محتوى ويُخزَّن كملف يبدو سليمًا."""
        response = admin_client.patch(
            detail_url(profile),
            {"favicon": SimpleUploadedFile("empty.png", b"", "image/png")},
            format="multipart",
        )

        assert response.status_code == 400

    @pytest.mark.parametrize("field", ["logo_light", "logo_dark", "icon", "favicon", "og_image"])
    def test_every_asset_field_is_guarded(self, admin_client, profile, field):
        """
        ⚠️  الحقل المنسيّ من الفحص هو الثغرة — والخمسة تُرفع من نفس
            الشاشة بنفس الزر.
        """
        response = admin_client.patch(
            detail_url(profile),
            {field: SimpleUploadedFile("x.png", b"not-an-image-at-all", "image/png")},
            format="multipart",
        )

        assert response.status_code == 400, field


# ═══════════════════════════════════════════════════════════
#  المسح والصلاحية
# ═══════════════════════════════════════════════════════════


class TestClearAndPermissions:
    def test_an_asset_can_be_removed(self, admin_client, profile):
        """رفع لوجو بالخطأ يجب أن يُصحَّح من نفس الشاشة."""
        admin_client.patch(
            detail_url(profile),
            {"logo_light": SimpleUploadedFile("logo.png", real_png_bytes(), "image/png")},
            format="multipart",
        )

        # ⚠️  JSON بقيمة `null` لا نموذجًا بقيمة فارغة: الثاني
        #     يتجاهله DRF بصمت ويعيد ٢٠٠ بينما الصورة مكانها.
        response = admin_client.patch(detail_url(profile), {"logo_light": None}, format="json")

        assert response.status_code == 200
        profile.refresh_from_db()
        assert not profile.logo_light.name

    def test_editing_other_fields_leaves_assets_alone(self, admin_client, profile):
        """
        ⚠️  الشاشة تحفظ ما تغيّر وحده. حفظ الاسم يجب ألا يمسح لوجو
            رُفع في تبويب آخر.
        """
        admin_client.patch(
            detail_url(profile),
            {"icon": SimpleUploadedFile("icon.png", real_png_bytes(), "image/png")},
            format="multipart",
        )

        admin_client.patch(detail_url(profile), {"name_ar": "اسم جديد"}, format="json")

        profile.refresh_from_db()
        assert profile.name_ar == "اسم جديد"
        assert profile.icon.name

    def test_a_customer_cannot_upload(self, profile):
        customer = _model("accounts", "User").objects.create_user(
            email="c@test.local", password=PASSWORD
        )
        customer.is_active = True
        customer.save()

        client = APIClient()
        client.force_authenticate(user=customer)

        response = client.patch(
            detail_url(profile),
            {"logo_light": SimpleUploadedFile("logo.png", real_png_bytes(), "image/png")},
            format="multipart",
        )

        assert response.status_code == 403


# ═══════════════════════════════════════════════════════════
#  بقية حقول الملف
# ═══════════════════════════════════════════════════════════


class TestProfileFields:
    def test_typography_and_shape_are_editable(self, admin_client, profile):
        response = admin_client.patch(
            detail_url(profile),
            {
                "font_ar": "Tajawal",
                "font_en": "Roboto",
                "font_size_base": "1.125",
                "radius": "0.250",
                "shadow_level": 2,
                "default_mode": "DARK",
            },
            format="json",
        )

        assert response.status_code == 200
        profile.refresh_from_db()
        assert profile.font_ar == "Tajawal"
        assert profile.shadow_level == 2
        assert profile.default_mode == "DARK"

    def test_out_of_range_values_are_refused(self, admin_client, profile):
        """
        ⚠️  الحدود على الخادم لا في الواجهة وحدها — فحصان متطابقان
            في مكانين يفترقان عند أول تعديل.
        """
        response = admin_client.patch(
            detail_url(profile), {"font_size_base": "9.000"}, format="json"
        )

        assert response.status_code == 400
        assert "font_size_base" in response.data["fields"]

    def test_contact_and_social_are_editable(self, admin_client, profile):
        response = admin_client.patch(
            detail_url(profile),
            {
                "contact_email": "hello@example.com",
                "whatsapp": "201000000000",
                "instagram": "https://instagram.com/store",
            },
            format="json",
        )

        assert response.status_code == 200
        profile.refresh_from_db()
        assert profile.contact_email == "hello@example.com"
        assert profile.instagram.endswith("/store")

    def test_a_malformed_email_is_refused(self, admin_client, profile):
        response = admin_client.patch(
            detail_url(profile), {"contact_email": "not-an-email"}, format="json"
        )

        assert response.status_code == 400
        assert "contact_email" in response.data["fields"]
