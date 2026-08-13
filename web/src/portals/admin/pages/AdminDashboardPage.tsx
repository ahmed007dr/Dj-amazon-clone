import { useTranslation } from 'react-i18next';

import { PageHeader } from '@/shared/layouts/PageHeader';
import { StateMessage } from '@/shared/ui/StateMessage';

export function AdminDashboardPage() {
  const { t } = useTranslation();

  return (
    <>
      <PageHeader title={t('nav.dashboard')} />
      {/* الشاشة الفعلية تُبنى مع بقية أقسام اللوحة */}
      <StateMessage icon="▤" title={t('state.emptyTitle')} />
    </>
  );
}
