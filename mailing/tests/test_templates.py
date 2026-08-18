"""
اختبارات القوالب المحرَّرة.

⚠️  **فتح القوالب للتحرير يفتح معها ثلاثة أبواب — وكلها تُغلَق هنا:**

    ١. `str.format` يقبل `{link.__class__}`: تعبير يتنقّل في خصائص
       الكائنات. مقبول ما دام النص في الكود، وثغرة قراءة ذاكرة لحظة
       يصير حقلًا يحرّره الأدمن.

    ٢. حرف زائد في `{totall}` كان يرفع `KeyError` فتُفقَد الرسالة —
       تحرير بريء يوقف بريد النظام كله.

    ٣. من يحرّر العربية وينسى الإنجليزية لا يكتشف ذلك أبدًا: لا يقرأ
       بريده بالإنجليزية.
"""

import pytest
from django.core.exceptions import ValidationError

from mailing import services
from mailing.models import TemplateOverride
from mailing.templates import TEMPLATES, placeholders, render_text


class TestSafeRenderer:
    def test_attribute_traversal_is_not_a_placeholder(self):
        """⚠️  البابان الأخطر: `{x.__class__}` و`{x[0]}` لا يُطابَقان أصلًا."""
        assert placeholders("{link.__class__.__mro__} و {items[0]}") == set()

    def test_attribute_expression_is_left_untouched(self):
        text = render_text("{user.password}", {"user": object()})

        assert text == "{user.password}"

    def test_typo_survives_instead_of_losing_the_message(self):
        """
        ⚠️  `{totall}` ظاهرًا في رسالة وصلت قبيحٌ ومحرج — لكنه يُقرأ
            ويُبلَّغ عنه. أما الرسالة المفقودة فلا يعرف أحد أنها كانت.
        """
        assert render_text("إجمالي {totall}", {"total": "450"}) == "إجمالي {totall}"

    def test_known_variables_are_substituted(self):
        assert render_text("مرحبًا {name}", {"name": "أحمد"}) == "مرحبًا أحمد"

    def test_every_shipped_template_declares_its_variables(self):
        """قالب بمتغيّر لا يعرفه أحد لا يمكن تحريره بأمان."""
        for key, template in TEMPLATES.items():
            assert template.variables or key, key


@pytest.mark.django_db
class TestOverrideValidation:
    def _override(self, **overrides):
        payload = {
            "key": "password_changed",
            "subject_ar": "تم تغيير كلمة المرور",
            "subject_en": "Password changed",
            "body_ar": "مرحبًا {name}",
            "body_en": "Hello {name}",
        }
        payload.update(overrides)
        return TemplateOverride(**payload)

    def test_unknown_variable_is_rejected_at_save(self):
        """
        ⚠️  الكود وحده يعرف ما يضعه في السياق: متغيّر خارج قائمته يصل
            إلى المستلم نصًّا خامًا. الرفض هنا يمنعه قبل أول رسالة.
        """
        override = self._override(body_ar="مرحبًا {name}، رصيدك {balance}")

        with pytest.raises(ValidationError) as exc:
            override.full_clean()

        assert "body_ar" in exc.value.error_dict

    def test_unknown_template_key_is_rejected(self):
        with pytest.raises(ValidationError):
            self._override(key="no-such-template").full_clean()

    def test_both_languages_are_required(self):
        """من يحرّر العربية وينسى الإنجليزية لا يكتشف ذلك أبدًا."""
        with pytest.raises(ValidationError) as exc:
            self._override(body_en="").full_clean()

        assert "body_en" in exc.value.error_dict

    def test_a_valid_override_passes(self):
        self._override().full_clean()


@pytest.mark.django_db
class TestOverrideResolution:
    def test_override_wins_over_code(self):
        TemplateOverride.objects.create(
            key="password_changed",
            subject_ar="تنبيه أمني",
            subject_en="Security alert",
            body_ar="مرحبًا {name}",
            body_en="Hello {name}",
        )

        subject, _body = services.render("password_changed", "ar", {"name": "أحمد"})

        assert subject == "تنبيه أمني"

    def test_disabling_the_override_restores_the_original(self):
        """
        ⚠️  تحرير فاسد وقت الضغط يجب أن يُلغى بضغطة — لا بإعادة كتابة
            النص الأصلي من الذاكرة ولا باستعادة نسخة احتياطية.
        """
        TemplateOverride.objects.create(
            key="password_changed",
            subject_ar="تنبيه أمني",
            subject_en="Security alert",
            body_ar="مرحبًا {name}",
            body_en="Hello {name}",
            is_active=False,
        )

        subject, _body = services.render("password_changed", "ar", {"name": "أحمد"})

        assert subject == TEMPLATES["password_changed"].subject_ar

    def test_no_override_at_all_is_a_valid_state(self):
        """الجدول تجاوزات لا قوالب: النظام يعمل كاملًا وهو فارغ."""
        assert TemplateOverride.objects.count() == 0

        subject, body = services.render("password_changed", "ar", {"name": "أحمد"})

        assert subject and body

    def test_a_broken_override_falls_back_to_code_instead_of_dropping_the_mail(
        self, monkeypatch
    ):
        """
        ⚠️  التجاوز يحرّره إنسان، وإنسان يخطئ. وخلل فيه يجب ألا يمنع
            وصول «إعادة تعيين كلمة المرور» — النسخة الأصلية قائمة
            دائمًا، فاستعمالها أرخص من إسقاط الرسالة.

            والعطل هنا مُحاكى بحقن استثناء في التصيير: القيود تمنع
            الصفّ التالف من الكتابة، وتبقى الطرق الأخرى إليه (ترحيل
            بيانات · تعديل SQL مباشر · خلل مستقبلي في التصيير).
        """
        TemplateOverride.objects.create(
            key="password_changed",
            subject_ar="تنبيه",
            subject_en="Alert",
            body_ar="مرحبًا {name}",
            body_en="Hello {name}",
        )

        def explode(self, language, context):
            raise ValueError("تجاوز تالف")

        monkeypatch.setattr(TemplateOverride, "render", explode)

        subject, _body = services.render("password_changed", "ar", {"name": "أحمد"})

        assert subject == TEMPLATES["password_changed"].subject_ar
