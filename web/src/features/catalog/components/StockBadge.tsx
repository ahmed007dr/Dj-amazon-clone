import { useTranslation } from 'react-i18next';

import { Badge } from '@/shared/ui/Badge';

import type { Availability } from '../types';

/**
 * The availability status.
 *
 * ⚠️  The number is shown **only when the server sends it**.
 *
 *     The server reveals the count below a given threshold ("3 left") and
 *     withholds it above ("in stock") — because "847 left" gives a competitor
 *     your stock volume. The frontend neither reconstructs the number nor guesses it.
 */
export function StockBadge({ availability }: { availability: Availability | undefined }) {
  const { t } = useTranslation();

  // No badge is shown before the data arrives — a wrong "out of stock" is worse than silence
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
