"""
تشفير بيانات اعتماد البوابات.

⚠️  **ما يهم فعلًا هنا هو ما في قاعدة البيانات لا ما في بايثون.**

    اختبار `credential.value == "secret"` وحده يمرّ حتى لو لم
    يُشفَّر شيء — فهو يقرأ ما كتبه للتو. الاختبار الحقيقي يقرأ
    العمود بـ SQL خام ويتأكد أن السر ليس فيه.
"""

import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import FieldError, ImproperlyConfigured
from django.db import connection

from core import encryption
from payments.models import PaymentProvider, ProviderCredential

pytestmark = pytest.mark.django_db


@pytest.fixture
def provider():
    return PaymentProvider.objects.create(
        code="paymob-test",
        name_ar="بيموب",
        name_en="Paymob",
        adapter_key="paymob",
    )


def raw_value(credential) -> str:
    """القيمة كما هي في العمود — بلا مرور بفكّ تشفير الحقل."""
    table = ProviderCredential._meta.db_table
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT value FROM {table} WHERE id = %s", [credential.pk])  # noqa: S608
        return cursor.fetchone()[0]


# ═══════════════════════════════════════════════════════════
#  التخزين
# ═══════════════════════════════════════════════════════════


class TestStorage:
    def test_secret_is_not_stored_in_plain_text(self, provider):
        """
        ⚠️  **الاختبار الأهم في الملف.**

            نسخة احتياطية أو تسريب SQL يجب ألا يعطي مفتاحًا قابلًا
            للاستعمال.
        """
        credential = ProviderCredential.objects.create(
            provider=provider, key="api_key", value="sk-live-super-secret"
        )

        stored = raw_value(credential)
        assert "sk-live-super-secret" not in stored
        assert stored.startswith(encryption.PREFIX)

    def test_value_reads_back_identical(self, provider):
        ProviderCredential.objects.create(
            provider=provider, key="api_key", value="sk-live-super-secret"
        )

        # قراءة جديدة من قاعدة البيانات لا من الكائن المحفوظ
        fetched = ProviderCredential.objects.get(provider=provider, key="api_key")
        assert fetched.value == "sk-live-super-secret"

    def test_same_secret_encrypts_differently_each_time(self, provider):
        """
        ⚠️  التشفير الحتمي يسرّب التساوي: من يرى العمود يعرف أن
            بوابتين تستخدمان نفس المفتاح.
        """
        first = ProviderCredential.objects.create(
            provider=provider, key="api_key", value="same-secret"
        )
        second = ProviderCredential.objects.create(
            provider=provider, key="hmac_secret", value="same-secret"
        )

        assert raw_value(first) != raw_value(second)
        assert first.value == second.value == "same-secret"

    def test_adapter_receives_the_plain_secret(self, provider):
        """
        ⚠️  التشفير الذي يصل البوابة نصًّا مشفّرًا يكسر كل عملية دفع.
            هذا الاختبار يمسك ذلك عند مسار البناء الحقيقي.
        """
        from payments.services import _build_adapter

        ProviderCredential.objects.create(
            provider=provider, key="hmac_secret", value="the-real-secret", is_sandbox=True
        )

        adapter = _build_adapter(provider)
        assert adapter.credentials["hmac_secret"] == "the-real-secret"

    def test_masked_value_shows_last_four_of_the_plain_secret(self, provider):
        credential = ProviderCredential.objects.create(
            provider=provider, key="api_key", value="abcdefgh1234"
        )
        assert credential.masked_value.endswith("1234")
        assert "abcdefgh" not in credential.masked_value


# ═══════════════════════════════════════════════════════════
#  الاستعلام
# ═══════════════════════════════════════════════════════════


class TestQuerying:
    def test_filtering_by_value_is_refused(self, provider):
        """
        ⚠️  **الفشل الصامت هو الخطر**: التشفير عشوائي، فـ
            `filter(value="k")` كان سيعيد صفرًا دائمًا بلا خطأ —
            ويبدو ذلك كـ«لا يوجد» لا كـ«لا يصح السؤال».
        """
        ProviderCredential.objects.create(provider=provider, key="api_key", value="k")

        with pytest.raises(FieldError):
            list(ProviderCredential.objects.filter(value="k"))

    def test_null_check_still_works(self, provider):
        """الفحص على مستوى `NULL` لا يمسّ المحتوى — فيبقى مسموحًا."""
        ProviderCredential.objects.create(provider=provider, key="api_key", value="k")
        assert ProviderCredential.objects.filter(value__isnull=False).count() == 1


