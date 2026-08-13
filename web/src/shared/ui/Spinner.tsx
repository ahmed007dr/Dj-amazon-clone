import { useTranslation } from 'react-i18next';

import './Spinner.css';

export function Spinner({ label }: { label?: string }) {
  const { t } = useTranslation();

  return (
    <div className="spinner" role="status">
      <span className="spinner__ring" aria-hidden />
      {/* ⚠️  نص للقارئ الشاشي — الدوّارة وحدها صامتة تمامًا. */}
      <span className="visually-hidden">{label ?? t('common.loading')}</span>
    </div>
  );
}
