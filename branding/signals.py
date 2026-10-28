"""
Invalidate the identity cache on any edit.

⚠️  The cache here is deliberately long (12 hours) because the identity is read
    on every page load and does not change once a month. And that is exactly
    what makes invalidation mandatory: the error window is half a day, not seconds.

⚠️  The contact channels ride in the same payload, so they invalidate the same key.
    A queryset `.update()` / `.bulk_update()` fires no signal — those call sites
    (reorder) invalidate explicitly.
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from branding.models import BrandProfile, ContactChannel, ThemePalette
from branding.services import invalidate_cache


@receiver(post_save, sender=BrandProfile)
@receiver(post_save, sender=ThemePalette)
@receiver(post_delete, sender=BrandProfile)
@receiver(post_delete, sender=ThemePalette)
@receiver(post_save, sender=ContactChannel)
@receiver(post_delete, sender=ContactChannel)
def _invalidate_branding_cache(sender, **kwargs):
    invalidate_cache()