# ═══════════════════════════════════════════════════════════
#  المفتاح
# ═══════════════════════════════════════════════════════════


class TestKeyHandling:
    def test_writing_without_a_key_is_refused(self, provider, settings):
        """
        ⚠️  **لا سقوط إلى نص صريح.**

            الحفظ الصامت بلا تشفير هو بالضبط الحالة التي أُصلحت:
            حقل موصوف بأنه «مشفّر» ومحتواه مكشوف.
        """
        settings.FIELD_ENCRYPTION_KEY = ""

        with pytest.raises(ImproperlyConfigured):
            ProviderCredential.objects.create(provider=provider, key="api_key", value="secret")

    def test_wrong_key_reads_empty_instead_of_crashing(self, provider, settings):
        """
        ⚠️  المفتاح الخاطئ يقع على **قوائم**: رفع الاستثناء يُسقط
            شاشة البوابات كلها بدل صف واحد.

            والقيمة الفارغة تجعل المحوّل يفشل بـ «بيانات اعتماد
            ناقصة» — وهو فشل آمن: لا تحصيل بمفتاح لم يُقرأ.
        """
        credential = ProviderCredential.objects.create(
            provider=provider, key="api_key", value="secret"
        )

        settings.FIELD_ENCRYPTION_KEY = Fernet.generate_key().decode()

        assert ProviderCredential.objects.get(pk=credential.pk).value == ""

    def test_rotation_reads_old_and_writes_new(self, provider, settings):
        """
        ⚠️  بلا تدوير، مفتاح مسرَّب يعني قاعدة بيانات لا تُنقَذ بلا
            توقّف. الأول يشفّر وكلها تفكّ.
        """
        old_key = settings.FIELD_ENCRYPTION_KEY
        credential = ProviderCredential.objects.create(
            provider=provider, key="api_key", value="written-with-old-key"
        )

        new_key = Fernet.generate_key().decode()
        settings.FIELD_ENCRYPTION_KEY = f"{new_key},{old_key}"

        # القديم ما زال مقروءًا
        fetched = ProviderCredential.objects.get(pk=credential.pk)
        assert fetched.value == "written-with-old-key"

        # وإعادة الحفظ تنقله إلى الجديد
        fetched.save(update_fields=["value"])
        settings.FIELD_ENCRYPTION_KEY = new_key
        assert ProviderCredential.objects.get(pk=credential.pk).value == "written-with-old-key"

    def test_malformed_key_names_the_setting(self, provider, settings):
        """
        رسالة `cryptography` الأصلية لا تذكر اسم المتغيّر، فيبحث
        المشغّل عنها في الكود لا في ملف البيئة.
        """
        settings.FIELD_ENCRYPTION_KEY = "not-a-fernet-key"

        with pytest.raises(ImproperlyConfigured, match="FIELD_ENCRYPTION_KEY"):
            ProviderCredential.objects.create(provider=provider, key="api_key", value="secret")


# ═══════════════════════════════════════════════════════════
#  الصفوف القديمة
# ═══════════════════════════════════════════════════════════


class TestLegacyRows:
    def test_plain_text_rows_stay_readable(self, provider):
        """
        ⚠️  الصف المكتوب قبل الترحيل بلا علامة تشفير — قراءته يجب
            أن تعمل، وإلا توقّف الدفع لحظة النشر وقبل أن يمرّ
            ترحيل البيانات.
        """
        credential = ProviderCredential.objects.create(
            provider=provider, key="api_key", value="new-value"
        )

        table = ProviderCredential._meta.db_table
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET value = %s WHERE id = %s",  # noqa: S608
                ["legacy-plain-secret", credential.pk],
            )

        assert ProviderCredential.objects.get(pk=credential.pk).value == "legacy-plain-secret"

    def test_re_encrypting_an_encrypted_value_is_a_no_op(self):
        """
        ⚠️  يجعل ترحيل البيانات قابلًا لإعادة التشغيل: تشفير مزدوج
            كان ينتج قيمة لا يفكّها أحد.
        """
        once = encryption.encrypt("secret")
        assert encryption.encrypt(once) == once
        assert encryption.decrypt(once) == "secret"

    def test_empty_values_pass_through_untouched(self):
        assert encryption.encrypt("") == ""
        assert encryption.encrypt(None) is None
        assert encryption.decrypt("") == ""
        assert encryption.decrypt(None) is None
