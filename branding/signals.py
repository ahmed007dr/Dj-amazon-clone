"""
إبطال كاش الهوية عند أي تعديل.

⚠️  الكاش هنا طويل عمدًا (١٢ ساعة) لأن الهوية تُقرأ في كل تحميل
    صفحة ولا تتغيّر مرة في الشهر. وهذا بالضبط ما يجعل الإبطال
    إلزاميًا: نافذة الخطأ نصف يوم لا ثوانٍ.
"""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from branding.models import BrandProfile, ThemePalette
from branding.services import invalidate_cache


@receiver(post_save, sender=BrandProfile)
@receiver(post_save, sender=ThemePalette)
@receiver(post_delete, sender=BrandProfile)
@receiver(post_delete, sender=ThemePalette)
def _invalidate_branding_cache(sender, **kwargs):
    invalidate_cache()
