"""
اختبارات الهوية البصرية.

⚠️  المتطلب: **التحكم في الألوان واللوجو والشعارات من لوحة الأدمن
    للفرونت إند** — بلا إعادة نشر.

    الاختبارات هنا تحرس الخصائص التي تجعل ذلك حقيقيًا: الأثر فوري ·
    التباين مفروض · الهوية تعمل قبل ضبطها.
"""

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient

from branding import services
from branding.contrast import contrast_ratio, passes_aa
from branding.models import BrandProfile, DefaultMode, ThemeMode, ThemePalette

PASSWORD = "Str0ng-Test-Pass!23"


def _model(label: str, name: str):
    """
    ⚠️  `apps.get_model` لا `import`.

        `branding` ممنوع من استيراد أي نطاق عمل — يفرضه
        `import-linter`، والاختبار جزء من الحزمة لا استثناء منها.
        وهذا صحيح: لو استورد `branding` النموذج `User` لصار حذف
        نطاق الحسابات كاسرًا للهوية البصرية بلا سبب.

        البحث بالنص يبقي الاعتماد على **وقت التشغيل** فقط، ويجب أن
        يقع داخل دالة لا في مستوى الوحدة (`AppRegistryNotReady`).
    """
    return apps.get_model(label, name)


@pytest.fixture
def profile(db):
    profile = BrandProfile.objects.create(
        code="test", name_ar="متجر", name_en="Store", is_active=True
    )
    for mode in ThemeMode:
        ThemePalette.objects.create(profile=profile, mode=mode)
    services.invalidate_cache()
    return profile


@pytest.fixture
def admin_client(db):
    user_model = _model("accounts", "User")

    admin = user_model.objects.create_user(
        email="brand-admin@test.local", password=PASSWORD, account_type="ADMIN"
    )
    admin.is_active = True
    admin.save()
    _model("administration", "AdminProfile").objects.create(user=admin)

    client = APIClient()
    client.force_authenticate(user=admin)
    return client


# ═══════════════════════════════════════════════════════════
#  حساب التباين
# ═══════════════════════════════════════════════════════════


class TestContrast:
    def test_known_ratios(self):
        """القيم المرجعية من مواصفة WCAG."""
        assert round(contrast_ratio("#000000", "#ffffff"), 1) == 21.0
        assert round(contrast_ratio("#ffffff", "#ffffff"), 1) == 1.0

    def test_order_does_not_matter(self):
        assert contrast_ratio("#123456", "#fedcba") == contrast_ratio("#fedcba", "#123456")

    def test_short_hex_is_expanded(self):
        assert contrast_ratio("#fff", "#000") == contrast_ratio("#ffffff", "#000000")

    def test_green_channel_dominates(self):
        """
        ⚠️  ليس متوسط القنوات — العين أشدّ حساسية للأخضر بكثير.

            متوسط بسيط يجعل الأزرق النقي والأخضر النقي متساويين،
            وهما في الواقع على طرفَي نقيض في القراءة.
        """
        green = contrast_ratio("#00ff00", "#000000")
        blue = contrast_ratio("#0000ff", "#000000")
        assert green > blue * 3

    def test_light_grey_on_white_fails_aa(self):
        """الرمادي الفاتح «الأنيق» — يسقط تحت الشمس ولعين ضعيفة."""
        assert not passes_aa("#aaaaaa", "#ffffff")
        assert passes_aa("#595959", "#ffffff")


