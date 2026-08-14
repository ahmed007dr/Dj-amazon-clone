import { useTranslation } from 'react-i18next';

import './StarRating.css';

/**
 * ⚠️  النجوم زخرفة بصرية — القيمة نصًّا لقارئ الشاشة.
 *
 *     خمسة رموز `★` بلا نص تُقرأ «نجمة نجمة نجمة…» بلا معنى.
 */
export function StarRating({ value, count }: { value: number | string; count?: number }) {
  const { t } = useTranslation();
  const numeric = typeof value === 'string' ? Number.parseFloat(value) : value;
  const rounded = Math.round(numeric);

  return (
    <span className="stars">
      <span className="stars__glyphs" aria-hidden>
        {'★★★★★'.slice(0, rounded)}
        <span className="stars__empty">{'★★★★★'.slice(0, 5 - rounded)}</span>
      </span>

      <span className="visually-hidden">
        {t('catalog.ratingOf', { value: numeric.toFixed(1) })}
      </span>

      {count !== undefined ? <span className="stars__count muted">({count})</span> : null}
    </span>
  );
}
