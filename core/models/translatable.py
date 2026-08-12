"""
ترجمة المحتوى — عربي وإنجليزي.

نميّز بين نوعين:
  • ترجمات الواجهة    → gettext / ملفات .po
  • ترجمات المحتوى    → حقلان في قاعدة البيانات  ← هذا الملف

المحتوى الذي يراه العميل يُخزَّن باللغتين ويُرسَل بهما معًا (ADR-34).
"""

from django.db import models
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _


class TranslatedFieldMixin:
    """
    يوفّر خاصية `<field>` تُرجع النسخة المطابقة للغة الحالية.

        class Product(TranslatedFieldMixin, BaseModel):
            TRANSLATED_FIELDS = ['name', 'description']
            name_ar = models.CharField(max_length=200)
            name_en = models.CharField(max_length=200)

        product.name        # حسب لغة الطلب، مع رجوع للعربية
        product.name_ar     # صريح
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
        # يُستدعى فقط عند فشل البحث المعتاد
        translated_fields = type(self).__dict__.get("TRANSLATED_FIELDS")
        if translated_fields and name in translated_fields:
            return self.translated(name)
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")


def TranslatedCharField(verbose_name, **kwargs):  # noqa: N802
    """مساعد لتقليل التكرار عند تعريف حقلَي لغة."""
    kwargs.setdefault("max_length", 200)
    return models.CharField(verbose_name, **kwargs)


class BilingualNameMixin(TranslatedFieldMixin, models.Model):
    """اسم ثنائي اللغة — النمط الأكثر تكرارًا."""

    TRANSLATED_FIELDS = ["name"]

    name_ar = models.CharField(_("الاسم بالعربية"), max_length=200)
    name_en = models.CharField(_("الاسم بالإنجليزية"), max_length=200)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name_ar or self.name_en
