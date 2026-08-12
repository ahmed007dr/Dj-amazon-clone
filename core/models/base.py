"""
النماذج الأساسية المشتركة.

⚠️  بنية تحتية فقط — ممنوع أي قاعدة عمل هنا.
    اختبار الانتماء: احذف نطاقًا واحدًا؛ إن بقي الكود مطلوبًا فهو core.
"""

import uuid

import uuid_utils
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def uuid7() -> uuid.UUID:
    """
    معرّف UUIDv7 — بادئة زمنية + عشوائي.

    اخترناه على v4 لأن v4 عشوائي بالكامل فيسبّب انقسام صفحات B-tree
    وتدهور الإدراج عند الملايين. أما v7 فمرتّب زمنيًا فيحافظ على
    موضعية الفهرس. (ADR-26)
    """
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)


class UUIDPrimaryKeyModel(models.Model):
    """
    مفتاح أساسي UUIDv7.

    يرثه **كل نموذج يظهر في رابط أو استجابة API**.
    الجداول الداخلية عالية الحجم تبقى BigInt. (ADR-25, ADR-28)
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid7,
        editable=False,
        verbose_name=_("المعرّف"),
    )

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(_("تاريخ الإنشاء"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("تاريخ التعديل"), auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)

    def delete(self):
        """حذف ناعم جماعي."""
        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()


class SoftDeleteManager(models.Manager):
    """المدير الافتراضي — يستبعد المحذوف ناعمًا."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(deleted_at__isnull=True)


class AllObjectsManager(models.Manager):
    """يشمل المحذوف — للأدمن والتدقيق."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db)


class SoftDeleteModel(models.Model):
    """
    حذف ناعم للكيانات التجارية.

    لا يُحذف منتج بِيع فعلًا — الطلبات التاريخية تشير إليه.
    """

    deleted_at = models.DateTimeField(_("تاريخ الحذف"), null=True, blank=True, db_index=True)

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(using=using, update_fields=["deleted_at"])

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)


class AuditedModel(models.Model):
    """مَن أنشأ ومَن عدّل. السجل التفصيلي في core.audit.AuditLog."""

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("أنشأه"),
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("عدّله"),
    )

    class Meta:
        abstract = True


class BaseModel(UUIDPrimaryKeyModel, TimeStampedModel, SoftDeleteModel):
    """الأساس المعتاد لكيان تجاري مكشوف."""

    class Meta:
        abstract = True
