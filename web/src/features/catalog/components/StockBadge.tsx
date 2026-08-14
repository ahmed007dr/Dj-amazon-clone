import { useTranslation } from 'react-i18next';

import { Badge } from '@/shared/ui/Badge';

import type { Availability } from '../types';

/**
 * حالة التوفر.
 *
 * ⚠️  الرقم يُعرض **حين يرسله الخادم فقط**.
 *
 *     الخادم يكشف العدد تحت عتبة معيّنة («متبقٍ ٣») ويحجبه فوقها
 *     («متوفر») — لأن «متبقٍ ٨٤٧» يعطي المنافس حجم المخزون.
 *     الواجهة لا تعيد بناء الرقم ولا تخمّنه.
 */
export function StockBadge({ availability }: { availability: Availability | undefined }) {
  const { t } = useTranslation();

  // لا تُعرض شارة قبل وصول البيانات — «غير متوفر» خاطئة أسوأ من الصمت
  if (!availability) return null;

  if (!availability.is_available) {
    return <Badge tone="danger">{t('catalog.outOfStock')}</Badge>;
  }

  if (availability.is_low) {
    return (
      <Badge tone="warning">
        {availability.available !== null
          ? t('catalog.onlyLeft', { count: availability.available })
          : t('catalog.lowStock')}
      </Badge>
    );
  }

  return <Badge tone="success">{t('catalog.inStock')}</Badge>;
}
