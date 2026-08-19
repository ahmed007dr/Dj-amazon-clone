"""
The shared base models.

⚠️  Infrastructure only — no business rule is permitted here.
    The membership test: delete one domain; if the code is still needed, it belongs to core.
"""

import uuid

import uuid_utils
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def uuid7() -> uuid.UUID:
    """
    A UUIDv7 identifier — a time prefix plus randomness.

    Chosen over v4 because v4 is entirely random, which causes B-tree page
    splits and degrades inserts at the scale of millions. v7 is time-ordered and
    so preserves index locality. (ADR-26)
    """
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)


class UUIDPrimaryKeyModel(models.Model):
    """
    A UUIDv7 primary key.

    Inherited by **every model that appears in a URL or an API response**.
    High-volume internal tables stay on BigInt. (ADR-25, ADR-28)
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
        """A bulk soft delete."""
        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()


class SoftDeleteManager(models.Manager):
    """The default manager — it excludes soft-deleted rows."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(deleted_at__isnull=True)


class AllObjectsManager(models.Manager):
    """Includes the deleted — for the admin and for auditing."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db)


class SoftDeleteModel(models.Model):
    """
    A soft delete for business entities.

    A product that has actually been sold is never deleted — historical orders
    point at it.
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
    """Who created it and who last changed it. The detailed record lives in core.audit.AuditLog."""

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
    """The usual base for an exposed business entity."""

    class Meta:
        abstract = True
