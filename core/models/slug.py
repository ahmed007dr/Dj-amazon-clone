"""
Textual identifiers (slugs).

⚠️  These used to live in `catalog`, and `academic` imported them — two
    independent siblings on the same layer, so `import-linter` refused it.

    And it was right: generating a unique, stable slug is **general
    infrastructure**, not catalogue logic. Its place is `core`, where everyone
    reaches it downward.
"""

from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


def unique_slug(model, base: str, instance_pk=None) -> str:
    """
    A unique **and stable** slug.

    ⚠️  The legacy code regenerated the slug on **every save** — meaning editing
        a product's name broke its URL and everything that pointed at it,
        indexing and external links alike.
    """
    candidate = slugify(base, allow_unicode=True) or "item"

    manager = getattr(model, "all_objects", model.objects)
    queryset = manager.filter(slug=candidate)
    if instance_pk:
        queryset = queryset.exclude(pk=instance_pk)

    if not queryset.exists():
        return candidate

    from core.identifiers import random_code

    return f"{candidate}-{random_code(5).lower()}"


class SlugMixin(models.Model):
    """Generates the slug on creation only, and never touches it again."""

    slug = models.SlugField(
        _("المعرّف النصي"),
        max_length=255,
        unique=True,
        allow_unicode=True,
        blank=True,
        help_text=_("يُولَّد تلقائيًا ولا يتغيّر بعدها — تغييره يكسر الروابط"),
    )

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(type(self), self.slug_source(), self.pk)
        super().save(*args, **kwargs)

    def slug_source(self) -> str:
        return getattr(self, "name_en", "") or getattr(self, "name_ar", "")