# ═══════════════════════════════════════════════════════════
#  حارس التباين
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestContrastGuard:
    def test_unreadable_palette_is_rejected(self, profile):
        """
        ⚠️  لوحة غير مقروءة تُكتشف عادةً بشكوى مستخدم لا يعرف كيف
            يصفها. الفحص هنا يجعلها خطأً في شاشة الأدمن.
        """
        palette = profile.palettes.get(mode=ThemeMode.LIGHT)
        palette.text = "#dddddd"
        palette.bg = "#ffffff"

        with pytest.raises(ValidationError):
            palette.clean()

    def test_white_on_light_green_is_rejected(self):
        """
        ⚠️  الفخّ الشائع: أبيض فوق أخضر فاتح — يبدو سليمًا ويعطي
            2.1:1، أي أقل من نصف الحد المقبول.
        """
        palette = ThemePalette(mode=ThemeMode.DARK, on_primary="#ffffff", primary="#66bb6a")

        with pytest.raises(ValidationError):
            palette.clean()

    def test_activation_refuses_a_failing_palette(self, admin_client, profile):
        candidate = BrandProfile.objects.create(code="broken", name_ar="س", name_en="X")
        ThemePalette.objects.create(
            profile=candidate, mode=ThemeMode.LIGHT, text="#eeeeee", bg="#ffffff"
        )
        ThemePalette.objects.create(profile=candidate, mode=ThemeMode.DARK)

        response = admin_client.post(reverse("v1:branding:profile-activate", args=[candidate.pk]))

        assert response.status_code == 400
        candidate.refresh_from_db()
        assert not candidate.is_active
        assert BrandProfile.objects.get(pk=profile.pk).is_active


# ═══════════════════════════════════════════════════════════
#  الحمولة العامة
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestPublicTheme:
    def test_is_public(self, profile):
        response = APIClient().get(reverse("v1:branding:theme"))
        assert response.status_code == 200

    def test_returns_ready_css_tokens(self, profile):
        """
        ⚠️  رموز جاهزة لا حقول خام.

            ترك الفرونت يبني أسماء المتغيرات يكرّرها في مستودعين،
            فتصير إضافة لون واحد تعديلين.
        """
        payload = APIClient().get(reverse("v1:branding:theme")).data

        assert payload["palettes"]["LIGHT"]["--color-primary"].startswith("#")
        assert payload["tokens"]["--radius"].endswith("rem")

    def test_both_modes_are_present(self, profile):
        payload = APIClient().get(reverse("v1:branding:theme")).data
        assert set(payload["palettes"]) == {"LIGHT", "DARK"}

    def test_works_before_any_profile_is_configured(self, db):
        """
        ⚠️  واجهة بلا ألوان ترسم صفحة بيضاء بنص أسود — تبدو عطلًا
            لا «لم تُضبط الهوية بعد».
        """
        assert not BrandProfile.objects.exists()

        payload = APIClient().get(reverse("v1:branding:theme")).data

        assert payload["palettes"]["LIGHT"]["--color-primary"]
        assert payload["palettes"]["DARK"]["--color-primary"]
        assert payload["default_mode"] == DefaultMode.SYSTEM

    def test_no_admin_fields_leak(self, profile):
        payload = str(APIClient().get(reverse("v1:branding:theme")).data)
        assert "is_active" not in payload
        assert str(profile.pk) not in payload


