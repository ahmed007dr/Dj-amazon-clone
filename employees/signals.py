"""
مزامنة صلاحيات الموظف مع حالته.

⚠️  **إشارة لا استدعاء يدوي.**

    إيقاف الموظف يقع من أكثر من مكان: شاشة الأدمن · أمر إداري ·
    تصحيح مباشر. ربط سحب الصلاحيات باستدعاء في نقطة واحدة يعني
    أن كل مسار آخر يترك موظفًا انتهت خدمته ومجموعته باقية —
    و`has_perm` في بقية النظام يقول «نعم».
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from employees.models import EmployeeProfile

logger = logging.getLogger(__name__)


@receiver(post_save, sender=EmployeeProfile, weak=False)
def sync_permissions_with_status(sender, instance, created, **kwargs):
    """
    ⚠️  **`apply_role_permissions` لا `set_role`.**

        الثانية تحفظ الملف، فتُعيد إطلاق هذه الإشارة إلى ما لا
        نهاية. وقع ذلك فعلًا، و`except` أدناه كان يبتلع
        `RecursionError` — فيبدو الحفظ ناجحًا بينما كل عملية تحرق
        ألف إطار مكدس وتسجّل استثناءً لا يقرأه أحد.

    ⚠️  والفشل يُسجَّل ولا يُفشل الحفظ.

        تعطّل المزامنة يجب ألا يمنع إيقاف موظف — والإيقاف هو
        الإجراء العاجل. لكنه **يُسجَّل بمستوى خطأ**: موظف موقوف
        بصلاحيات باقية حالة تُراجَع لا تُبتلع.
    """
    from employees import services

    try:
        if instance.is_active:
            services.apply_role_permissions(instance)
        else:
            services.revoke_permissions(instance)
    except RecursionError:
        # ⚠️  لا يُبتلع أبدًا: هو عَرَض خلل بنيوي لا فشل عابر،
        #     وابتلاعه هو ما أخفاه أول مرة.
        raise
    except Exception:
        logger.exception("فشلت مزامنة صلاحيات الموظف %s", instance.employee_number)
