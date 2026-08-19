"""
Operational system settings, configurable by the admin.

They replace constants fixed in code.

The boundaries:
  core/settings  → operational settings (limits · feature flags · business rules)
  branding/      → everything the customer sees (colours · logo · fonts)
"""

from decimal import Decimal

from django.core.cache import cache
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models.base import TimeStampedModel

CACHE_KEY_PREFIX = "system_setting:"
CACHE_TIMEOUT = 60 * 60


class SettingValueType(models.TextChoices):
    STRING = "STRING", _("نص")
    INT = "INT", _("رقم صحيح")
    DECIMAL = "DECIMAL", _("رقم عشري")
    BOOL = "BOOL", _("صح/خطأ")
    JSON = "JSON", _("JSON")


class SettingGroup(models.TextChoices):
    GENERAL = "general", _("عام")
    TAX = "tax", _("الضريبة")
    INVENTORY = "inventory", _("المخزون")
    ORDERS = "orders", _("الطلبات")
    PRICING = "pricing", _("التسعير")
    LOYALTY = "loyalty", _("الولاء")
    SECURITY = "security", _("الأمان")
    NOTIFICATIONS = "notifications", _("الإشعارات")


class SystemSetting(TimeStampedModel):
    key = models.SlugField(_("المفتاح"), max_length=100, primary_key=True)
    value = models.JSONField(_("القيمة"))
    value_type = models.CharField(_("نوع القيمة"), max_length=16, choices=SettingValueType.choices)
    group = models.CharField(
        _("المجموعة"),
        max_length=32,
        choices=SettingGroup.choices,
        default=SettingGroup.GENERAL,
        db_index=True,
    )
    label_ar = models.CharField(_("الوصف بالعربية"), max_length=200)
    label_en = models.CharField(_("الوصف بالإنجليزية"), max_length=200)
    help_text_ar = models.TextField(_("شرح بالعربية"), blank=True)
    help_text_en = models.TextField(_("شرح بالإنجليزية"), blank=True)
    is_editable = models.BooleanField(_("قابل للتحرير"), default=True)

    class Meta:
        verbose_name = _("إعداد نظام")
        verbose_name_plural = _("إعدادات النظام")
        ordering = ["group", "key"]

    def __str__(self):
        return f"{self.key} = {self.value}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete(f"{CACHE_KEY_PREFIX}{self.key}")

    @property
    def typed_value(self):
        if self.value_type == SettingValueType.DECIMAL:
            return Decimal(str(self.value))
        return self.value

    # ── The public interface ───────────────────────────────

    @classmethod
    def get(cls, key: str, default=None):
        """Read a setting, with caching."""
        cache_key = f"{CACHE_KEY_PREFIX}{key}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            setting = cls.objects.get(pk=key)
        except cls.DoesNotExist:
            return default

        value = setting.typed_value
        cache.set(cache_key, value, CACHE_TIMEOUT)
        return value

    @classmethod
    def set(cls, key: str, value, **defaults):
        setting, _created = cls.objects.update_or_create(
            pk=key, defaults={"value": value, **defaults}
        )
        return setting