# ═══════════════════════════════════════════════════════════
#  الأثر الفوري — جوهر المتطلب
# ═══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestLiveControl:
    def test_color_change_reaches_the_frontend_immediately(self, admin_client, profile):
        """
        ⚠️  **جوهر المتطلب.**

            الأدمن يغيّر اللون الأساسي فينعكس على الحمولة العامة في
            الطلب التالي — بلا إعادة نشر ولا إعادة بناء.
        """
        client = APIClient()
        palette = profile.palettes.get(mode=ThemeMode.LIGHT)

        before = client.get(reverse("v1:branding:theme")).data
        assert before["palettes"]["LIGHT"]["--color-primary"] != "#0b5394"

        response = admin_client.patch(
            reverse("v1:branding:palette-detail", args=[profile.pk, palette.pk]),
            {"primary": "#0b5394", "on_primary": "#ffffff"},
            format="json",
        )
        assert response.status_code == 200

        after = client.get(reverse("v1:branding:theme")).data
        assert after["palettes"]["LIGHT"]["--color-primary"] == "#0b5394"

    def test_cache_is_invalidated_outside_the_api_too(self, profile):
        """
        ⚠️  الهوية تُعدَّل من أربعة مسارات (API · لوحة Django ·
            البذرة · الـ shell). الإبطال بإشارة لا باستدعاء يدوي —
            وإلا ترك أي مسار منسيّ ألوانًا قديمة نصف يوم.
        """
        client = APIClient()
        client.get(reverse("v1:branding:theme"))  # يملأ الكاش

        palette = profile.palettes.get(mode=ThemeMode.LIGHT)
        palette.primary = "#7b1fa2"
        palette.on_primary = "#ffffff"
        palette.save()

        after = client.get(reverse("v1:branding:theme")).data
        assert after["palettes"]["LIGHT"]["--color-primary"] == "#7b1fa2"

    def test_activating_a_profile_deactivates_the_previous(self, admin_client, profile):
        replacement = BrandProfile.objects.create(code="winter", name_ar="شتاء", name_en="Winter")
        for mode in ThemeMode:
            ThemePalette.objects.create(profile=replacement, mode=mode)

        admin_client.post(reverse("v1:branding:profile-activate", args=[replacement.pk]))

        profile.refresh_from_db()
        replacement.refresh_from_db()
        assert replacement.is_active
        assert not profile.is_active

    def test_active_profile_cannot_be_deleted(self, admin_client, profile):
        response = admin_client.delete(reverse("v1:branding:profile-detail", args=[profile.pk]))
        assert response.status_code == 409

    def test_new_profile_is_born_with_both_palettes(self, admin_client):
        """ملف بلا لوحات يعني هوية بلا ألوان — وتفعيله يطفئ الموقع."""
        response = admin_client.post(
            reverse("v1:branding:profiles"),
            {"code": "winter", "name_ar": "شتاء", "name_en": "Winter"},
            format="json",
        )

        assert response.status_code == 201
        created = BrandProfile.objects.get(code="winter")
        assert created.palettes.count() == 2
        assert not created.is_active

    def test_preview_does_not_touch_the_live_theme(self, admin_client, profile):
        """
        ⚠️  «جرّب ثم تراجع» على الهوية يعني أن كل زائر خلال المحاولة
            رأى ألوانًا مكسورة.
        """
        client = APIClient()
        before = client.get(reverse("v1:branding:theme")).data

        response = admin_client.post(
            reverse("v1:branding:preview"),
            {"primary": "#ff0000", "on_primary": "#ff0000", "mode": ThemeMode.LIGHT},
            format="json",
        )

        assert response.status_code == 200
        assert response.data["passes_aa"] is False

        after = client.get(reverse("v1:branding:theme")).data
        assert after == before

    def test_preview_ignores_unknown_fields(self, admin_client):
        """حقل مجهول واحد لا يجوز أن يصير خطأ ٥٠٠."""
        response = admin_client.post(
            reverse("v1:branding:preview"),
            {"primary": "#2e7d32", "nonsense": "x"},
            format="json",
        )
        assert response.status_code == 200

    def test_customer_cannot_edit_branding(self, profile):
        customer = _model("accounts", "User").objects.create_user(
            email="c@test.local", password=PASSWORD
        )
        customer.is_active = True
        customer.save()

        client = APIClient()
        client.force_authenticate(user=customer)

        response = client.get(reverse("v1:branding:profiles"))
        assert response.status_code == 403


@pytest.mark.django_db
def test_only_one_profile_can_be_active(profile):
    """«ما ألوان النظام؟» يجب ألا تعتمد على ترتيب الاستعلام."""
    from django.db.utils import IntegrityError

    with pytest.raises(IntegrityError):
        BrandProfile.objects.create(code="second", name_ar="ث", name_en="S", is_active=True)
