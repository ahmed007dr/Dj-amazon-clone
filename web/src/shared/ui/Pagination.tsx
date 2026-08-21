import { useTranslation } from 'react-i18next';

import { Button } from './Button';

import './Pagination.css';

/**
 * Page-number pagination — for the admin screens alone.
 *
 * ⚠️  "Page 5 of 42" is operational information whoever processes orders needs,
 *     and the server exposes `count` for these screens only. The public listings
 *     use a cursor, because exposing the total count tells a competitor the
 *     volume of activity. (ADR-32)
 */
export function Pagination({
  page,
  pages,
  onChange,
}: {
  page: number;
  pages: number;
  onChange: (next: number) => void;
}) {
  const { t } = useTranslation();

  if (pages <= 1) return null;

  return (
    <nav className="pagination" aria-label={t('common.next')}>
      <Button
        variant="secondary"
        size="sm"
        disabled={page <= 1}
        onClick={() => {
          onChange(page - 1);
        }}
      >
        {t('common.previous')}
      </Button>

      <span className="pagination__status">{t('common.pageOf', { page, pages })}</span>

      <Button
        variant="secondary"
        size="sm"
        disabled={page >= pages}
        onClick={() => {
          onChange(page + 1);
        }}
      >
        {t('common.next')}
      </Button>
    </nav>
  );
}
