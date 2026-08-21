import { useTranslation } from 'react-i18next';

import './Spinner.css';

export function Spinner({ label }: { label?: string }) {
  const { t } = useTranslation();

  return (
    <div className="spinner" role="status">
      <span className="spinner__ring" aria-hidden />
      {/* ⚠️  Text for the screen reader — the spinner alone is entirely silent. */}
      <span className="visually-hidden">{label ?? t('common.loading')}</span>
    </div>
  );
}
