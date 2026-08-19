"""
Edited template tests.

⚠️  **Opening the templates for editing opens three doors with them — and all are closed here:**

    1. `str.format` accepts `{link.__class__}`: an expression walking through an
       object's attributes. Tolerable while the text lives in code, and a
       memory-read hole the moment it becomes a field the admin edits.

    2. One extra character in `{totall}` raised `KeyError` and the message was
       lost — an innocent edit stopping the whole system's mail.

    3. Whoever edits the Arabic and forgets the English never discovers it: they
       do not read their mail in English.
"""

import pytest
from django.core.exceptions import ValidationError

from mailing import services
from mailing.models import TemplateOverride
from mailing.templates import TEMPLATES, placeholders, render_text


class TestSafeRenderer:
    def test_attribute_traversal_is_not_a_placeholder(self):
        """⚠️  The two most dangerous doors: `{x.__class__}` and `{x[0]}` do not match at all."""
        assert placeholders("{link.__class__.__mro__} و {items[0]}") == set()

    def test_attribute_expression_is_left_untouched(self):
        text = render_text("{user.password}", {"user": object()})

        assert text == "{user.password}"

    def test_typo_survives_instead_of_losing_the_message(self):
        """
        ⚠️  A visible `{totall}` in a message that arrived is ugly and
            embarrassing — but it gets read and reported. Whereas nobody knows a
            lost message ever existed.
        """
        assert render_text("إجمالي {totall}", {"total": "450"}) == "إجمالي {totall}"

    def test_known_variables_are_substituted(self):
        assert render_text("مرحبًا {name}", {"name": "أحمد"}) == "مرحبًا أحمد"

    def test_every_shipped_template_declares_its_variables(self):
        """A template with a variable nobody knows cannot be edited safely."""
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
        ⚠️  Only the code knows what it puts in the context: a variable outside
            its list reaches the recipient as raw text. Rejecting here prevents
            it before the first message.
        """
        override = self._override(body_ar="مرحبًا {name}، رصيدك {balance}")

        with pytest.raises(ValidationError) as exc:
            override.full_clean()

        assert "body_ar" in exc.value.error_dict

    def test_unknown_template_key_is_rejected(self):
        with pytest.raises(ValidationError):
            self._override(key="no-such-template").full_clean()

    def test_both_languages_are_required(self):
        """Whoever edits the Arabic and forgets the English never discovers it."""
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
        ⚠️  A bad edit made under pressure must be undone with one click — not
            by retyping the original text from memory, nor by restoring a backup.
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
        """The table holds overrides, not templates: the system works fully while it is empty."""
        assert TemplateOverride.objects.count() == 0

        subject, body = services.render("password_changed", "ar", {"name": "أحمد"})

        assert subject and body

    def test_a_broken_override_falls_back_to_code_instead_of_dropping_the_mail(self, monkeypatch):
        """
        ⚠️  The override is edited by a human, and humans make mistakes. And a
            defect in it must not stop "password reset" arriving — the original
            version is always there, and using it is cheaper than dropping the
            message.

            The fault here is simulated by injecting an exception into the
            rendering: the constraints prevent a corrupt row being written, and
            the other routes to it remain (a data migration · a direct SQL edit ·
            a future defect in the rendering).
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
