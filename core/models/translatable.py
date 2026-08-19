"""
Content translation — Arabic and English.

We distinguish two kinds:
  • interface translations  → gettext / .po files
  • content translations    → two database fields  ← this file

Content the customer sees is stored in both languages and sent in both (ADR-34).
"""

from django.db import models
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _


class TranslatedFieldMixin:
    """
    Provides a `<field>` property returning the version matching the current language.

        class Product(TranslatedFieldMixin, BaseModel):
            TRANSLATED_FIELDS = ['name', 'description']
            name_ar = models.CharField(max_length=200)
            name_en = models.CharField(max_length=200)

        product.name        # per the request language, falling back to Arabic
        product.name_ar     # explicit
    """

    TRANSLATED_FIELDS: list[str] = []
    FALLBACK_LANGUAGE = "ar"

    def translated(self, field_name: str) -> str:
        lang = (get_language() or self.FALLBACK_LANGUAGE)[:2]
        value = getattr(self, f"{field_name}_{lang}", "")
        if not value:
            value = getattr(self, f"{field_name}_{self.FALLBACK_LANGUAGE}", "")
        return value

    def __getattr__(self, name):
        # Called only when the ordinary lookup fails
        translated_fields = type(self).__dict__.get("TRANSLATED_FIELDS")
        if translated_fields and name in translated_fields:
            return self.translated(name)
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")


def TranslatedCharField(verbose_name, **kwargs):  # noqa: N802
    """A helper that reduces repetition when defining a pair of language fields."""
    kwargs.setdefault("max_length", 200)
    return models.CharField(verbose_name, **kwargs)


class BilingualNameMixin(TranslatedFieldMixin, models.Model):
    """A bilingual name — the most frequently repeated pattern."""

    TRANSLATED_FIELDS = ["name"]

    name_ar = models.CharField(_("الاسم بالعربية"), max_length=200)
    name_en = models.CharField(_("الاسم بالإنجليزية"), max_length=200)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name_ar or self.name_en
