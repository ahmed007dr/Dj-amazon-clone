"""
المعرّفات النصية (slugs).

⚠️  كانت في `catalog` فاستوردها `academic` — وهما صنوان مستقلان في
    نفس الطبقة، فرفضه `import-linter`.

    وهو محق: توليد slug فريد وثابت **بنية تحتية عامة** لا منطق
    كتالوج. مكانها `core` حيث يصل إليها الجميع نازلًا.
"""

from django.db import models
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _


def unique_slug(model, base: str, instance_pk=None) -> str:
    """
    slug فريد **وثابت**.

    ⚠️  الكود القديم كان يعيد توليد الـ slug في **كل حفظ** — أي أن
        تعديل اسم منتج يكسر رابطه وكل ما أشار إليه من فهرسة وروابط
        خارجية.
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
    """يولّد الـ slug عند الإنشاء فقط ثم لا يمسّه."""

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
